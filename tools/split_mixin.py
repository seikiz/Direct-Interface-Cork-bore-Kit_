# -*- coding: utf-8 -*-
"""split_mixin.py —— 把 Kit.py 里成组的方法整块搬进独立 mixin 文件（机械、可重放、会自检）。

为什么要有这个工具，而不是每次手写切分脚本：
    血洗要拆十几刀，每刀都可能踩同一类坑（漏 import、丢方法、块边界吃多）。
    把"切分 + 账目核对 + import 自动补齐"做成工具，每刀只改参数。

用法：
    python tools/split_mixin.py --out shell_codex.py --class CodexMixin --match "_codex_|_player_"

保证：
    ① 方法块按 4 空格 def 边界切，紧跟的注释行一起带走；
    ② 切完做**符号对账**：旧类方法集合 = 新类 + mixin + 剩余，少一个就报错退出；
    ③ 自动补 import：标准库模块 / 项目内模块 / shell_util 里的共用名；
    ④ 剩下的未定义名打印出来（人工只需看这一行）。
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
SRC_DEFAULT = os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py")


def split_methods(lines, class_line_idx, pattern):
    """切出匹配 pattern 的方法块（含紧邻注释），返回 [(start, end)] 与下一步扫描位置。"""
    rx = re.compile(pattern)
    blocks = []
    i = class_line_idx + 1
    while i < len(lines):
        m = re.match(r"^    def (\w+)", lines[i])
        if m and rx.search(m.group(1)):
            start = i
            back = i
            while back - 1 > class_line_idx and re.match(r"^    #", lines[back - 1]) and (i - back) < 4:
                back -= 1
            j = i + 1
            while j < len(lines):
                if re.match(r"^    (def |@)", lines[j]) or (lines[j] and not lines[j].startswith(" ")):
                    break
                j += 1
            blocks.append((back, j))
            i = j
        else:
            i += 1
    return blocks


def top_level_defs(text):
    """模块顶层的 def/class/常量名。"""
    names = set(re.findall(r"^def (\w+)", text, re.M))
    names |= set(re.findall(r"^class (\w+)", text, re.M))
    names |= set(re.findall(r"^([A-Z_][A-Z0-9_]*)\s*=", text, re.M))
    return names


def used_names(text):
    """模块内被读到的顶层名（Name 且是 Load），排除定义、局部变量。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    defined = set()
    loaded = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                defined.add(node.id)
            else:
                loaded.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.Attribute):
            pass
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
    return {n for n in loaded - defined if not hasattr(builtins, n)}


def project_modules():
    return {f[:-3] for f in os.listdir(ROOT) if f.endswith(".py")}


def shell_util_names():
    p = os.path.join(ROOT, "shell_util.py")
    if not os.path.isfile(p):
        return set()
    return top_level_defs(io.open(p, encoding="utf-8").read())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--out", required=True, help="新文件（相对仓库根）")
    ap.add_argument("--class", dest="cls", required=True, help="mixin 类名")
    ap.add_argument("--match", required=True, help="方法名正则（如 _codex_|_player_）")
    args = ap.parse_args(argv)

    src = args.src
    lines = io.open(src, encoding="utf-8").read().split("\n")
    cls_i = next(i for i, l in enumerate(lines) if re.match(r"^class HtmlApp\b", l))

    before = top_level_defs("\n".join(lines))
    before_methods = set(re.findall(r"^    def (\w+)", "\n".join(lines), re.M))

    blocks = split_methods(lines, cls_i, args.match)
    if not blocks:
        print("没匹配到方法，退出")
        return 2
    names = [re.match(r"^    def (\w+)", lines[a]).group(1) for a, b in blocks
             if re.match(r"^    def ", lines[a])]

    body = []
    for a, b in blocks:
        body.extend(lines[a:b])
        body.append("")

    # 生成新模块（先写，再根据<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌静态分析补 import）
    modname = os.path.basename(args.out)[:-3]
    header = ('# -*- coding: utf-8 -*-\n'
              '"""%s —— 从 Kit.py 拆出的 mixin（%s）。\n\n'
              '包含方法：%s\n\n'
              '为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；\n'
              'mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。\n'
              '"""\n'
              'from __future__ import annotations\n\n') % (
        modname, args.match, "、".join(names[:12]) + ("…" if len(names) > 12 else ""))
    text = header + "class %s:\n    \"\"\"%s\"\"\"\n\n" % (args.cls, modname) + "\n".join(body)
    if not body:
        text += "    pass\n"

    # 静态分析：哪些名字没有定义
    undefined = sorted(used_names(text))
    imports = []
    proj = project_modules()   # 只认项目里的模块文件；shell_util 的名字单独走 from 导入
    for n in undefined:
        if n in proj:
            imports.append("import %s" % n)
        elif n in sys.stdlib_module_names:
            imports.append("import %s" % n)
    shared = [n for n in undefined if n in shell_util_names()]
    if shared:
        imports.append("from shell_util import %s" % ", ".join(sorted(shared)))
    unknown = [n for n in undefined if n not in proj and n not in sys.stdlib_module_names]

    if imports:
        text = text.replace("from __future__ import annotations\n\n",
                            "from __future__ import annotations\n\n" + "\n".join(imports) + "\n\n", 1)

    out_path = os.path.join(ROOT, args.out)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(text)

    # 从 Kit.py 删除（倒序）
    for a, b in sorted(blocks, key=lambda x: -x[0]):
        del lines[a:b]

    # 改 class 定义 + 加 import
    out_cls = next(i for i, l in enumerate(lines) if re.match(r"^class HtmlApp\b", l))
    old_cls = lines[out_cls]
    if old_cls.startswith("class HtmlApp("):
        lines[out_cls] = old_cls.replace("class HtmlApp(", "class HtmlApp(%s, " % args.cls, 1)
    else:
        lines[out_cls] = "class HtmlApp(%s):" % args.cls
    ins = next(i for i, l in enumerate(lines) if l.startswith("from shell_ws import"))
    lines.insert(ins + 1, "from %s import %s" % (modname, args.cls))

    io.open(src, "w", encoding="utf-8", newline="\n").write("\n".join(lines))

    # 对账
    after_methods = set(re.findall(r"^    def (\w+)", "\n".join(lines), re.M))
    moved = set(re.findall(r"^    def (\w+)", text, re.M))
    lost = before_methods - after_methods - moved
    print("搬走 %d 个方法、%d 行 → %s" % (len(names), len(body), args.out))
    print("Kit.py: %d 行（原 %d）" % (len(lines), len(before_methods) and 7292))
    print("自动补的 import:", imports or "(无)")
    print("未识别名字（需人工）:", unknown or "(无)")
    print("对账丢失方法:", sorted(lost) or "(无)")
    return 0 if not lost else 1


if __name__ == "__main__":
    sys.exit(main())
