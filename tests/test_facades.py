# -*- coding: utf-8 -*-
"""门面台账测试：拆块留下的"根目录转发函数"只许减少，不许新增。

背景（ARCHITECTURE 十/十三）：
拆块时为了让调用点零改动，会把根目录老模块降级成门面（`def generate(...): return _svc().generate(...)`）。
这是**过渡态**。门面一多就变成两套入口：新人不知道改哪份，两份慢慢分叉——那正是屎山的起点。

闸门在 `tools/audit_facades.py`（棘轮），这里守它的行为：
  ① 判定器认得出"纯转发"（单行 return，且调的是别的对象）与**不是**转发（自己算的）；
  ② 真实仓库当前数量 ≤ 基线；
  ③ 模拟"新增一个转发" → 必须判红（否则闸门是装饰）；
  ④ 模拟"减少到 0" → 允许（棘轮只拦增长）；
  ⑤ 基线文件本身存在、schema 正确、登记的每个文件都真的还在仓库里。

跑法：python tests\\test_facades.py
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import audit_facades as AF   # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def ast_fn(src):
    import ast
    return ast.parse(src).body[0]


def main():
    print("=" * 62)
    print(u"门面台账：根目录转发函数只许减少")
    print("=" * 62)

    print(u"\n== ① 判定器：什么算'纯转发' ==")
    check(u"obj.name(...) 算转发",
          AF._is_forwarder(ast_fn("def f(a):\n    return _svc().name(a)\n")))
    check(u"return BLOCK.CONST 属性转发算转发",
          AF._is_forwarder(ast_fn("def f():\n    return BLOCK.CONST\n")))
    check(u"自己算的不算转发",
          not AF._is_forwarder(ast_fn("def f(a):\n    return a + 1\n")))
    check(u"两行体（先算再返回）不算转发",
          not AF._is_forwarder(ast_fn("def f(a):\n    x = a + 1\n    return x\n")))
    check(u"带 docstring 的单行 return 仍算转发",
          AF._is_forwarder(ast_fn('def f(a):\n    """说明"""\n    return _svc().name(a)\n')))

    print(u"\n== ② 基线文件 ==")
    check(u"基线存在", os.path.isfile(AF.BASE), AF.BASE)
    base = json.load(io.open(AF.BASE, encoding="utf-8")) if os.path.isfile(AF.BASE) else {}
    files = base.get("files", {})
    check(u"基线有 schema 与 files", base.get("schema") == 1 and isinstance(files, dict))
    check(u"基线登记了至少 3 个门面（image_gen/voice_engine/codex_core）", len(files) >= 3, str(list(files)))
    for fn in AF.KNOWN:
        check(u"基线与实况都包含 %s" % fn, fn in files and os.path.isfile(os.path.join(ROOT, fn)))

    print(u"\n== ③ 当前仓库：数量不超基线 ==")
    live = AF.collect()
    total_now = sum(m["count"] for m in live.values())
    total_base = sum(m.get("count", 0) for m in files.values())
    check(u"门面总数 %d ≤ 基线 %d" % (total_now, total_base), total_now <= total_base)
    check(u"check() 返回 0（绿）", AF.check() == 0)

    print(u"\n== ④ 反向验证：新增转发必须判红 ==")
    real_collect = AF.collect
    try:
        # 在原实况上给 codex_<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌core 多塞一个转发函数
        fake = {k: dict(v) for k, v in live.items()}
        if "codex_core.py" in fake:
            fake["codex_core.py"]["count"] += 1
        else:
            fake["codex_core.py"] = dict(count=1, total=1, getattr_proxy=False, forwards=["x"])
        AF.collect = lambda: fake
        rc = AF.check()
        check(u"多了 1 个转发 → check() 返回 1", rc == 1, u"rc=%d" % rc)
        check(u"并且总数判定也变红", sum(m["count"] for m in fake.values()) > total_base)
    finally:
        AF.collect = real_collect

    print(u"\n== ⑤ 债务必须显式回收：门面清零后基线也要下调 ==")
    # 这条语义是**故意的**：门面没了但基线还留着 → 仍然红，提示你用 --write 下调。
    # 棘轮不只拦增长，也逼你把"已还清的债"从台账里划掉，否则台账长期虚报。
    try:
        AF.collect = lambda: {}
        rc = AF.check()
        check(u"全部清零但基线未下调 → check() 返回 1（逼你 --write 回收）", rc == 1, u"rc=%d" % rc)
    finally:
        AF.collect = real_collect

    print(u"\n== ⑥ 门面文件本身不许变大 ==")
    for fn in ("image_gen.py", "voice_engine.py", "codex_core.py"):
        p = os.path.join(ROOT, fn)
        if not os.path.isfile(p):
            continue
        n = len(io.open(p, encoding="utf-8").read().splitlines())
        check(u"%s %d 行 ≤ 400（门面只该是一层薄转调）" % (fn, n), n <= 400, u"%d 行" % n)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("FACADES_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
