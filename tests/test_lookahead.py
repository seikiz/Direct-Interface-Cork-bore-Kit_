# -*- coding: utf-8 -*-
"""
前瞻展开测试。

核心要证的只有一件事：
    **在分叉点处分不开的两种情况，往前生成两轮之后能分开，而且机制会挑对。**

测试用【假模型】——确定性的、可控的，不花一个 token。
这样机制对不对可以反复验，不用等真实 API。

跑法：utau_env\\Scripts\\python.exe tests\\test_lookahead.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import lookahead as la           # noqa: E402
import tree_weight as tw         # noqa: E402

PASS = 0
FAIL = 0

KEYS = ["册子", "扉页", "铅笔", "笔迹", "字", "第三排", "原主人", "封面", "墨水"]
CASE = "旧书店 雨夜 台灯 阿岚 你 皮面开裂的册子 柜台 桌子 雨 册子是你上次问的那本 扉页上有一行铅笔字"

BASE = [{"role": "system", "content": "你是阿岚。"},
        {"role": "user", "content": "那本册子呢？"}]

# 两条路的剧本：第一轮【完<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌全一样】（这是难点所在）
SAME_FIRST = "（她沉默了一会儿，给你倒了杯茶）"
GOOD_TAIL = [
    "（她按住封面）先别问是谁写的，你先看这两个字。",
    "（台灯挪近）铅笔字被水泡过一半，但第三排还在。",
]
DRIFT_TAIL = [
    "（她望向窗外）有些事你以为忘了，其实只是没下雨。",
    "（她低声）人这一辈子就是等一场雨。",
]
CONFAB_TAIL = [
    "（她忽然笑了）我小时候院子里有棵石榴树，我母亲一颗颗剥给我吃。",
    "（她望向窗外）雨停了街上的人就都出来了。",
]


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def make_model(scripts, depth):
    """假模型：按 expand 的【顺序】访问吐词。

    注意：expand 是一条分支跑完再跑下一条（不是交错），所以这里按
    "每 depth 次调用换一条分支"来切。之前写成按调用序号交错，
    结果每条的 turns 都被错位的剧本污染了 —— 是测试自己的错。
    """
    state = {"n": 0}

    def fn(messages):
        i = state["n"]
        state["n"] += 1
        b = i // max(1, depth)
        d = i % max(1, depth)
        seq = scripts[b] if b < len(scripts) else scripts[-1]
        return seq[d] if d < len(seq) else ""
    return fn


# ============================================================
def test_score_branch():
    print("\n== 1. 分支打分 ==")
    good = la.score_branch([SAME_FIRST] + GOOD_TAIL, KEYS, CASE)
    drift = la.score_branch([SAME_FIRST] + DRIFT_TAIL, KEYS, CASE)
    conf = la.score_branch([SAME_FIRST] + CONFAB_TAIL, KEYS, CASE)
    print("        回到目标 %s" % good)
    print("        漂走     %s" % drift)
    print("        编造     %s" % conf)
    check("回目标的得分最高", good["score"] > drift["score"],
          "%s vs %s" % (good["score"], drift["score"]))
    check("编造被扣到最低", conf["score"] < good["score"],
          "%s vs %s" % (conf["score"], good["score"]))
    check("编造计数正确", conf["confab"] >= 1, str(conf))
    check("漂走的端点覆盖为 0", drift["end_cov"] == 0.0, str(drift))
    check("端点权重高于均值（end_cov 单独列出）",
          "end_cov" in good and "coverage" in good)


def test_fork_is_indistinguishable():
    print("\n== 2. 前提：第一轮两边一模一样（这正是难点）==")
    c = [tw.anchor_coverage(SAME_FIRST, KEYS)] * 2
    check("同一个第一轮，覆盖一样", c[0] == c[1] == 0.0, str(c))
    # 只看第一轮，两条路的分支得分应当相同
    b_good = la.score_branch([SAME_FIRST], KEYS, CASE)
    b_drift = la.score_branch([SAME_FIRST], KEYS, CASE)
    check("只看第一轮 → 分不出（分数相同）",
          b_good["score"] == b_drift["score"], "%s vs %s" % (b_good, b_drift))
    # 往前两轮 → 分得出
    f_good = la.score_branch([SAME_FIRST] + GOOD_TAIL, KEYS, CASE)
    f_drift = la.score_branch([SAME_FIRST] + DRIFT_TAIL, KEYS, CASE)
    check("往前两轮 → 分得出",
          f_good["score"] - f_drift["score"] > 0.2,
          "%s vs %s" % (f_good["score"], f_drift["score"]))


def test_rubric_cannot_override_margin():
    """性质测试：rubric 只能裁决，不能覆盖【够大】的实质分差。

    这是从实测（_tree_data6.py）反推出来的一条硬性质：
    如果 rubric 能在启发式已经拉开分差时翻盘，那么模型判定只要有一半判错，
    树搜索就会主动把好分支扔掉 —— 实测捕获率从 62% 掉到 35%。

    阈值本身是算出来的，不是拍的：
        rubric 取值范围 0~1，评审判反时最多造成 KR 分的落差，
        所以"可翻盘的最小分差" = KR。
    这条断言的作用是：以后谁把 rubric 权重调大，可翻盘区就变宽，测试会红。
    """
    print("\n== 3b. rubric 不能覆盖实质分差（实测反推出的安全性质）==")
    import inspect
    import re as _re
    src = inspect.getsource(la.score_branch)
    m = _re.search(r"score = ([\d.]+) \* \(0\.4 \* mid \+ 0\.6 \* end_cov\) \+ ([\d.]+) \* float\(rubric\)", src)
    check("能从源码里读出 rubric 系数（避免测试跟着实现一起漂）",
          m is not None, src.replace("\n", " ")[:120])
    kr = float(m.group(2)) if m else 0.30
    flip_min = kr           # 评审完全判反时能被翻掉的最小分差
    print("        从源码读出 KR=%.2f → 可翻盘的最小分差 = %.2f" % (kr, flip_min))

    # 用一条大分差：一条在推进 + 一条编造，差 0.5
    good = [SAME_FIRST, "（她把册子推过来）你看扉页这两个字。"]
    bad = [SAME_FIRST, "（她笑了）我小时候院子里有棵石榴树。"]
    gap = (la.score_branch(good, KEYS, CASE)["score"]
           - la.score_branch(bad, KEYS, CASE)["score"])
    check("这条分差确实大过可翻盘阈值", abs(gap) > flip_min,
          "分差=%.4f 阈值=%.2f" % (gap, flip_min))
    # 最坏情况：评审把两者完全判反
    s_good = la.score_branch(good, KEYS, CASE, rubric=0.0)["score"]
    s_bad = la.score_branch(bad, KEYS, CASE, rubric=1.0)["score"]
    check("评审完全判反，也翻不过来", s_good > s_bad,
          "好=%.4f 坏=%.4f" % (s_good, s_bad))

    # 反过来的边界：分差为零时，rubric 必须能说话，否则它就白付了成本
    tie_a = la.score_branch([SAME_FIRST], KEYS, CASE, rubric=0.0)["score"]
    tie_b = la.score_branch([SAME_FIRST], KEYS, CASE, rubric=1.0)["score"]
    check("分差为零时 rubric 能裁决", tie_b > tie_a,
          "%.4f vs %.4f" % (tie_a, tie_b))
    # 权重必须是【小量】：rubric 单独不足以压过一整个 base 的量级
    check("rubric 权重是小量而非主导", kr <= 0.5, "KR=%.2f" % kr)
    # 编造这类硬故障必须压过满分 rubric（否则前瞻会挑编造）
    conf = la.score_branch([SAME_FIRST] + CONFAB_TAIL, KEYS, CASE, rubric=1.0)
    check("编造仍然压得住满分 rubric", conf["score"] < 0,
          str(conf["score"]))


def test_picks_the_right_branch():
    print("\n== 3. 机制要挑对分支 ==")
    # 分支0 漂走，分支1 回到目标；两者第一轮相同
    fn = make_model([[SAME_FIRST] + DRIFT_TAIL, [SAME_FIRST] + GOOD_TAIL], 3)
    r = la.expand(fn, BASE, branches=2, depth=3, keys=KEYS, case_text=CASE)
    print(la.describe(r))
    check("前瞻成功", r.get("ok") is True, str(r.get("err")))
    check("挑中了回到目标的那条", r.get("best_i") == 1, "挑中了 %s" % r.get("best_i"))
    check("交给用户的是第一轮（两条相同的那句）",
          r.get("first") == SAME_FIRST, repr(r.get("first")))
    check("调用次数 = 分支 × 深度", r.get("calls") == 6, str(r.get("calls")))

    # 反过来：好分支在前，也要挑对
    fn2 = make_model([[SAME_FIRST] + GOOD_TAIL, [SAME_FIRST] + DRIFT_TAIL], 3)
    r2 = la.expand(fn2, BASE, branches=2, depth=3, keys=KEYS, case_text=CASE)
    check("反过来也能挑对", r2.get("best_i") == 0, "挑中了 %s" % r2.get("best_i"))


def test_confabulation_loses():
    print("\n== 4. 编造那条必须输 ==")
    fn = make_model([[SAME_FIRST] + CONFAB_TAIL, [SAME_FIRST] + GOOD_TAIL], 3)
    r = la.expand(fn, BASE, branches=2, depth=3, keys=KEYS, case_text=CASE)
    print(la.describe(r))
    check("编造那条没被选中", r.get("best_i") == 1, "挑中了 %s" % r.get("best_i"))
    b0 = [x for x in r["branches"] if x["i"] == 0][0]
    check("编造那条被记了编造", b0["confab"] >= 1, str(b0))


def test_cost_cap():
    print("\n== 5. 成本硬上限（配置写错也不能把额度烧光）==")
    fn = make_model([[SAME_FIRST] + GOOD_TAIL, [SAME_FIRST] + DRIFT_TAIL], 3)
    r = la.expand(fn, BASE, branches=5, depth=5, keys=KEYS, case_text=CASE, cap=4)
    print(la.describe(r))
    check("调用次数不超过上限", r.get("calls", 99) <= 4, str(r.get("calls")))
    check("标记了被截断", r.get("capped") is True)
    check("仍然给出了结果", r.get("ok") is True and bool(r.get("first")))


def test_no_keys_refuses():
    print("\n== 6. 没设目标就拒绝前瞻（不能变成瞎挑）==")
    fn = make_model([[SAME_FIRST], [SAME_FIRST]], 2)
    r = la.expand(fn, BASE, branches=2, depth=2, keys=[], case_text=CASE)
    check("拒绝执行", r.get("ok") is False, str(r))
    check("原因说明是缺关键词", "关键词" in (r.get("err") or ""), str(r.get("err")))


def test_partial_failure_still_counts():
    print("\n== 7. 半条分支也要入账（探到一半失败本身是信息）==")
    calls = {"n": 0}

    def flaky(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return SAME_FIRST
        raise RuntimeError("网络断了")

    r = la.expand(flaky, BASE, branches=1, depth=3, keys=KEYS, case_text=CASE)
    check("没有整体崩", r.get("ok") is True, str(r))
    check("记下了错误", r["branches"] and r["branches"][0].get("error"),
          str(r.get("branches")))
    check("已探到的轮次仍被计入", r["branches"][0]["n_turns"] == 1,
          str(r["branches"][0].get("n_turns")))
    # 返回的分支摘要【不】带上探过的原文 —— 那既占体积，也不是调用方需要的
    check("分支摘要里不返回原文", "turns" not in r["branches"][0],
          str(list(r["branches"][0].keys())))
    check("胜出内容是第一轮", r.get("first") == SAME_FIRST, repr(r.get("first")))


def test_empty_reply_stops():
    print("\n== 8. 模型吐空 → 停止该分支，不空转 ==")
    def empty(messages):
        return "   "
    r = la.expand(empty, BASE, branches=2, depth=3, keys=KEYS, case_text=CASE)
    check("没有可用分支 → 明确失败", r.get("ok") is False, str(r))
    check("原因说明没有产出", "没有产出" in (r.get("err") or ""), str(r.get("err")))


def test_no_base_messages():
    print("\n== 9. 没有载荷时不硬跑 ==")
    r = la.expand(lambda m: "x", [], branches=2, depth=2, keys=KEYS)
    check("明确失败", r.get("ok") is False and "载荷" in (r.get("err") or ""), str(r))


if __name__ == "__main__":
    print("=" * 62)
    print("前瞻展开测试（假模型，不花 token）")
    print("=" * 62)
    test_score_branch()
    test_fork_is_indistinguishable()
    test_picks_the_right_branch()
    test_rubric_cannot_override_margin()
    test_confabulation_loses()
    test_cost_cap()
    test_no_keys_refuses()
    test_partial_failure_still_counts()
    test_empty_reply_stops()
    test_no_base_messages()
    print("\n" + "=" * 62)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)

