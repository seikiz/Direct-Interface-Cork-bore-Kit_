# -*- coding: utf-8 -*-
"""
价值声明（rubric）+ 模型判定 测试。

这一块是"便宜版的 PRM"：作者声明标准，模型按标准判一次。
最不能错的两件事：
  ① **模型不按格式回是常态** —— 抠不出分就必须退回启发式，不能瞎猜、不能崩
  ② **判定失败不能打断生成** —— 它是锦上添花，不是关键路径

跑法：utau_env\\Scripts\\python.exe tests\\test_rubric.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import lookahead as la     # noqa: E402
import rubric as rb        # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


CRIT = ["每轮必须推进一点", "不解释来历", "不写成说明文"]


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_normalize():
    print("\n== 1. 标准声明：洗干净 ==")
    check("去编号", rb.normalize("1. 甲\n2、乙\n3）丙") == ["甲", "乙", "丙"],
          str(rb.normalize("1. 甲\n2、乙\n3）丙")))
    check("去重", rb.normalize("甲\n甲\n乙") == ["甲", "乙"])
    check("去空行", rb.normalize("甲\n\n\n乙") == ["甲", "乙"])
    check("分号也能分", rb.normalize("甲；乙") == ["甲", "乙"])
    check("字符串输入不炸", isinstance(rb.normalize("甲"), list))
    check("空输入", rb.normalize("") == [] and rb.normalize(None) == [])
    many = "\n".join("标准%d" % i for i in range(20))
    check("限量（写太多模型会平均化）", len(rb.normalize(many)) == rb.MAX_CRITERIA,
          str(len(rb.normalize(many))))


def test_build_prompt():
    print("\n== 2. 判定提示词 ==")
    ctx = [{"role": "system", "content": "人设"},
           {"role": "user", "content": "那本册子呢？"},
           {"role": "assistant", "content": "（推过去）你看。"}]
    msgs = rb.build_prompt(CRIT, ctx, "待评内容")
    check("两条 message", len(msgs) == 2, str(len(msgs)))
    check("system 里列了全部标准",
          all(c in msgs[0]["content"] for c in CRIT))
    check("system 里要求 JSON 输出", "scores" in msgs[0]["content"])
    check("明确说了别按文笔判", "不按感觉判" in msgs[0]["content"])
    check("user 里带上了前文", "那本册子呢" in msgs[1]["content"])
    check("user 里带上了待评内容", "待评内容" in msgs[1]["content"])
    check("前文里不含 system 消息",
          "人设" not in msgs[1]["content"], str(msgs[1]["content"][:60]))


def test_parse_tolerance():
    print("\n== 3. 解析容错（模型不按格式回是常态）==")
    n = 3
    good = '{"scores":[5,4,3],"note":"ok"}'
    v = rb.parse_verdict(good, n)
    check("标准 JSON", v and v["scores"] == [5, 4, 3], str(v))
    check("带 note", v and v["note"] == "ok")

    wrapped = '好的，我的评分是 {"scores": [4,4,2]} 完毕'
    v2 = rb.parse_verdict(wrapped, n)
    check("JSON 包在废话里", v2 and v2["scores"] == [4, 4, 2], str(v2))

    v3 = rb.parse_verdict("scores: [5, 3, 1]", n)
    check("没有花括号但有关键字", v3 and v3["scores"] == [5, 3, 1], str(v3))

    v4 = rb.parse_verdict("评分：4 3 2", n)
    check("纯数字行兜底", v4 and v4["scores"] == [4, 3, 2], str(v4))

    check("完全不给分 → None（宁可退回启发式）",
          rb.parse_verdict("我不会打分", n) is None)
    check("空 → None", rb.parse_verdict("", n) is None)
    check("标准 0 条 → None", rb.parse_verdict(good, 0) is None)

    v5 = rb.parse_verdict('{"scores":[9,-3,4]}', n)
    check("越界被夹到 0~5", v5 and v5["scores"] == [5, 0, 4], str(v5))

    v6 = rb.parse_verdict('{"scores":["3","4","5"]}', n)
    check("字符串数字也认", v6 and v6["scores"] == [3, 4, 5], str(v6))

    check("分数不够时返回 None（不能少判一项）",
          rb.parse_verdict('{"scores":[5]}', n) is None)


def test_aggregate():
    print("\n== 4. 聚合成 0~1 ==")
    check("[5,5,5] → 1.0", rb.aggregate({"scores": [5, 5, 5]}, 3) == 1.0)
    check("[0,0,0] → 0.0", rb.aggregate({"scores": [0, 0, 0]}, 3) == 0.0)
    check("[5,3,1] → 0.6", rb.aggregate({"scores": [5, 3, 1]}, 3) == 0.6)
    check("None → None", rb.aggregate(None, 3) is None)


def test_judge_never_raises():
    print("\n== 5. 判定绝不打断生成（它是锦上添花，不是关键路径）==")
    ok = rb.judge(lambda m: '{"scores":[4,4,4]}', CRIT, [], "内容")
    check("正常判定", ok["score"] is not None and ok["error"] is None, str(ok))

    def boom(m):
        raise RuntimeError("网络断了")
    bad = rb.judge(boom, CRIT, [], "内容")
    check("模型调用抛异常 → 退回 None", bad["score"] is None, str(bad))
    check("记下了原因", "网络断了" in (bad["error"] or ""), str(bad["error"]))

    junk = rb.judge(lambda m: "我不想评分", CRIT, [], "内容")
    check("模型乱回 → 退回 None", junk["score"] is None, str(junk))
    check("说明了是格式问题", "格式" in (junk["error"] or ""), str(junk["error"]))

    check("没有标准 → 不判", rb.judge(lambda m: "x", [], [], "内容")["score"] is None)
    check("没有内容 → 不判", rb.judge(lambda m: "x", CRIT, [], "")["score"] is None)


def test_judge_candidates_cap():
    print("\n== 6. 批量判定有硬上限（否则前瞻会变烧钱机器）==")
    calls = {"n": 0}

    def counted(m):
        calls["n"] += 1
        return '{"scores":[3,3,3]}'
    out = rb.judge_candidates(counted, CRIT, [], ["a", "b", "c", "d", "e"], cap=3)
    check("只判了上限条数", calls["n"] == 3, str(calls["n"]))
    check("返回条数完整", len(out) == 5, str(len(out)))
    check("超限的被标记而不是静默丢弃",
          out[3]["score"] is None and "上限" in (out[3]["error"] or ""), str(out[3]))


# ============================================================
def test_lookahead_uses_rubric():
    print("\n== 7. rubric 接进前瞻：只判端点，且只做裁决不做覆盖 ==")
    SAME = "（她沉默了一会儿，给你倒了杯茶）"
    A = [SAME, "（她按住封面）先看扉页那两个字。"]
    B = [SAME, "（她望向窗外）有些事你以为忘了。"]
    # 案卷要给够 —— 给太薄的话，正常内容会被当成编造。
    # （"那两个字"的头名词"字"必须在案卷里，否则 indict 会误判。）
    KEYS = ["册子", "扉页", "字"]
    CASE = "册子 扉页 铅笔字 封面"
    # 没有 rubric：靠启发式，A 胜（它碰了关键词）
    sA = la.score_branch(A, KEYS, CASE)
    sB = la.score_branch(B, KEYS, CASE)
    check("无 rubric 时 A 胜", sA["score"] > sB["score"], "%s vs %s" % (sA, sB))
    check("无 rubric 时 rubric 字段是 None", sA["rubric"] is None)
    # 有 rubric，且评审把两者判反了（B=0.9, A=0.1，最大反向信号）：
    # 这【不应该】翻盘 —— 启发式已经给出 0.36 的实质分差，rubric 不该压过它。
    # （原来这里期望"能翻盘"，那正是被实测否掉的行为：kr/ka=1.25 时
    #   一个 q=0.5 的瞎判就能把好分支扔掉，捕获率 62%→35%。见 _tree_data6.py）
    sA2 = la.score_branch(A, KEYS, CASE, rubric=0.1)
    sB2 = la.score_branch(B, KEYS, CASE, rubric=0.9)
    check("rubric 翻不掉实质分差（A 仍然胜）", sA2["score"] > sB2["score"],
          "%s vs %s" % (sA2, sB2))
    check("rubric 被记进结果", sB2["rubric"] == 0.9, str(sB2))
    # 但分差为零时，rubric 就是唯一的裁决者 —— 这才是它该起的作用
    sE1 = la.score_branch([SAME], KEYS, CASE, rubric=0.1)
    sE2 = la.score_branch([SAME], KEYS, CASE, rubric=0.9)
    check("平手时 rubric 能裁决（后者胜）", sE2["score"] > sE1["score"],
          "%s vs %s" % (sE1, sE2))
    check("平手时无 rubric 则完全等价",
          la.score_branch([SAME], KEYS, CASE)["score"]
          == la.score_branch([SAME], KEYS, CASE)["score"])
    # 编造依然能压过 rubric —— 硬故障优先
    sC = la.score_branch([SAME, "（她笑了）我小时候院子里有棵石榴树。"],
                         KEYS, CASE, rubric=1.0)
    check("编造仍然压得住 rubric", sC["score"] < sB2["score"],
          "%s vs %s" % (sC, sB2))

    # expand 里 judge_fn 只被调 K 次（不是 K×D）
    st = {"n": 0}
    # 注意 A/B 本身就以 SAME 开头（那是"分叉点两条一样"的设定），
    # 不能再拼一个 SAME 上去 —— 叠了的话深度 2 取到的两轮都是 SAME（踩过一次）。
    SCRIPTS = [B, A]
    calls = {"n": 0}

    def fake(m):
        i = calls["n"]
        calls["n"] += 1
        b, d = i // 2, i % 2
        return SCRIPTS[b][d] if d < len(SCRIPTS[b]) else ""

    judged = []

    def judge(t):
        judged.append(t)
        return 0.2 if "窗外" in t else 0.9
    r = la.expand(fake, [{"role": "user", "content": "x"}], branches=2, depth=2,
                  keys=KEYS, case_text=CASE, judge_fn=judge)
    check("前瞻成功", r.get("ok") is True, str(r.get("err")))
    check("judge 只被调了 2 次（K 次，不是 K×D 次）", len(judged) == 2, str(len(judged)))
    check("judge 拿到的是端点", all(isinstance(t, str) and t for t in judged),
          str(judged))
    check("挑了 rubric 高的那条", r.get("best_i") == 1, str(r.get("best_i")))


def test_judge_fn_failure_falls_back():
    print("\n== 8. 判定抛异常时前瞻照跑（不能因为评审挂了就不回话）==")
    SAME = "（她沉默了一会儿，给你倒了杯茶）"
    SCRIPTS = [[SAME, "（她望向窗外）有些事你以为忘了。"],
               [SAME, "（她按住封面）先看扉页那两个字。"]]
    calls = {"n": 0}

    def fake(m):
        i = calls["n"]
        calls["n"] += 1
        b, d = i // 2, i % 2
        return SCRIPTS[b][d] if d < len(SCRIPTS[b]) else ""

    def boom(t):
        raise RuntimeError("评审服务挂了")
    r = la.expand(fake, [{"role": "user", "content": "x"}], branches=2, depth=2,
                  keys=["册子", "扉页", "字"], case_text="册子 扉页 字", judge_fn=boom)
    check("照样出结果", r.get("ok") is True, str(r.get("err")))
    check("退回启发式也能挑对（碰关键词的那条胜）", r.get("best_i") == 1,
          str(r.get("best_i")))
    check("rubric 字段是 None", all(b.get("rubric") is None for b in r["branches"]),
          str(r["branches"]))


if __name__ == "__main__":
    print("=" * 62)
    print("价值声明（rubric）测试")
    print("=" * 62)
    test_normalize()
    test_build_prompt()
    test_parse_tolerance()
    test_aggregate()
    test_judge_never_raises()
    test_judge_candidates_cap()
    test_lookahead_uses_rubric()
    test_judge_fn_failure_falls_back()
    print("\n" + "=" * 62)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
