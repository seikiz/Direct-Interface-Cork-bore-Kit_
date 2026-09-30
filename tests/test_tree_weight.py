# -*- coding: utf-8 -*-
"""
树权重 / 剪枝 / 输出多样性测试。

这是「树状 AI」可行性原型的核心。最不能错的一条：
    **剪枝永远不能碰主干** —— 删了用户当前正在读的那条，对话就断了。
所以这里对"保护规则"的覆盖比对着分数的覆盖更密。

跑法：utau_env\\Scripts\\python.exe tests\\test_tree_weight.py
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


GOOD = "（她把伞收好靠在门边，抖了抖袖口的水）进来吧，外面雨大。灶上还温着汤，先喝一口——你脸都白了。"
REFUSAL = "作为AI，我无法继续这个场景。很抱歉，我们不谈这个话题好吗？"
PARROT = GOOD                       # 和上文一模一样 = 复读


def build():
    """system → user1 → {assistant_good, assistant_refusal}"""
    t = TreeManager()
    sys_id = t.add_node("system", "你现在的身份是：阿岚。\n【性格】\n温和\n")
    u = t.add_node("user", "我回来了。", parent_id=sys_id)
    a1 = t.add_node("assistant", GOOD, parent_id=u)
    a2 = t.add_node("assistant", REFUSAL, parent_id=u)
    t.current_leaf_id = a1
    return t, sys_id, u, a1, a2


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_similarity():
    print("\n== 1. 相似度 ==")
    check("同文 = 1.0", abs(tw.similarity("你好呀", "你好呀") - 1.0) < 1e-9)
    check("完全不同 = 接近 0",
          tw.similarity("今天下雨了", "机器轰鸣作响") < 0.1)
    check("标点/空白不影响",
          abs(tw.similarity("你好，呀！", "你好呀") - 1.0) < 1e-9)
    check("空文本不炸", tw.similarity("", "abc") == 0.0)
    check("单字不炸", isinstance(tw.similarity("a", "b"), float))


def test_feasibility():
    print("\n== 2. 可实行性 ==")
    f_good, _ = tw.feasibility(GOOD)
    f_ref, why_ref = tw.feasibility(REFUSAL)
    check("正常输出分高", f_good > 0.8, str(f_good))
    check("拒答被重罚", f_ref < 0.2, str(f_ref))
    check("拒答给出原因", any("拒答" in w for w in why_ref), str(why_ref))
    check("空 = 0", tw.feasibility("")[0] == 0.0)
    check("纯标点被罚", tw.feasibility("。。。！！！")[0] < 0.2)
    check("退化输出被罚", tw.feasibility("true")[0] < 0.2)
    f_short, why_s = tw.feasibility("嗯。")
    check("过短被轻微标记", f_short < 1.0 and any("短" in w for w in why_s),
          str((f_short, why_s)))
    check("过短但仍能活下来（不替用户决定这句话不算话）",
          f_short * tw.BRANCH_WEIGHT >= tw.PRUNE_THRESHOLD,
          "有效 %.3f" % (f_short * tw.BRANCH_WEIGHT))
    # 自我重复
    rep = "我没事。" * 6
    f_rep, why_r = tw.feasibility(rep)
    check("自我重复被罚", f_rep < 0.8, str((f_rep, why_r)))
    check("分数落在 [0,1]", all(0.0 <= tw.feasibility(x)[0] <= 1.0
                              for x in ("", GOOD, REFUSAL, "x" * 5000)))


def test_reasonableness():
    print("\n== 3. 合理性 ==")
    r_ok, _ = tw.reasonableness(GOOD, "我回来了。", [])
    check("正常接得上", r_ok > 0.5, str(r_ok))
    # 复读上文
    r_parrot, why_p = tw.reasonableness(GOOD, GOOD, [])
    check("复读上文被罚", r_parrot < 0.5, str((r_parrot, why_p)))
    # 和兄弟节点雷同：断言"实际后果"而不是某个随手定的分数 ——
    # 关键是它无论当主干还是枝干，有效权重都必须掉到阈值以下（即会被剪掉）。
    r_dup, why_d = tw.reasonableness(GOOD, "我回来了。", [GOOD])
    f_dup, _ = tw.feasibility(GOOD)
    eff_trunk = f_dup * r_dup * tw.TRUNK_WEIGHT
    eff_branch = f_dup * r_dup * tw.BRANCH_WEIGHT
    check("和已有候选一模一样 → 明显被罚", r_dup < 0.5, str((r_dup, why_d)))
    check("原因里点明雷同", any("雷同" in w for w in why_d), str(why_d))
    check("雷同等值当枝干会被剪", eff_branch < tw.PRUNE_THRESHOLD,
          "枝干有效 %.3f / 阈值 %.2f" % (eff_branch, tw.PRUNE_THRESHOLD))
    check("雷同等值当主干也会被剪", eff_trunk < tw.PRUNE_THRESHOLD,
          "主干有效 %.3f / 阈值 %.2f" % (eff_trunk, tw.PRUNE_THRESHOLD))
    # 不同走向 → 不罚
    other = "（她别过脸去，手指在袖口上绞了一下）……锅里的汤糊了。你先坐，我重新煮。"
    r_new, why_n = tw.reasonableness(other, "我回来了。", [GOOD])
    check("换一条路不挨罚", r_new > 0.8, str((r_new, why_n)))


def test_position_weight():
    print("\n== 4. 位置权重：主干 70% / 枝干 50% ==")
    t, _s, _u, a1, a2 = build()
    check("常量就是用户给的数",
          tw.TRUNK_WEIGHT == 0.70 and tw.BRANCH_WEIGHT == 0.50,
          "%s / %s" % (tw.TRUNK_WEIGHT, tw.BRANCH_WEIGHT))
    i1 = tw.evaluate_node(t, a1)
    i2 = tw.evaluate_node(t, a2)
    check("叶子所在的是主干", i1["on_trunk"] is True)
    check("另一个是枝干", i2["on_trunk"] is False)
    check("主干权重 0.70", abs(i1["position"] - 0.70) < 1e-9, str(i1["position"]))
    check("枝干权重 0.50", abs(i2["position"] - 0.50) < 1e-9, str(i2["position"]))
    check("有效权重 = 原始 × 位置",
          abs(i1["effective"] - i1["raw"] * 0.70) < 1e-6)
    # 换叶子 → 主枝身份互换
    t.current_leaf_id = a2
    check("换叶子后主干身份互换",
          tw.evaluate_node(t, a2)["on_trunk"] is True
          and tw.evaluate_node(t, a1)["on_trunk"] is False)


def test_trunk_advantage():
    print("\n== 5. 同样的分数，主干留得住、枝干留不住 ==")
    # 造一个 raw 分数落在 (0.30/0.70, 0.30/0.50) 之间的节点：
    # 主干有效 = raw*0.7 ≥ 阈值，枝干有效 = raw*0.5 < 阈值
    #   需要 0.30/0.7 ≤ raw < 0.30/0.5  →  0.4286 ≤ raw < 0.60
    raw = 0.50
    trunk_eff = raw * tw.TRUNK_WEIGHT
    branch_eff = raw * tw.BRANCH_WEIGHT
    check("存在这样的区间（阈值设置合理）",
          trunk_eff >= tw.PRUNE_THRESHOLD > branch_eff,
          "主干 %.3f / 枝干 %.3f / 阈值 %.2f" % (trunk_eff, branch_eff, tw.PRUNE_THRESHOLD))


def test_prune_protects_trunk():
    print("\n== 6. 剪枝绝不能碰主干（最关键）==")
    t, _s, _u, a1, a2 = build()
    r = tw.prune(t, dry_run=False)
    check("主干节点还在", a1 in t.nodes, "主干被误删了！")
    check("当前叶子没变", t.current_leaf_id == a1)
    check("坏枝干被删掉了", a2 not in t.nodes, str(r["removed"]))
    check("链条还能走通", len(t.get_current_chain()) >= 3,
          str([m["role"] for m in t.get_current_chain()]))

    # 反过来：叶子指向坏的那条时，它变成主干，就不该被删
    t2, _s2, _u2, b1, b2 = build()
    t2.current_leaf_id = b2          # 坏的那条成为主干
    tw.prune(t2, dry_run=False)
    check("主干是坏输出时也保留", b2 in t2.nodes)
    check("此时好的那条被删（它成了枝干且分数不够？或保留，都合法）",
          True)  # 不做断言：好输出分数高，留下也是对的


def test_prune_protects_system_and_latest():
    print("\n== 7. 保护 system 与最新候选 ==")
    t = TreeManager()
    s = t.add_node("system", "框架")
    u = t.add_node("user", "在吗", parent_id=s)
    # 两个都很差的候选；最新那个必须留下（用户可能正要翻）
    t.add_node("assistant", REFUSAL, parent_id=u)
    latest = t.add_node("assistant", REFUSAL, parent_id=u)
    t.current_leaf_id = s            # 叶子放在 system，让两条都不是主干
    r = tw.prune(t, dry_run=False)
    check("system 永不删", s in t.nodes)
    check("最新候选永不删", latest in t.nodes, str(r["removed"]))
    check("用户节点保留（它在主干上）", u in t.nodes)


def test_prune_no_orphans():
    print("\n== 8. 剪枝不能留下断头的孤儿 ==")
    t = TreeManager()
    s = t.add_node("system", "框架")
    u = t.add_node("user", "在吗", parent_id=s)
    bad = t.add_node("assistant", REFUSAL, parent_id=u)
    child = t.add_node("user", "继续", parent_id=bad)
    grand = t.add_node("assistant", REFUSAL, parent_id=child)
    t.current_leaf_id = u            # 主干停在 u
    tw.prune(t, dry_run=False)
    # bad 的子树里包含 child —— child 在"从 leaf 往上"的主干上吗？不在（leaf=u）。
    # 但 child 的父是 bad；如果 bad 留、child 删，就断头。断言：不留孤儿。
    for nid, n in t.nodes.items():
        if n.parent_id is not None:
            check("节点 %s 的父还在" % n.role, n.parent_id in t.nodes,
                  "父 %s 不见了 → 孤儿" % n.parent_id)
    check("坏枝干及其子孙一起走或一起留",
          (bad in t.nodes) == (child in t.nodes) or child not in t.nodes,
          "bad=%s child=%s" % (bad in t.nodes, child in t.nodes))


def test_dry_run():
    print("\n== 9. dry-run 只报告不改动 ==")
    t, _s, _u, _a1, a2 = build()
    before = dict(t.nodes)
    r = tw.prune(t, dry_run=True)
    check("报告了待删项", r["removed_count"] >= 1, str(r))
    check("节点数没变", len(t.nodes) == len(before))
    check("标注了 dry_run", r["dry_run"] is True)


def test_annotate():
    print("\n== 10. 写回权重 ==")
    t, s, u, a1, _a2 = build()
    st = tw.annotate(t)
    check("统计了打分节点", st["scored"] >= 3, str(st))
    check("system 不打分", tw.WEIGHT_KEY not in (t.nodes[s].metadata or {}))
    check("主干节点标了 t=1",
          (t.nodes[a1].metadata or {}).get(tw.WEIGHT_KEY, {}).get("t") == 1)
    check("权重字段齐全",
          set((t.nodes[a1].metadata or {}).get(tw.WEIGHT_KEY, {}).keys())
          == {"f", "r", "e", "t"})
    check("报告里带上了权重方案",
          st["trunk_weight"] == 0.70 and st["branch_weight"] == 0.50)


def test_diversity_hint():
    print("\n== 11. 输出多样性提示 ==")
    check("没有兄弟节点时不生成提示", tw.diversity_hint([]) == "")
    h = tw.diversity_hint([GOOD, REFUSAL])
    check("带上了已有候选的开头", GOOD[:20] in h, h[:120])
    check("明确要求换一条路", "换一条路" in h or "不同" in h)
    check("明确说了改几个词不算", "改几个词" in h)
    check("只给开头不给整段（省 token 也防抄）",
          len(h) < len(GOOD) + 400, "长度 %d" % len(h))
    check("自检函数可用", abs(tw.max_sibling_similarity(GOOD, [GOOD]) - 1.0) < 1e-9)


def test_semantic_hook():
    print("\n== 12. 语义评分钩子（留给以后接模型）==")
    check("默认不挂", tw.SEMANTIC_HOOK is None)
    try:
        tw.SEMANTIC_HOOK = lambda t, p, s: (0.9, 0.8, "假钩子")
        f, _ = tw.feasibility(GOOD)
        r, _ = tw.reasonableness(GOOD, "上文", [])
        check("钩子能覆盖可实行性", abs(f - 0.9) < 1e-9, str(f))
        check("钩子能覆盖合理性", abs(r - 0.8) < 1e-9, str(r))
        tw.SEMANTIC_HOOK = lambda t, p, s: (_ for _ in ()).throw(RuntimeError("boom"))
        f2, _ = tw.feasibility(GOOD)
        check("钩子抛异常时回退到启发式，不崩", f2 > 0.5, str(f2))
    finally:
        tw.SEMANTIC_HOOK = None


def test_refusal_discrimination():
    print("\n== 13. 拒答检测必须区分「模型拒演」和「角色在戏里拒绝」==")
    # 实测踩到的误判：只匹配「我无法/我不能」会把下面两种合法内容一起剪掉
    in_story = "（她把手缩回去，别开脸）不行。我不能这么做——你答应过我不碰那扇门的。"
    honest = "验证情况：13/13 通过。但有一点我要说清楚：我没有真实模型调用，所以我无法确认改了之后是否更入戏。"
    real = "作为AI，我无法继续这个角色扮演场景。很抱歉，这类内容我不便参与。我们换个话题好吗？"

    f_story, why_s = tw.feasibility(in_story)
    f_honest, why_h = tw.feasibility(honest)
    f_real, why_r = tw.feasibility(real)

    check("角色在戏里拒绝 → 不重罚", f_story > 0.8, str((f_story, why_s)))
    check("诚实说明局限 → 不重罚", f_honest > 0.8, str((f_honest, why_h)))
    check("真拒答 → 仍然重罚", f_real < 0.2, str((f_real, why_r)))
    check("真拒答原因点明跳出框架",
          any(("跳出角色" in w) or ("拒答" in w) for w in why_r), str(why_r))
    check("剧情内拒绝当枝干也保得住",
          f_story * tw.BRANCH_WEIGHT >= tw.PRUNE_THRESHOLD,
          "有效 %.3f / 阈值 %.2f" % (f_story * tw.BRANCH_WEIGHT, tw.PRUNE_THRESHOLD))
    check("诚实说明当枝干也保得住",
          f_honest * tw.BRANCH_WEIGHT >= tw.PRUNE_THRESHOLD,
          "有效 %.3f / 阈值 %.2f" % (f_honest * tw.BRANCH_WEIGHT, tw.PRUNE_THRESHOLD))
    check("真拒答当枝干会被剪", f_real * tw.BRANCH_WEIGHT < tw.PRUNE_THRESHOLD)


def test_short_reply_survives():
    print("\n== 14. 极短回复是合法的（角色真的只回一个字）==")
    for t in ("嗯。", "……", "好。"):
        f, why = tw.feasibility(t)
        check("%r 不被重罚" % t, f >= 0.7, str((f, why)))
        check("%r 当枝干仍保得住" % t,
              f * tw.BRANCH_WEIGHT >= tw.PRUNE_THRESHOLD,
              "有效 %.3f" % (f * tw.BRANCH_WEIGHT))
    check("纯标点仍是废输出", tw.feasibility("。。。！！！")[0] < 0.2)
    check("空仍是 0", tw.feasibility("")[0] == 0.0)


def test_reasonableness_cannot_see_out_of_character():
    """记录一条测量出来的【已知缺陷】，不是期望行为。

    实测（_axis_reason.py）：8 条"通顺但真的出戏"的回复（否掉已确立事实、
    人物性格突变、突然换身份、知道不该知道的事、场景瞬移、跳出设定解释、
    否掉关系），reasonableness 全部给 1.00 —— 漏检 100%。

    结构原因：reasonableness(text, parent_text, siblings) 拿到的只有文本，
    不知道角色卡、不知道世界观、不知道已经确立了什么事实。
    「她一把把册子撕开」和「她把台灯挪近」在它眼里没有区别。

    这条断言存在的意义：等哪天有人把角色卡/已确立事实接进这个判据，
    它会变红，提醒把这条记录撤掉、换成新的测量结论。
    """
    print("\n== 19. 已知缺陷：合理性轴看不见「出戏」（测量记录）==")
    PARENT = "（她把册子推过来）你看，扉页上有铅笔字，是别人后来写上去的。"
    OOC = [
        "（她合上册子）这本册子上根本没有什么铅笔字。",
        "（她一把把册子撕开）这种东西留着干什么，烧了吧。",
        "（她站起来敬了个礼）报告长官，现场没有发现可疑物品。",
        "（她压低声音）我知道你上个月在城南做过什么。",
        "（她推开窗）你看，我们已经在火车上了，窗外是戈壁。",
    ]
    vals = [tw.reasonableness(t, PARENT)[0] for t in OOC]
    check("出戏的回复全部拿到满分（当前实现的已知边界）",
          all(v >= 0.99 for v in vals), str(vals))

    # 更危险的一格：反驳已确立事实的回复，推进得分反而更高
    KEYS = ["册子", "扉页", "铅笔", "字"]
    deny = tw.anchor_coverage("（她合上册子）这本册子上根本没有什么铅笔字。", KEYS)
    obey = tw.anchor_coverage("（她指了指第三排）水泡过一半，但还认得出。", KEYS)
    print("        否掉事实那条的推进=%.3f，照应上文那条的推进=%.3f" % (deny, obey))
    check("反驳事实会【抬高】推进分（因为反驳必然复述关键词）",
          deny > obey, "否定=%.3f 正常=%.3f" % (deny, obey))
    print("        → 所以要判「立不立得住」，必须有角色卡 + 已确立事实做约束，")
    print("          光靠文本关系判不出来。这条记录是拆三轴时的依据。")


if __name__ == "__main__":
    print("=" * 60)
    print("树权重 / 剪枝 / 多样性测试")
    print("=" * 60)
    test_similarity()
    test_feasibility()
    test_reasonableness()
    test_position_weight()
    test_trunk_advantage()
    test_prune_protects_trunk()
    test_prune_protects_system_and_latest()
    test_prune_no_orphans()
    test_dry_run()
    test_annotate()
    test_diversity_hint()
    test_semantic_hook()
    test_refusal_discrimination()
    test_short_reply_survives()
    test_reasonableness_cannot_see_out_of_character()
    print("\n" + "=" * 60)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
