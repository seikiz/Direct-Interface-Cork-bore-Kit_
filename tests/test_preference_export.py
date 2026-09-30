# -*- coding: utf-8 -*-
"""
偏好导出测试。

这件事的价值全在"数据只增不减、错过补不回来"上，所以最不能错的是：
    **不能记错。** 记错一条偏好标签 = 往训练集里掺一条谎言，
    而且它会在树里永久留存，事后无法分辨。

所以这里对"什么情况下宁可不记"的覆盖，比"能抽多少条"更密。

跑法：utau_env\\Scripts\\python.exe tests\\test_preference_export.py
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import preference_export as pe   # noqa: E402
import tree_weight as tw         # noqa: E402

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


def node(nid, role, content, parent=None, children=None, meta=None):
    return {"id": nid, "role": role, "content": content, "parent_id": parent,
            "children_ids": children or [], "metadata": meta or {}}


def build_tree():
    """sys → u1 → [a1, a2, a3]（用户滑了三次，停在 a2）→ u2 → [b1, b2]（停在 b2）"""
    nodes = {
        "sys": node("sys", "system", "框架", None, ["u1"]),
        "u1": node("u1", "user", "那本册子呢？", "sys", ["a1", "a2", "a3"]),
        "a1": node("a1", "assistant", "（她把册子推过来）你看这笔迹。", "u1", [],
                   {"w": {"e": 0.9}, "drift": {"s": "cleared"}}),
        "a2": node("a2", "assistant", "（她按住封面）先看扉页那行铅笔字。", "u1", ["u2"],
                   {"w": {"e": 0.6}, "drift": {"s": "cleared"}}),
        "a3": node("a3", "assistant", "（她望向窗外）有些事你以为忘了。", "u1", [],
                   {"w": {"e": 0.1}, "drift": {"s": "drifted"}}),
        "u2": node("u2", "user", "什么字？", "a2", ["b1", "b2"]),
        "b1": node("b1", "assistant", "别告诉她。", "u2", [], {"w": {"e": 0.8}}),
        "b2": node("b2", "assistant", "「别告诉她」——她写的是谁？", "u2", [],
                   {"w": {"e": 0.5}}),
    }
    return nodes, "b2"


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_basic_extract():
    print("\n== 1. 基本抽取 ==")
    nodes, leaf = build_tree()
    rec = pe.extract(nodes, leaf, role="阿岚")
    print("        抽到 %d 条" % len(rec))
    check("抽到 2 个分叉", len(rec) == 2, str(len(rec)))
    r1 = [r for r in rec if r["parent_id"] == "u1"]
    check("第一个分叉存在", len(r1) == 1)
    if r1:
        r1 = r1[0]
        check("正样本是链上的那条", r1["chosen"].startswith("（她按住封面）"),
              r1["chosen"][:20])
        check("负样本是另外两条", len(r1["rejected"]) == 2, str(len(r1["rejected"])))
        check("记下了被选中的位置", r1["chosen_index"] == 1, str(r1["chosen_index"]))
        check("候选总数正确", r1["n_candidates"] == 3)
        check("带上了上下文", len(r1["context"]) >= 1, str(r1["context"]))
        check("上下文带上了 system（它本来就是这个模型输入的一部分）",
              any(m["role"] == "system" for m in r1["context"]), str(r1["context"]))
        check("上下文是判定点【之前】的内容（不含被选中的那条）",
              all(m["content"] != r1["chosen"] for m in r1["context"]),
              str(r1["context"]))
        check("带上了启发式权重", r1["chosen_features"]["weight"] == 0.6,
              str(r1["chosen_features"]))
    # 第二个分叉：上下文里应当有 system + 之前那轮 user/assistant
    r2 = [r for r in rec if r["parent_id"] == "u2"]
    check("第二个分叉也抽到了（不被开头那句 system 挡住）", len(r2) == 1,
          str([r["parent_id"] for r in rec]))
    if r2:
        roles = [m["role"] for m in r2[0]["context"]]
        check("第二个分叉的上下文 = system + 历史轮次",
              roles[0] == "system" and "user" in roles, str(roles))


def test_skips_ambiguous():
    print("\n== 2. 判不了就【不记】（记错比漏记糟得多）==")
    nodes, leaf = build_tree()
    # 分叉不在当前链上 → 当初选了谁无从知道 → 必须跳过。
    # 注意：要真构造"不在链上"，得另开一条支线 —— 只把某个候选的 children 清空，
    # 它的父节点 u1 仍然是叶子的祖先，那个分叉照样在链上（我第一次就构造错了）。
    off = {
        "sys": node("sys", "system", "f", None, ["u1", "u1b"]),
        "u1": node("u1", "user", "主线的问题", "sys", ["a1", "a1x"]),
        "a1": node("a1", "assistant", "主线的回答", "u1", []),
        "a1x": node("a1x", "assistant", "主线被放弃的回答", "u1", []),
        "u1b": node("u1b", "user", "支线的问题", "sys", ["a2", "a3"]),
        "a2": node("a2", "assistant", "支线甲", "u1b", []),
        "a3": node("a3", "assistant", "支线乙", "u1b", []),
    }
    rec_off = pe.extract(off, "a1", role="x")
    check("主线上的分叉记得下", any(r["parent_id"] == "u1" for r in rec_off),
          str([r["parent_id"] for r in rec_off]))
    check("支线上的分叉被跳过（不知道当初选了谁）",
          all(r["parent_id"] != "u1b" for r in rec_off),
          str([r["parent_id"] for r in rec_off]))
    # 单候选不分叉
    one = {"sys": node("sys", "system", "f", None, ["u"]),
           "u": node("u", "user", "hi", "sys", ["a"]),
           "a": node("a", "assistant", "yo", "u", [])}
    check("只有一个候选 → 不算选择", pe.extract(one, "a") == [])
    # 空树
    check("空树不炸", pe.extract({}, None) == [])
    check("非字典不炸", pe.extract(None, None) == [])
    # 子节点被删过（children_ids 指向不存在的节点）→ 不能崩
    broken = {"sys": node("sys", "system", "f", None, ["u"]),
              "u": node("u", "user", "hi", "sys", ["a", "幽灵"]),
              "a": node("a", "assistant", "yo", "u", [])}
    check("children_ids 指向不存在的节点时不崩",
          isinstance(pe.extract(broken, "a"), list))


def test_skips_greeting():
    print("\n== 3. 开场白不是候选之一，是设定 ==")
    nodes = {
        "sys": node("sys", "system", "f", None, ["g1", "g2"]),
        "g1": node("g1", "assistant", "开场白A", "sys", [], {"greeting": True}),
        "g2": node("g2", "assistant", "开场白B", "sys", []),
    }
    check("默认跳过 greeting", pe.extract(nodes, "g2") == [])
    check("可以显式不跳过", len(pe.extract(nodes, "g2", skip_greeting=False)) == 1)


def test_summarize_agreement():
    print("\n== 4. 一致率 —— 这份数据最重要的产出 ==")
    nodes, leaf = build_tree()
    rec = pe.extract(nodes, leaf, role="阿岚")
    s = pe.summarize(rec)
    print("        %s" % {k: v for k, v in s.items() if k != "note"})
    # u1：你选了 0.6，被放弃里有 0.9 → 不一致
    # u2：你选了 0.5，被放弃是 0.8 → 不一致
    check("统计了配对数", s["scored_pairs"] == 2, str(s["scored_pairs"]))
    check("一致率 0（启发式和你实际选择不一致）", s["agreement"] == 0.0,
          str(s["agreement"]))
    check("记下了位置偏置", s["chosen_index_0"] == 0 and s["position_bias"] == 0.0,
          str(s.get("position_bias")))
    check("统计了被放弃的总数", s["rejected_total"] == 3, str(s["rejected_total"]))
    check("有 3 个以上候选的分叉被统计", s["forks_with_3plus"] == 1)
    check("带一句能行动的结论", "价值函数" in s["note"], s["note"])

    # 反过来：启发式选中了你选的那条
    for r in rec:
        r["chosen_features"]["weight"] = 1.0
        for x in r["rejected_features"]:
            x["weight"] = 0.1
    s2 = pe.summarize(rec)
    check("一致时算得对", s2["agreement"] == 1.0, str(s2["agreement"]))


def test_export_jsonl():
    print("\n== 5. 导出 JSONL ==")
    nodes, leaf = build_tree()
    rec = pe.extract(nodes, leaf, role="阿岚")
    d = tempfile.mkdtemp()
    p = os.path.join(d, "prefs.jsonl")
    n = pe.export_jsonl(rec, p)
    check("写入条数正确", n == len(rec))
    lines = open(p, encoding="utf-8").read().strip().split("\n")
    check("文件行数一致", len(lines) == len(rec), str(len(lines)))
    ok = True
    for ln in lines:
        o = json.loads(ln)
        if not (o.get("chosen") and o.get("rejected") and o.get("context")):
            ok = False
    check("每行都是合法且完整的 JSON", ok)
    check("中文没被转义", "册子" in open(p, encoding="utf-8").read())


def test_scan_dir():
    print("\n== 6. 扫存档目录 ==")
    nodes, leaf = build_tree()
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "阿岚.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "阿岚",
                   "history_tree": {"nodes": nodes, "current_leaf_id": leaf}},
                  f, ensure_ascii=False)
    # 坏文件不能把整次扫描带崩
    with open(os.path.join(d, "坏.json"), "w", encoding="utf-8") as f:
        f.write("{ 这不是 json")
    with open(os.path.join(d, "空.json"), "w", encoding="utf-8") as f:
        json.dump({"name": "空"}, f, ensure_ascii=False)
    r = pe.scan_dir(d)
    check("扫到 1 个角色的样本", r["sum"]["samples"] == len(pe.extract(nodes, leaf)),
          str(r["by_role"]))
    check("坏文件被跳过而不是崩掉", isinstance(r["records"], list))
    check("按角色分组", "阿岚" in r["by_role"], str(r["by_role"]))
    check("目录不存在不炸", pe.scan_dir(os.path.join(d, "不存在"))["sum"]["samples"] == 0)


if __name__ == "__main__":
    print("=" * 62)
    print("偏好导出测试")
    print("=" * 62)
    test_basic_extract()
    test_skips_ambiguous()
    test_skips_greeting()
    test_summarize_agreement()
    test_export_jsonl()
    test_scan_dir()
    print("\n" + "=" * 62)
    print(f"通过 {PASS} / 失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
