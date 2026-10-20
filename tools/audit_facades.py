# -*- coding: utf-8 -*-
"""门面台账（facade ledger）：拆块时留在仓库根的"转发函数"必须**只减不增**。

为什么要有它
------------
拆块时为了让调用点零改动，会把根目录的老模块降级成门面：

    def generate(prompt, **kw):          # image_gen.py
        return _svc().generate(prompt, **kw)

这是**过渡态**，不是终态。门面一多就变成"两套入口"：新人不知道改哪份，
旧的能跑、新的也能跑，于是两边慢慢分叉 —— 这正是屎山（ARCHITECTURE 十三节）的起点。

所以这里把门面数量变成棘轮：
  · 逐个统计每个"门面模块"里的纯转发函数（函数体只有一行 return，且调用了别的对象）；
  · 数量记进 `tools/facades_baseline.json`，**只许减**，涨了 exit 1；
  · 任何新出现的"疑似门面"文件（`def x(): return other.y(...)` 占比高）必须在基线里登记，
    否则算"偷偷新增门面"。

跑法：
    python tools/audit_facades.py            # 检查（CI / accept.py 用）
    python tools/audit_facades.py --write    # 首次建立基线 / 减少后下调（只能调小）
"""
import ast
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = os.path.join(HERE, "facades_baseline.json")

# 已经登记过的门面模块（历史欠债）。<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌新文件要进这里，必须先在基线里出现。
KNOWN = [
    "image_gen.py",
    "voice_engine.py",
    "codex_core.py",
]

# 这些名字不算"转发"（它们本来就是公共 API 的纯函数实现）
SKIP_FUNCS = {"main", "__init__"}


def _is_forwarder(node):
    """函数体只有一条 return，且 return 的是"调用别的对象上的东西"。"""
    if not isinstance(node, ast.FunctionDef):
        return False
    body = [n for n in node.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    value = body[0].value
    if isinstance(value, ast.Call):
        f = value.func
        # obj.name(...) 或 obj.attr.attr(...)
        return isinstance(f, ast.Attribute)
    if isinstance(value, ast.Attribute):
        # 属性转发：return BLOCK.PRESETS
        return True
    return False


def scan_file(path):
    """返回 (转发函数名列表, 总公共函数数, 是否有 __getattr__ 代理)。"""
    try:
        src = io.open(path, encoding="utf-8").read()
    except OSError:
        return [], 0, False
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [], 0, False
    fwd, total, has_getattr = [], 0, False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            if node.name in SKIP_FUNCS:
                continue
            total += 1
            if _is_forwarder(node):
                fwd.append(node.name)
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__":
            has_getattr = True
    return fwd, total, has_getattr


def collect():
    """扫仓库根的所有 .py，找出"疑似门面"。"""
    out = {}
    for fn in sorted(os.listdir(ROOT)):
        if not fn.endswith(".py"):
            continue
        path = os.path.join(ROOT, fn)
        if not os.path.isfile(path):
            continue
        fwd, total, has_getattr = scan_file(path)
        if not fwd and not has_getattr:
            continue
        # 判定：>=3 个转发函数，或（有 __getattr__ 且至少 1 个转发）
        looks_facade = len(fwd) >= 3 or (has_getattr and fwd)
        if looks_facade:
            out[fn] = dict(forwards=sorted(fwd), count=len(fwd), total=total,
                           getattr_proxy=has_getattr)
    return out


def check():
    live = collect()
    if not os.path.isfile(BASE):
        print("[FAIL] 没有基线（先跑 python tools/audit_facades.py --write）")
        return 1
    base = json.load(io.open(BASE, encoding="utf-8"))
    base_files = base.get("files", {})
    problems = []

    # ① 已登记的门面数量只许减
    for fn, meta in base_files.items():
        want = meta.get("count", 0)
        got = live.get(fn, {}).get("count", 0)
        if got > want:
            problems.append("%s 门面函数 %d > 基线 %d（新增了转发，门面不许变大）" % (fn, got, want))
        if fn not in live:
            problems.append("%s 在基线里但已不是门面（请下调基线：--write）" % fn)

    # ② 未登记的新门面
    for fn in live:
        if fn not in base_files:
            problems.append("%s 是新门面（%d 个转发函数），要进基线必须先说明理由" % (fn, live[fn]["count"]))

    # ③ 清单漂移：KNOWN 里的文件必须都在 live 里
    for fn in KNOWN:
        if fn not in live and fn not in base_files:
            problems.append("%s 在 KNOWN 里但既不在实况也不在基线" % fn)

    total_now = sum(m["count"] for m in live.values())
    total_base = sum(m.get("count", 0) for m in base_files.values())
    if total_now > total_base:
        problems.append("门面总数 %d > 基线 %d（只许减）" % (total_now, total_base))

    print("门面台账：%d 个门面模块 / %d 个转发函数（基线 %d）"
          % (len(live), total_now, total_base))
    for fn, meta in sorted(live.items()):
        print("  %-18s %2d 转发 / %2d 公共" % (fn, meta["count"], meta["total"]))
    if problems:
        print("\n[FAIL] %d 项：" % len(problems))
        for p in problems:
            print("   - " + p)
        return 1
    print("\n[ok] 门面只减不增")
    return 0


def write():
    live = collect()
    old = {}
    if os.path.isfile(BASE):
        old = json.load(io.open(BASE, encoding="utf-8")).get("files", {})
    files = {}
    for fn, meta in live.items():
        prev = old.get(fn, {}).get("count")
        if prev is not None and meta["count"] > prev:
            print("[拒绝] %s 转发函数 %d > 基线 %d：基线只许下调" % (fn, meta["count"], prev))
            return 1
        files[fn] = dict(count=meta["count"], total=meta["total"],
                         getattr_proxy=meta["getattr_proxy"],
                         reason="拆块时保留的转发门面，调用点零改动；清理顺序见 ARCHITECTURE 十")
    json.dump({"schema": 1, "note": "门面模块与转发函数数量，只许减少（tools/audit_facades.py）",
               "files": files},
              io.open(BASE, "w", encoding="utf-8", newline=""), ensure_ascii=False, indent=2)
    print("已写入 %s：%d 个门面 / %d 个转发"
          % (BASE, len(files), sum(v["count"] for v in files.values())))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(write() if "--write" in sys.argv else check())
