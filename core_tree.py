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

from tree_index import TreeIndex, iso_to_epoch as _iso_to_epoch
from tree_repair import repair_links


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
    """管理树状对话历史的所有操作（节点增删改查、索引维护、链缓存、叶子修正）"""
    def __init__(self):
        self.nodes: Dict[str, MessageNode] = {}
        self.root_id: Optional[str] = None
        self.current_leaf_id: Optional[str] = None
        self.index: TreeIndex = TreeIndex()
        self._version: int = 0
        self._chain_cache_key = None
        self._chain_cache_nodes: List[MessageNode] = []

    def bump_version(self):
        self._version += 1
        self._chain_cache_key = None

    # ---------- 节点操作 ----------
    def add_node(self, role: str, content: str, parent_id: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
        node = MessageNode(role, content, parent_id, metadata)
        self.nodes[node.id] = node
        parent_node = self.nodes.get(parent_id) if parent_id else None
        if parent_node is not None:
            parent_node.children_ids.append(node.id)
        if self.root_id is None:
            self.root_id = node.id
        self.current_leaf_id = node.id
        self.index.on_add(node, parent_node)
        self.bump_version()
        return node.id

    def update_node(self, node_id: str, content: Optional[str] = None, metadata: Optional[Dict] = None) -> bool:
        """原地修改节点内容或元数据，并同步刷新索引与链缓存。"""
        node = self.nodes.get(node_id)
        if node is None:
            return False
        if content is not None:
            node.content = content
        if metadata is not None:
            node.metadata = metadata
        self.index.on_update(node)
        self.bump_version()
        return True

    def delete_node(self, node_id: str):
        """迭代栈删除节点及其全部后代（避免千层深树 RecursionError），并同步维护索引。"""
        if node_id not in self.nodes:
            return
        root_del = self.nodes[node_id]
        parent_node = self.nodes.get(root_del.parent_id) if root_del.parent_id else None
        if parent_node is not None and node_id in parent_node.children_ids:
            parent_node.children_ids.remove(node_id)
        # 后序迭代收集整棵待删子树（带环保护）
        stack = [node_id]
        to_remove: List[str] = []
        seen = set()
        while stack:
            cur_id = stack.pop()
            if cur_id in seen or cur_id not in self.nodes:
                continue
            seen.add(cur_id)
            to_remove.append(cur_id)
            stack.extend(self.nodes[cur_id].children_ids)
        leaf_deleted = self.current_leaf_id in seen
        for rid in reversed(to_remove):
            n = self.nodes.pop(rid, None)
            if n is not None:
                self.index.on_delete(n, parent_node if rid == node_id else None)
        if leaf_deleted:
            self.current_leaf_id = root_del.parent_id
        if self.root_id in seen:
            self.root_id = None
        self.bump_version()

    def delete_subtree(self, node_id: str):
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        for cid in node.children_ids[:]:
            self.delete_node(cid)
        node.children_ids = []
        self.index.leaves.add(node_id)
        self.bump_version()

    def get_node(self, node_id: str) -> Optional[MessageNode]:
        return self.nodes.get(node_id)

    def search_nodes(self, query: str, role: Optional[str] = None,
                     speaker: Optional[str] = None, limit: int = 20) -> List[MessageNode]:
        """利用倒排索引快速搜索历史节点。"""
        ids = self.index.search(self.nodes, query, role=role, speaker=speaker, limit=limit)
        return [self.nodes[nid] for nid in ids if nid in self.nodes]

    # ---------- 链追踪 ----------
    def get_current_chain_nodes(self) -> List[MessageNode]:
        """返回 root → current_leaf 的 MessageNode 列表（带版本号缓存与环保护）。"""
        leaf = self.current_leaf_id
        if not leaf or leaf not in self.nodes:
            return []
        cache_key = (self._version, leaf, len(self.nodes))
        if self._chain_cache_key == cache_key:
            return list(self._chain_cache_nodes)
        node = self.nodes.get(leaf)
        ancestors, _seen = [], set()
        while node and node.id not in _seen:   # 环保护：父子互指的坏存档会死循环
            _seen.add(node.id)
            ancestors.append(node)
            if node.parent_id and node.parent_id in self.nodes:
                node = self.nodes[node.parent_id]
            else:
                break
        ancestors.reverse()
        self._chain_cache_key = cache_key
        self._chain_cache_nodes = ancestors
        return list(ancestors)

    def get_current_chain(self) -> List[Dict]:
        ancestors = self.get_current_chain_nodes()
        if not ancestors:
            return []
        chain = []
        for n in ancestors:
            # _node_id/_ts 是给 salience 算清晰度用的内部字段（下划线前缀，
            # 出网前会被 _mk_stream 剥掉），不是给模型看的。
            chain.append({"role": n.role, "content": n.content,
                          "timestamp": n.timestamp,
                          "_node_id": n.id,
                          "_ts": self.index.epoch_of(n.id, n.timestamp),
                          "metadata": dict(n.metadata or {})})
        return chain

    def get_all_nodes_data(self) -> Dict:
        return {
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "root_id": self.root_id,
            "current_leaf_id": self.current_leaf_id,
            "index": self.index.to_summary(),
        }

    def load_nodes_data(self, data: Dict):
        self.nodes = {}
        self.root_id = None
        self.current_leaf_id = None
        self.index.clear()
        self.bump_version()
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
        self.index.rebuild(self)
        self.bump_version()
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
        self._chain_cache_key = None
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
        self.index.clear()
        self.bump_version()


# ============================================================
#   ContextInjector - 动态上下文注入器
#   根据用户输入检索索引文件，按需注入世界知识
# ============================================================
