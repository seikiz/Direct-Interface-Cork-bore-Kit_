# -*- coding: utf-8 -*-
"""core_tree —— 对话树的数据结构（从 DICK_core.py 拆出）。

包含：`MessageNode`（一个节点）与 `TreeManager`（整棵树的增删改查 + 链追踪 + 叶子修正）。

为什么单独成文件：它们是**纯数据**，不依赖 ChatCore 的状态，却被 20+ 个测试
和 Kit.py 的存档逻辑直接 import。放在 2991 行的 DICK_core 里，
每改一次树逻辑都要滚过半个文件才能找到它。

兼容：`DICK_core` 仍然 `from core_tree import MessageNode, TreeManager`，
所以 `DICK_core.TreeManager` 这种写法继续有效。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from tree_repair import repair_links

def _iso_to_epoch(ts):
    """ISO 时间戳 → epoch 秒。解析不了就返回 0（调用方按"没有时间"处理）。"""
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(str(ts)).timestamp()
    except (ValueError, TypeError):
        return 0.0


class MessageNode:
    """对话节点，构成树状历史"""
    __slots__ = ('id', 'role', 'content', 'parent_id', 'children_ids', 'timestamp', 'metadata')
    def __init__(self, role: str, content: str, parent_id: Optional[str] = None, metadata: Optional[Dict] = None):
        self.id = str(uuid.uuid4())
        self.role = role
        self.content = content
        self.parent_id = parent_id
        self.children_ids = []
        self.timestamp = datetime.now().isoformat()
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data):
        node = cls(data['role'], data['content'], data.get('parent_id'), data.get('metadata', {}))
        node.id = data['id']
        node.children_ids = data.get('children_ids', [])
        node.timestamp = data.get('timestamp', datetime.now().isoformat())
        return node


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#   TreeManager - 纯树状历史管理（无 API 依赖）
# ============================================================

class TreeManager:
    """管理树状对话历史的所有操作（节点增删改查、链追踪、叶子修正）"""
    def __init__(self):
        self.nodes: Dict[str, MessageNode] = {}
        self.root_id: Optional[str] = None
        self.current_leaf_id: Optional[str] = None

    # ---------- 节点操作 ----------
    def add_node(self, role: str, content: str, parent_id: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
        node = MessageNode(role, content, parent_id, metadata)
        self.nodes[node.id] = node
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children_ids.append(node.id)
        if self.root_id is None:
            self.root_id = node.id
        self.current_leaf_id = node.id
        return node.id

    def delete_node(self, node_id: str):
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        for cid in node.children_ids[:]:
            self.delete_node(cid)
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node_id in parent.children_ids:
                parent.children_ids.remove(node_id)
        del self.nodes[node_id]
        if self.current_leaf_id == node_id:
            self.current_leaf_id = node.parent_id

    def delete_subtree(self, node_id: str):
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        for cid in node.children_ids[:]:
            self.delete_node(cid)
        node.children_ids = []

    def get_node(self, node_id: str) -> Optional[MessageNode]:
        return self.nodes.get(node_id)

    # ---------- 链追踪 ----------
    def get_current_chain(self) -> List[Dict]:
        if not self.current_leaf_id or self.current_leaf_id not in self.nodes:
            return []
        chain = []
        node = self.nodes.get(self.current_leaf_id)
        ancestors, _seen = [], set()
        while node and node.id not in _seen:   # 环保护：父子互指的坏存档会死循环
            _seen.add(node.id)
            ancestors.append(node)
            if node.parent_id and node.parent_id in self.nodes:
                node = self.nodes[node.parent_id]
            else:
                break
        ancestors.reverse()
        for n in ancestors:
            # _node_id/_ts 是给 salience 算清晰度用的内部字段（下划线前缀，
            # 出网前会被 _mk_stream 剥掉），不是给模型看的。
            chain.append({"role": n.role, "content": n.content,
                          "timestamp": n.timestamp,
                          "_node_id": n.id,
                          "_ts": _iso_to_epoch(n.timestamp),
                          "metadata": dict(n.metadata or {})})
        return chain

    def get_all_nodes_data(self) -> Dict:
        return {
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "root_id": self.root_id,
            "current_leaf_id": self.current_leaf_id
        }

    def load_nodes_data(self, data: Dict):
        self.nodes = {}
        self.root_id = None
        self.current_leaf_id = None
        if not isinstance(data, dict):
            print("[TreeManager] 加载历史树失败：数据不是对象，已重置为空树")
            return
        raw_nodes = data.get('nodes')
        if not isinstance(raw_nodes, dict):
            print("[TreeManager] 加载历史树失败：nodes 缺失或非法，已重置为空树")
            return
        for nid, ndata in raw_nodes.items():
            try:
                self.nodes[nid] = MessageNode.from_dict(ndata)
            except Exception:
                # 单个节点损坏不影响整棵树（存档守护会兜底修复文件本身）
                continue
        self.root_id, self.current_leaf_id = data.get('root_id'), data.get('current_leaf_id')
        repair_links(self)     # 老存档可能没 children_ids：按 parent_id 重建，否则回档只剩一个节点
        self.fix_leaf()
        print(f"[TreeManager] 加载后链长度: {len(self.get_current_chain())}")

    # ---------- 叶子修正 ----------
    def fix_leaf(self):
        """只在 leaf 失效时兜底（有效就不能改：读档不许把进度挪到别的分支）"""
        if self.current_leaf_id and self.current_leaf_id in self.nodes:
            return
        if not self.nodes or self.root_id is None:
            return
        node = self.nodes.get(self.root_id)
        if not node: return
        visited = set()
        while node.children_ids and node.id not in visited:
            visited.add(node.id)
            last_id = node.children_ids[-1]
            if last_id in self.nodes:
                node = self.nodes[last_id]
            else:
                break
        self.current_leaf_id = node.id
        print(f"[TreeManager] 叶子节点修正: {node.id} ({node.role})")

    def ensure_valid_leaf(self):
        if self.current_leaf_id is None or self.current_leaf_id not in self.nodes:
            self.fix_leaf()

    def count_nodes(self) -> int:
        return len(self.nodes)

    def clear(self):
        self.nodes = {}
        self.root_id = None
        self.current_leaf_id = None


# ============================================================
#   ContextInjector - 动态上下文注入器
#   根据用户输入检索索引文件，按需注入世界知识
# ============================================================
