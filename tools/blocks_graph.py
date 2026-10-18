# -*- coding: utf-8 -*-
"""blocks_graph.py —— 积木依赖图：出图 + 环检测 + 结构面指标

判断标准：ARCHITECTURE.md 十（积木协议）/ 十一（低耦六项指标）。
这个工具负责其中**结构面**的四项：
    ① 块之间 import = 0        （复用 audit_kernel_boundaries 的扫描，这里只做汇总）
    ③ 依赖成环 = 0             （本文件的核心：出图 + 环检测）
    ④ 单文件行数 ≤400（硬 800）（block.json 允许的文件清单逐个量）
    ⑤ 接口签名哈希             （给 accept.py 与快照比对，改了就是"改架构"）

用法：
    python tools/blocks_graph.py            # 人看：块的清单 + 依赖边 + 环 + 行数
    python tools/blocks_graph.py --json     # 机器可读
    python tools/blocks_graph.py --dot      # Graphviz DOT（贴进文档/看图）
"""

import ast
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BLOCKS_BASELINE = os.path.join(HERE, "block_interfaces.json")

SOFT_LINES = 400
HARD_LINES = 800
SKIP_DIRS = {"__pycache__", ".git"}


# ==================================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌============================== 发现块
def block_dirs(root=ROOT):
    """块目录：kernel/ 与 modules/<id>/（判定依据 = 有 block.json）"""
    out = []
    for base in (os.path.join(root, "kernel"),):
        if os.path.isfile(os.path.join(base, "block.json")):
            out.append(base)
    mroot = os.path.join(root, "modules")
    if os.path.isdir(mroot):
        for name in sorted(os.listdir(mroot)):
            d = os.path.join(mroot, name)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "block.json")):
                out.append(d)
    return out


def _read(path):
    with io.open(path, encoding="utf-8", errors="replace", newline="") as f:
        return f.read()


def _load_json(path):
    try:
        return json.loads(_read(path)), ""
    except Exception as e:
        return None, str(e)[:160]


def blocks(root=ROOT):
    """{block_id: {...}}；坏掉的块也列出来（errors 里说明），不能静默消失"""
    out = {}
    for d in block_dirs(root):
        bj, err = _load_json(os.path.join(d, "block.json"))
        if bj is None:
            out[os.path.basename(d)] = {"dir": d, "block": None, "errors": [err]}
            continue
        bid = str(bj.get("block") or os.path.basename(d))
        mf, merr = _load_json(os.path.join(d, "manifest.json"))
        out[bid] = {
            "dir": d,
            "block": bj,
            "errors": ([] if not merr else ["manifest.json 读不出来：%s" % merr]),
            "manifest": mf,
            "layer": str(bj.get("layer") or ""),
            "files": list(bj.get("files") or []),
        }
    return out


# ================================================================ 依赖图 / 环
def edges(root=ROOT):
    """依赖边：只认 manifest.requires.modules（声明出来的依赖才画进图）

    块之间的**import**必须为 0（audit 查），所以图里能出现的边只有声明式依赖 ——
    这也是"依赖关系看得见"的前提：看不见的依赖等于没有依赖管理。
    """
    out = []
    for bid, info in blocks(root).items():
        mf = info.get("manifest") or {}
        for dep in ((mf.get("requires") or {}).get("modules") or []):
            out.append({"from": bid, "to": str(dep), "kind": "requires"})
    return sorted(out, key=lambda e: (e["from"], e["to"]))


def cycles(root=ROOT):
    """找出所有环（DFS + 栈）。返回 [[a, b, a], …]"""
    graph = {}
    for e in edges(root):
        graph.setdefault(e["from"], []).append(e["to"])
    found, seen = [], set()

    def walk(node, stack):
        for nxt in graph.get(node, []):
            if nxt in stack:
                cyc = stack[stack.index(nxt):] + [nxt]
                key = tuple(sorted(set(cyc)))
                if key not in seen:
                    seen.add(key)
                    found.append(cyc)
                continue
            walk(nxt, stack + [nxt])

    for n in sorted(graph):
        walk(n, [n])
    return found


def missing_deps(root=ROOT):
    """声明了依赖但块不存在 → 也是坏图"""
    known = set(blocks(root))
    return [e for e in edges(root) if e["to"] not in known]


def dot(root=ROOT):
    lines = ["digraph blocks {", '  rankdir=LR;']
    for bid, info in sorted(blocks(root).items()):
        shape = "box" if info.get("layer") == "kernel" else "ellipse"
        lines.append('  "%s" [shape=%s];' % (bid, shape))
    for e in edges(root):
        lines.append('  "%s" -> "%s";' % (e["from"], e["to"]))
    lines.append("}")
    return "\n".join(lines)


# ================================================================ 接口签名
def _sig(fn):
    args = [a.arg for a in fn.args.args]
    if args and args[0] == "self":
        args = args[1:]
    if fn.args.vararg:
        args.append("*" + fn.args.vararg.arg)
    if fn.args.kwarg:
        args.append("**" + fn.args.kwarg.arg)
    return "%s(%s)" % (fn.name, ",".join(args))


def _class_methods(path, class_name):
    """从单文件里取某个类的 {方法名: 签名}（纯 AST，不执行代码）"""
    try:
        tree = ast.parse(_read(path))
    except SyntaxError:
        return {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {fn.name: _sig(fn) for fn in node.body
                    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {}


def interface_signatures(root=ROOT):
    """{block: {method: sig}} —— 声明的接口方法必须真在 impl 里找到

    block.json 的两种写法都认：
        "interface": {"class": "X", "impl": ["a.py", "b.py"], "methods": [...]}
        "interface": {"impls": [{"file": "a.py", "class": "X"}, …], "methods": [...]}
    第二种用于"接口实现分布在多文件/多类"（例如 client.py + transfer.py 的 mixin）。
    """
    out, problems = {}, {}
    for bid, info in blocks(root).items():
        bj = info.get("block") or {}
        itf = bj.get("interface") or {}
        impls = itf.get("impls") or []
        if not impls:
            cls = str(itf.get("class") or "")
            files = itf.get("impl") or []
            if isinstance(files, str):
                files = [files]
            impls = [{"file": f, "class": cls} for f in files]
        found = {}
        for item in impls:
            found.update(_class_methods(os.path.join(info["dir"], str(item.get("file") or "")),
                                        str(item.get("class") or "")))
        sigs, missing = {}, []
        for name in (itf.get("methods") or []):
            if name in found:
                sigs[name] = found[name]
            else:
                missing.append(name)
        out[bid] = sigs
        if missing:
            problems[bid] = "接口声明了但实现里没有：%s" % "、".join(missing)
        elif not impls:
            problems[bid] = "block.json 没写 interface.impls"
    return out, problems


def interface_hashes(root=ROOT):
    """{block: 16 位哈希}（方法名+参数名+顺序；改一个字符就变）"""
    sigs, problems = interface_signatures(root)
    out = {}
    for bid, sig in sigs.items():
        blob = "\n".join("%s" % sig[k] for k in sorted(sig)).encode("utf-8")
        out[bid] = hashlib.sha256(blob).hexdigest()[:16]
    return out, problems


# ================================================================ 行数预算
def line_report(root=ROOT):
    """逐文件量行数：>硬限 = error，>软限 = warn（ARCHITECTURE.md 九.1）"""
    rows = []
    for bid, info in blocks(root).items():
        for f in info.get("files") or []:
            p = os.path.join(info["dir"], f)
            if not os.path.isfile(p) or not f.endswith((".py", ".md", ".json")):
                continue
            n = len(_read(p).splitlines())
            level = "error" if n > HARD_LINES else ("warn" if n > SOFT_LINES else "ok")
            rows.append({"block": bid, "file": os.path.relpath(p, root).replace("\\", "/"),
                         "lines": n, "level": level})
    return sorted(rows, key=lambda r: -r["lines"])


# ================================================================ 汇总检查
def check(root=ROOT):
    """结构面体检：返回 {"problems": [...], ...}；problems 一条都不许有"""
    problems = []
    cyc = cycles(root)
    for c in cyc:
        problems.append("依赖成环：%s" % " → ".join(c))
    for e in missing_deps(root):
        problems.append("依赖的块不存在：%s → %s" % (e["from"], e["to"]))
    hashes, if_problems = interface_hashes(root)
    for bid, why in sorted(if_problems.items()):
        problems.append("%s：%s" % (bid, why))
    for row in line_report(root):
        if row["level"] == "error":
            problems.append("%s 有 %d 行（硬上限 %d）：块该拆了"
                            % (row["file"], row["lines"], HARD_LINES))
    return {"problems": problems, "cycles": cyc, "hashes": hashes,
            "lines": line_report(root), "edges": edges(root), "blocks": sorted(blocks(root))}


# ================================================================ 接口快照
def load_baseline(path=BLOCKS_BASELINE):
    data, err = _load_json(path)
    return (data or {}), err


def save_baseline(hashes, path=BLOCKS_BASELINE):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"schema": 1, "interface_hashes": hashes},
                           ensure_ascii=False, indent=2) + "\n")
    return path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    res = check()
    if "--dot" in argv:
        print(dot())
        return 0 if not res["problems"] else 1
    if "--json" in argv:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if not res["problems"] else 1
    print("=" * 66)
    print("积木依赖图 / 低耦结构面（判断标准：ARCHITECTURE.md 十、十一）")
    print("=" * 66)
    print("块：%s" % "、".join(res["blocks"]))
    print("\n依赖边（只认 manifest.requires.modules）：")
    if not res["edges"]:
        print("  （无 —— 三个块互不依赖）")
    for e in res["edges"]:
        print("  %s → %s" % (e["from"], e["to"]))
    print("\n环检测：%s" % ("无环" if not res["cycles"] else "发现 %d 个环！" % len(res["cycles"])))
    print("\n行数预算（软 %d / 硬 %d）：" % (SOFT_LINES, HARD_LINES))
    for row in res["lines"]:
        flag = {"ok": "  ", "warn": "⚠ ", "error": "✗ "}[row["level"]]
        print("  %s%-46s %4d 行" % (flag, row["file"], row["lines"]))
    print("\n接口签名哈希：")
    for bid, h in sorted(res["hashes"].items()):
        print("  %-12s %s" % (bid, h))
    if res["problems"]:
        print("\n问题：")
        for p in res["problems"]:
            print("  ✗ %s" % p)
        return 1
    print("\n结论：结构面 0 问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
