# -*- coding: utf-8 -*-
"""split_ast.py —— 用语法树精确切方法（替代按行猜边界的老工具）。

老工具（tools/split_mixin.py）靠正则找 `def` 边界，反复踩坑：
    · 把相邻方法/模块级 import 一起吃掉（`_activate_core` 失踪）
    · 装饰器留在原文件（`@staticmethod` 丢失 → 多一个 self）
    · 模块级函数被当成方法搬走（`ws_header_name`）

这个版本换 ast：
    ① `ast.parse` 拿到每个方法（含装饰器）的 **精确行号区间**（lineno / end_lineno）
    ② 按行号切片，**原文照搬**（注释、缩进、格式一个字不动）
    ③ 切完做**符号对账**：原类方法集合 == 留下的 + 搬走的，缺一个就报错退出
    ④ 新模块的 import 由 AST 分析补齐（标准库 / 项目内模块 / shell_util 共享名）

用法：
    python tools/split_ast.py --src DICK_core.py --class ChatCore \
        --out core_prompt.py --mixin PromptMixin --match "_build_role_prompt|_rebuild_system_node|..."

不加 --write 只做试运行（打印将搬走哪些方法、多少行）。
"""
from __future__ import annotations

import argparse
import ast
import builtins
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    return io.open(path, encoding="utf-8").read()


def find_class(tree, name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def method_span(fn, lines):
    """方法（含装饰器与紧邻注释）的行号区间，1-based → 0-based 切片。"""
    start = min([d.lineno for d in fn.decorator_list] + [fn.lineno]) - 1
    # 往上带紧邻注释行（最多 3 行<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌，且必须是注释、不是别的语句）
    back = start
    while back - 1 >= 0 and lines[back - 1].strip().startswith("#") and start - back < 3:
        back -= 1
    return back, fn.end_lineno


def used_names(src):
    """模块里读到、但没在本模块定义的顶层名（用于补 import）。"""
    tree = ast.parse(src)
    defined, loaded = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name):
            (defined if isinstance(node.ctx, (ast.Store, ast.Del)) else loaded).add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
    return {n for n in loaded - defined if not hasattr(builtins, n)}


def project_modules():
    return {f[:-3] for f in os.listdir(ROOT) if f.endswith(".py")}


def shell_util_names():
    p = os.path.join(ROOT, "shell_util.py")
    if not os.path.isfile(p):
        return set()
    t = ast.parse(load(p))
    names = set()
    for node in t.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
    return names


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--class", dest="cls", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mixin", required=True)
    ap.add_argument("--match", required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    src_path = os.path.join(ROOT, args.src)
    src = load(src_path)
    lines = src.split("\n")
    tree = ast.parse(src)
    cls = find_class(tree, args.cls)
    if cls is None:
        print("找不到类 %s" % args.cls)
        return 2

    rx = re.compile(args.match)
    methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and rx.search(n.name)]
    if not methods:
        print("没匹配到方法")
        return 2

    spans = []
    for fn in methods:
        a, b = method_span(fn, lines)
        spans.append((a, b, fn.name))
    spans.sort()
    # 重叠检查（装饰器/注释上溯可能碰在一起）
    for (a1, b1, n1), (a2, b2, n2) in zip(spans, spans[1:]):
        if a2 < b1:
            print("块重叠：%s 与 %s，人工处理" % (n1, n2))
            return 2

    body = []
    for a, b, name in spans:
        body.append("\n".join(lines[a:b]).rstrip())
    moved_src_text = "\n\n".join(body) + "\n"

    before = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    after = before - {s[2] for s in spans}

    header = ('# -*- coding: utf-8 -*-\n'
              '"""%s —— 从 %s 的 %s 拆出（ast 精确切分）。\n\n'
              '方法：%s\n"""\n'
              'from __future__ import annotations\n\n') % (
        args.mixin, args.src, args.cls,
        "、".join(n for _, _, n in spans))

    # 试拼一次以满足 import 分析
    tmp = header + "class %s:\n" % args.mixin + "\n".join(
        "    " + ln if ln.strip() else ln for ln in moved_src_text.split("\n"))
    try:
        undefined = sorted(used_names(tmp))
    except SyntaxError as e:
        print("拼出来的模块语法有问题：", e)
        return 2

    proj, shared = project_modules(), shell_util_names()
    imports = []
    for n in undefined:
        if n in shared:
            continue
        if n in proj:
            imports.append("import %s" % n)
        elif n in sys.stdlib_module_names:
            imports.append("import %s" % n)
    shared_used = [n for n in undefined if n in shared]
    if shared_used:
        imports.append("from shell_util import %s" % ", ".join(sorted(shared_used)))
    unknown = [n for n in undefined if n not in proj and n not in shared]

    if imports:
        tmp = tmp.replace("from __future__ import annotations\n\n",
                          "from __future__ import annotations\n\n" + "\n".join(sorted(set(imports))) + "\n\n", 1)

    print("将搬走 %d 个方法、%d 行 → %s" % (len(spans), sum(b - a for a, b, _ in spans), args.out))
    print("  方法：", ", ".join(n for _, _, n in spans))
    print("  自动 import：", sorted(set(imports)) or "(无)")
    print("  未识别（需人工看）：", unknown or "(无)")
    print("  对账：原类 %d 个方法，搬走后剩 %d（差 %d）" % (len(before), len(after), len(spans)))

    if not args.write:
        print("\n（试运行，未写文件；加 --write 执行）")
        return 0

    # ① 写新模块
    out_path = os.path.join(ROOT, args.out)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(tmp.rstrip() + "\n")

    # ② 从原文件删（倒序）
    for a, b, _ in sorted(spans, key=lambda x: -x[0]):
        del lines[a:b]
    new_src = "\n".join(lines)

    # ③ 类定义加 mixin + 补 import
    t2 = ast.parse(new_src)
    c2 = find_class(t2, args.cls)
    cls_line = new_src.split("\n")[c2.lineno - 1]
    modname = args.out[:-3]
    if c2.bases:
        new_cls_line = cls_line.replace("(%s)" % ast.unparse(c2.bases[0]),
                                        "(%s, %s)" % (ast.unparse(c2.bases[0]), args.mixin), 1) \
            if len(c2.bases) == 1 else None
        if new_cls_line is None:
            print("类有多个基类，请手动加 %s" % args.mixin)
            return 2
    else:
        new_cls_line = cls_line.replace("class %s:" % args.cls,
                                        "class %s(%s):" % (args.cls, args.mixin), 1)
    src_lines = new_src.split("\n")
    src_lines[c2.lineno - 1] = new_cls_line
    # import 放在类定义之前
    imp = "from %s import %s" % (modname, args.mixin)
    if imp not in src_lines:
        src_lines.insert(c2.lineno - 1, imp + "\n")
    io.open(src_path, "w", encoding="utf-8", newline="\n").write("\n".join(src_lines))

    # ④ 对账
    t3 = ast.parse(io.open(src_path, encoding="utf-8").read())
    c3 = find_class(t3, args.cls)
    final = {n.name for n in c3.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = before - final - {s[2] for s in spans}
    print("写盘完成。对账：", "OK" if not missing else ("缺 %s" % sorted(missing)))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
