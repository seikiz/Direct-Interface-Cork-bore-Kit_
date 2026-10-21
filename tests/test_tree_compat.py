# -*- coding: utf-8 -*-
"""存档关系自愈：老存档只有 parent_id → 回档只剩一个节点/一条线。

这是用户报的"有时候只有一个节点，像兼容性问题，更新后出现"的根因：
树有两份关系 —— 每个节点的 `parent_id`（权威）和父节点的 `children_ids`（缓存）。
老版本/另一台机器写出来的存档可能只写了 parent_id；渲染器读 children_ids，
于是根节点看起来没有孩子 → 整棵树画成一个点。**聊天记录其实都在**，
所以现象很难归因。

验：python tests\\test_tree_compat.py
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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


def new_tree():
    from DICK_core import TreeManager
    return TreeManager()


def nd(role, content, parent, nid, children=None):
    """造一个存档节点（可刻意不带 children_ids，模拟老格式）"""
    d = {"id": nid, "role": role, "content": content, "parent_id": parent,
         "timestamp": "2026-01-01T00:00:00"}
    if children is not None:
        d["children_ids"] = children
    return d


def reachable(t):
    """从 root 沿 children_ids 能走到的节点数"""
    if not t.root_id or t.root_id not in t.nodes:
        return 0
    seen, stack = set(), [t.root_id]
    while stack:
        nid = stack.pop()
        if nid in seen or nid not in t.nodes:
            continue
        seen.add(nid)
        stack.extend(t.nodes[nid].children_ids)
    return len(seen)


def main():
    print("=" * 62)
    print(u"存档关系自愈（parent_id 权威 · children_ids 是缓存）")
    print("=" * 62)

    print(u"\n== ① 老格式：只有 parent_id，没有 children_ids ==")
    t = new_tree()
    t.load_nodes_data({"nodes": {
        "r": nd("system", "根", None, "r"),
        "a": nd("user", "第一句", "r", "a"),
        "b": nd("assistant", "回复", "a", "b"),
        "c": nd("user", "分支", "b", "c"),
        "d": nd("assistant", "另一条分支", "b", "d"),
    }, "root_id": "r", "current_leaf_id": "c"})
    check(u"5 个节点都在", len(t.nodes) == 5, str(len(t.nodes)))
    check(u"从根能走到全部 5 个（不再是一个点）", reachable(t) == 5, str(reachable(t)))
    check(u"b 有两个孩子（分支保住了）",
          sorted(t.nodes["b"].children_ids) == ["c", "d"], str(t.nodes["b"].children_ids))
    check(u"root_id 仍是 r", t.root_id == "r", str(t.root_id))
    check(u"current_leaf_id 仍是 c", t.current_leaf_id == "c", str(t.current_leaf_id))

    print(u"\n== ② children_ids 写脏了（指向不存在的节点）==")
    t = new_tree()
    t.load_nodes_data({"nodes": {
        "r": nd("system", "根", None, "r", ["a", "ghost"]),
        "a": nd("user", "你好", "r", "a"),
    }, "root_id": "r", "current_leaf_id": "a"})
    check(u"脏引用被清掉", t.nodes["r"].children_ids == ["a"], str(t.nodes["r"].children_ids))
    check(u"仍然能走到 2 个节点", reachable(t) == 2, str(reachable(t)))

    print(u"\n== ③ root_id 缺失 / 悬空 ==")
    t = new_tree()
    t.load_nodes_data({"nodes": {
        "a": nd("system", "根", None, "a"),
        "b": nd("user", "第二句", "a", "b"),
    }, "current_leaf_id": "b"})
    check(u"root_id 被补成没有父的那个", t.root_id == "a", str(t.root_id))
    check(u"能走到 2 个节点", reachable(t) == 2, str(reachable(t)))

    t = new_tree()
    t.load_nodes_data({"nodes": {
        "a": nd("system", "根", None, "a"),
        "b": nd("user", "第二句", "a", "b"),
    }, "root_id": "不存在的id", "current_leaf_id": "b"})
    check(u"悬空 root_id 被修正", t.root_id == "a", str(t.root_id))

    print(u"\n== ④ current_leaf_id 悬空 → 取最深的叶子 ==")
    t = new_tree()
    t.load_nodes_data({"nodes": {
        "r": nd("system", "根", None, "r"),
        "a": nd("user", "一", "r", "a"),
        "b": nd("assistant", "二", "a", "b"),
        "b2": nd("assistant", "分叉", "a", "b2"),
    }, "root_id": "r", "current_leaf_id": "不存在"})
    check(u"leaf 落在叶子上（b 或 b2）", t.current_leaf_id in ("b", "b2"), str(t.current_leaf_id))
    check(u"leaf 指向的节点确实没有孩子",
          not t.nodes[t.current_leaf_id].children_ids, str(t.nodes[t.current_leaf_id].children_ids))

    print(u"\n== ⑤ 悬空父引用：节点被当成根，不会消失 ==")
    t = new_tree()
    t.load_nodes_data({"nodes": {
        "r": nd("system", "根", None, "r"),
        "x": nd("user", "父节点丢了", "ghost", "x"),
    }, "root_id": "r", "current_leaf_id": "x"})
    check(u"两个节点都在", len(t.nodes) == 2, str(len(t.nodes)))
    check(u"悬空父引用被清空", t.nodes["x"].parent_id is None, str(t.nodes["x"].parent_id))

    print(u"\n== ⑥ 环（不该出现，但不能把程序卡死）==")
    t = new_tree()
    t.load_nodes_data({"nodes": {
        "r": nd("system", "根", "b", "r"),
        "b": nd("user", "互为父", "r", "b"),
    }, "root_id": "r", "current_leaf_id": "b"})
    check(u"不抛异常且节点都在", len(t.nodes) == 2, str(len(t.nodes)))

    print(u"\n== ⑦ 修完之后再存一遍，应该是合法格式 ==")
    t = new_tree()
    t.load_nodes_data({"nodes": {
        "r": nd("system", "根", None, "r"),
        "a": nd("user", "一", "r", "a"),
    }, "root_id": "r", "current_leaf_id": "a"})
    data = t.get_all_nodes_data()
    check(u"存回去带上了 children_ids",
          data["nodes"]["r"].get("children_ids") == ["a"], str(data["nodes"]["r"].get("children_ids")))
    check(u"存回去带上了 root_id", data.get("root_id") == "r", str(data.get("root_id")))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("TREE_COMPAT_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌