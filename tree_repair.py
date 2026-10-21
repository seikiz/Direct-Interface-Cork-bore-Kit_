# -*- coding: utf-8 -*-
"""存档结构自愈：按 parent_id 重建 children_ids，并修 root / leaf。

**为什么需要**（用户报的"回档里只有一个节点 / 只有一条线，像兼容性问题，升级后出现"）：
    树有两份"关系"：每个节点的 `parent_id`（权威）和父节点的 `children_ids`（缓存）。
    老版本 / 另一个端写出来的存档可能**只写了 parent_id**，或者 `children_ids` 写丢/写错。
    渲染器（安卓二维分支图、桌面当前链）都读 `children_ids` —— 一旦它空，
    根节点看起来"没有孩子"，整棵树就画成一个点或一条线；聊天记录却还在，
    于是现象很难归因（不是丢档，是关系缓存坏了）。

策略：**parent_id 永远是权威**。加载后无条件重建 children_ids，
      root_id 悬空就取一个没有父的节点，current_leaf_id 悬空就取最深的叶子。
      函数返回统计，方便上层打一行日志（"修补了 N 个节点"）。
"""
from __future__ import annotations


def _node_attr(node, name):
    if isinstance(node, dict):
        return node.get(name)
    return getattr(node, name, None)


def _set_children(node, children):
    if isinstance(node, dict):
        node["children_ids"] = children
    else:
        node.children_ids = children


def _children_of(node):
    return list(_node_attr(node, "children_ids") or [])


def repair_links(owner):
    """重建 owner.nodes 的关系缓存。owner 需要有 .nodes / .root_id / .current_leaf_id。

    返回 dict：rebuilt（重建了多少条子关系）/ orphans（没有有效父的节点数）/
             root_fixed / leaf_fixed（是否动过）。
    """
    nodes = getattr(owner, "nodes", None) or {}
    stats = {"rebuilt": 0, "orphans": 0, "root_fixed": False, "leaf_fixed": False}
    if not nodes:
        return stats

    # ① 清空所有 children_id<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌s（重建，不做增量，避免残留脏关系）
    for node in nodes.values():
        _set_children(node, [])

    # ② 按 parent_id 挂回去；父不存在的当根（并清掉悬空引用）
    orphans = []
    for nid, node in nodes.items():
        pid = _node_attr(node, "parent_id")
        if pid and pid in nodes and pid != nid:
            _set_children(nodes[pid], _children_of(nodes[pid]) + [nid])
            stats["rebuilt"] += 1
        else:
            if pid:
                if isinstance(node, dict):
                    node["parent_id"] = None
                else:
                    node.parent_id = None
            orphans.append(nid)
    stats["orphans"] = len(orphans)

    # ③ 根：现有 root 不在树里 → 取"没有父"的第一个；再不行随便拿一个
    root = getattr(owner, "root_id", None)
    if not root or root not in nodes:
        owner.root_id = orphans[0] if orphans else next(iter(nodes))
        stats["root_fixed"] = True

    # ④ 叶子：现有 leaf 不在树里 → 取最深的叶子（沿 children 走，防环）
    leaf = getattr(owner, "current_leaf_id", None)
    if not leaf or leaf not in nodes:
        owner.current_leaf_id = _deepest_leaf(owner, nodes) or owner.root_id
        stats["leaf_fixed"] = True
    return stats


def _deepest_leaf(owner, nodes):
    """从根往下找最深的叶子；有环也能停（seen 集合）。"""
    root = getattr(owner, "root_id", None)
    if not root or root not in nodes:
        return None
    seen = set()
    best, best_depth = None, -1
    stack = [(root, 0)]
    while stack:
        nid, depth = stack.pop()
        if nid in seen or nid not in nodes:
            continue
        seen.add(nid)
        node = nodes[nid]
        kids = _children_of(node)
        if not kids:
            if depth > best_depth:
                best, best_depth = nid, depth
            continue
        for k in kids:
            stack.append((k, depth + 1))
    return best
