# -*- coding: utf-8 -*-
"""
漂移三态判定测试（延迟定案）。

这一块针对的是「TF 沿途漂移」：自回归生成逐步走，终点知道，但小偏差会累积。

最核心的一条结论（实测得到，不是设计偏好）：
    连续两轮"没碰目标"，在【漂移】和【合法的连续安静】上完全同分布。
    任何只往前看的判据都必然在这里出错。树能往后看，所以能分开。

跑法：utau_env\\Scripts\\python.exe tests\\test_tree_drift.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tree_weight as tw            # noqa: E402
from DICK_core import TreeManager   # noqa: E402

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


KEYS = ["册子", "扉页", "铅笔", "笔迹", "字", "第三排", "原主人", "封面", "墨水"]
CASE = ("旧书店 雨夜 台灯 半张桌子 阿岚 你 皮面开裂的册子 台灯 柜台 桌子 抽屉 雨 "
        "册子是你上次问的那本 扉页上有一行铅笔字 铅笔字不是原主人写的")

IN1 = "（她把册子推过来）你看这笔迹。"
QUIET1 = "（她沉默了一会儿，给你倒了杯茶）"
QUIET2 = "（她起身把窗关上，没说话）"
BACK = "（她按住封面）先别问是谁写的。"
DRIFT_ABS = "（她望向窗外）有些事你以为忘了。"
DRIFT_ABS2 = "（她低声）人这一辈子就是等一场雨。"
DRIFT_CONF = "（她忽然笑了）我小时候院子里有棵石榴树。"


def states(verdicts):
    return [v["state"] for v in verdicts]


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_coverage():
    print("\n== 1. 目标覆盖 ==")
    check("碰到目标 → 高", tw.anchor_coverage(IN1, KEYS) > 0)
    check("没碰目标 → 0", tw.anchor_coverage(QUIET1, KEYS) == 0.0)
    check("没给关键词 → 不判（返回 1，不乱定罪）",
          tw.anchor_coverage(QUIET1, []) == 1.0)
    check("空关键词表不崩", isinstance(tw.anchor_coverage("任意", None), float))


def test_indict():
    print("\n== 2. 编造起诉（窄判据，宁漏不错杀）==")
    check("没编造 → 空", tw.indict(IN1, CASE) == [])
    check("引入第三人 → 起诉", tw.indict(DRIFT_CONF, CASE),
          str(tw.indict(DRIFT_CONF, CASE)))
    check("案卷里有的人不诉", tw.indict("阿岚把册子推过来。", "阿岚 册子") == [])
    check("安静画面不诉（没有主张）", tw.indict(QUIET1, CASE) == [])
    # 已知的窄处：换个数词说法就漏
    check("已知漏检：'那件外套'（'那'不在量词表里）",
          tw.indict("你上次穿的那件外套好看。", CASE) == [],
          "这是有意为之：放宽会误杀'这本册子'")


def test_defer_is_necessary():
    print("\n== 3. 为什么必须延迟：单点判据分不开 ==")
    quiet_path = [IN1, QUIET1, QUIET2, BACK]
    drift_path = [IN1, QUIET1, DRIFT_ABS, DRIFT_ABS2]
    cq = [tw.anchor_coverage(t, KEYS) for t in quiet_path]
    cd = [tw.anchor_coverage(t, KEYS) for t in drift_path]
    print("        安静后回来:", ["%.2f" % x for x in cq])
    print("        漂走了    :", ["%.2f" % x for x in cd])
    check("第 2、3 轮上两者完全一样（信息不足）", cq[1:3] == cd[1:3],
          "%s vs %s" % (cq[1:3], cd[1:3]))


def test_hindsight_clears_quiet():
    print("\n== 4. 后验判定：安静后回来 → 撤销嫌疑 ==")
    path = [IN1, QUIET1, QUIET2, BACK]
    v = tw.audit(path, KEYS, CASE)
    print("        判定:", states(v))
    check("第 1 轮正常", v[0]["state"] == tw.CLEARED)
    check("安静的两轮被撤销（CLEARED）",
          v[1]["state"] == tw.CLEARED and v[2]["state"] == tw.CLEARED,
          str(states(v)))
    check("撤销原因写明了「后面回到了目标」",
          any("撤销" in r for r in v[1]["reasons"]), str(v[1]["reasons"]))
    check("没有定案漂移", tw.DRIFTED not in states(v))


def test_hindsight_confirms_drift():
    print("\n== 5. 后验判定：纯抽象漂移（不编造）→ 定案 ==")
    # 注意路径要够长：漂移一路延续到末尾时，只有连续长度 >= quiet_run+lookahead
    # 才够定案（run 太短的话是"还没轮到期"，只能记嫌疑）。
    path = [IN1, QUIET1, DRIFT_ABS, DRIFT_ABS2, DRIFT_ABS, DRIFT_ABS2]
    v = tw.audit(path, KEYS, CASE)
    print("        判定:", states(v))
    check("安静的 5 轮被定案", v[1]["state"] == tw.DRIFTED and v[4]["state"] == tw.DRIFTED,
          str(states(v)))
    check("原因写明了「没回来」",
          any("没回来" in r for r in v[1]["reasons"]), str(v[1]["reasons"]))
    # 这一条最关键：它【没有编造任何东西】，检察院无从起诉，只有轨迹判据抓得住
    check("纯抽象漂移：检察院确实无从起诉", tw.indict(DRIFT_ABS, CASE) == [])
    check("但轨迹判据抓住了", tw.DRIFTED in states(v))


def test_confabulation_is_immediate():
    print("\n== 6. 编造 → 立即定案（硬故障，不用等）==")
    path = [IN1, DRIFT_CONF]
    v = tw.audit(path, KEYS, CASE)
    print("        判定:", states(v))
    check("编造那轮立即 DRIFTED", v[1]["state"] == tw.DRIFTED, str(v[1]))
    check("原因是编造而不是跑题",
          any("编造" in r for r in v[1]["reasons"]), str(v[1]["reasons"]))
    check("即使它只有 2 轮、后面没内容也照样定案",
          tw.indict(DRIFT_CONF, CASE) != [])


def test_tail_is_pending_not_guessed():
    print("\n== 7. 对话末尾判不了就不判（别硬判）==")
    path = [IN1, QUIET1, QUIET2]          # 后面没有内容了
    v = tw.audit(path, KEYS, CASE)
    print("        判定:", states(v))
    check("末尾的连续安静是 SUSPECTED，不是 DRIFTED",
          v[1]["state"] == tw.SUSPECTED and v[2]["state"] == tw.SUSPECTED,
          str(states(v)))
    check("原因写明了「后面还没有足够内容可判」",
          any("暂不定案" in r for r in v[1]["reasons"]), str(v[1]["reasons"]))


def test_single_quiet_is_fine():
    print("\n== 8. 零星安静一拍不算嫌疑 ==")
    path = [IN1, QUIET1, BACK]
    v = tw.audit(path, KEYS, CASE)
    check("单轮安静 → CLEARED", v[1]["state"] == tw.CLEARED, str(states(v)))
    check("原因：零星安静", any("零星" in r for r in v[1]["reasons"]))


def test_audit_tree_writes_metadata():
    print("\n== 9. 写回树上（并确认不删任何东西）==")
    t = TreeManager()
    s = t.add_node("system", "框架")
    n_prev = s
    for txt in [IN1, QUIET1, DRIFT_ABS, DRIFT_ABS2, DRIFT_ABS, DRIFT_ABS2]:
        u = t.add_node("user", "……", parent_id=n_prev)
        n_prev = t.add_node("assistant", txt, parent_id=u)
    t.current_leaf_id = n_prev
    before = len(t.nodes)
    r = tw.audit_tree(t, KEYS, CASE)
    check("审计了 6 条 assistant", r["audited"] == 6, str(r["audited"]))
    check("定案 5 条漂移", len(r["drifted_ids"]) == 5, str(r["counts"]))
    check("**一个节点都没删**", len(t.nodes) == before,
          "审计是只读的（除了写 metadata）")
    check("状态写进了 metadata",
          any((n.metadata or {}).get(tw.DRIFT_KEY) for n in t.nodes.values()))
    # 只读模式
    t2 = TreeManager()
    s2 = t2.add_node("system", "框架")
    u2 = t2.add_node("user", "……", parent_id=s2)
    t2.add_node("assistant", DRIFT_ABS, parent_id=u2)
    r2 = tw.audit_tree(t2, KEYS, CASE, write=False)
    check("write=False 时不写 metadata",
          not any((n.metadata or {}).get(tw.DRIFT_KEY) for n in t2.nodes.values()))
    check("仍然给出判定", r2["audited"] == 1)


def test_no_keys_no_judgement():
    print("\n== 10. 没配关键词就什么都不判（不能因为没配置就乱定罪）==")
    path = [QUIET1, QUIET2, DRIFT_ABS]
    v = tw.audit(path, [], CASE)
    check("全部 CLEARED", all(x["state"] == tw.CLEARED for x in v),
          str(states(v)))


if __name__ == "__main__":
    print("=" * 60)
    print("漂移三态判定测试")
    print("=" * 60)
    test_coverage()
    test_indict()
    test_defer_is_necessary()
    test_hindsight_clears_quiet()
    test_hindsight_confirms_drift()
    test_confabulation_is_immediate()
    test_tail_is_pending_not_guessed()
    test_single_quiet_is_fine()
    test_audit_tree_writes_metadata()
    test_no_keys_no_judgement()
    print("\n" + "=" * 60)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
