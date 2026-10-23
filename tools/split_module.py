# -*- coding: utf-8 -*-
"""split_module.py —— 把模块顶层的函数/常量成组搬到新模块（ast 精确切分）。

用途：net.py 这种"没有类、全是顶层函数"的服务端文件。
和 tools/split_ast.py 同一套思路，只是对象从"类里的方法"换成"模块顶层语句"：
  ① ast 拿精确行号区间（含装饰器）
  ② 原文切片搬到新模块
  ③ 原模块补 `from 新模块 import ...`（保持同名可见）
  ④ 符号对账：原顶层名字集合 == 留下的 + 搬走的

用法：
    python tools/split_module.py --src net.py --out net_transfer.py \
        --match "upload_any_gz|download_any_gz|_gzip_json_response|_store_upload|upload_finish|upload_plugin"
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


def top_nodes(tree):
    """顶层 def/class/赋值 → {名字: (起始行, 结束行)}，1-based。"""
    out = {}
    for node in tree.body:
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        for n in names:
            start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])
            out[n] = (start, node.end_lineno)
    return out


def used_names(src):
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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--match", required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    src_path = os.path.join(ROOT, args.src)
    src = io.open(src_path, encoding="utf-8").read()
    lines = src.split("\n")
    tops = top_nodes(ast.parse(src))

    rx = re.compile(args.match)
    picked = sorted(((tops[n][0], tops[n][1], n) for n in tops if rx.search(n)))
    if not picked:
        print("没匹配到顶层名字")
        return 2

    body = []
    for a, b, n in picked:
        body.append("\n".join(lines[a - 1:b]).rstrip())
    text = "\n\n".join(body) + "\n"

    header = ('# -*- coding: utf-8 -*-\n'
              '"""%s —— 从 %s 拆出的顶层块（ast 精确切分）。\n\n'
              '包含：%s\n"""\n'
              'from __future__ import annotations\n\n') % (
        os.path.basename(args.out)[:-3], args.src, "、".join(n for _, _, n in picked))

    try:
        undefined = sorted(used_names(header + text))
    except SyntaxError as e:
        print("拼出来语法有问题：", e)
        return 2

    proj = {f[:-3] for f in os.listdir(ROOT) if f.endswith(".py")}
    imports = ["import %s" % n for n in undefined if n in sys.stdlib_module_names]
    imports += ["import %s" % n for n in undefined if n in proj and n != os.path.basename(args.out)[:-3]]
    unknown = [n for n in undefined if n not in proj and n not in sys.stdlib_module_names]

    print("将搬走 %d 个顶层名字、%d 行" % (len(picked), sum(b - a + 1 for a, b, _ in picked)))
    print("  名字：", ", ".join(n for _, _, n in picked))
    print("  自动 import：", sorted(set(imports)) or "(无)")
    print("  未识别（需人工）：", unknown or "(无)")

    if not args.write:
        print("\n（试运行；加 --write 执行）")
        return 0

    header += "\n".join(sorted(set(imports))) + ("\n\n" if imports else "\n")
    io.open(os.path.join(ROOT, args.out), "w", encoding="utf-8", newline="\n").write(header + text)

    for a, b, _ in sorted(picked, key=lambda x: -x[0]):
        del lines[a - 1:b]

    modname = args.out[:-3]
    names = ", ".join(n for _, _, n in picked)
    insert_at = 0
    for i, l in enumerate(lines):
        if l.startswith(("import ", "from ")):
            insert_at = i
    lines.insert(insert_at + 1, "from %s import %s" % (modname, names))
    io.open(src_path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))

    after = set(top_nodes(ast.parse(io.open(src_path, encoding="utf-8").read())))
    lost = set(tops) - after - {n for _, _, n in picked}
    print("写盘完成。对账：", "OK" if not lost else ("缺 %s" % sorted(lost)))
    return 0 if not lost else 1


if __name__ == "__main__":
    sys.exit(main())
