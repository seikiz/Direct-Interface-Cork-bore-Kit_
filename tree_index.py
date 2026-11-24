# -*- coding: utf-8 -*-
"""tree_index.py —— 对话树内存增量索引与轻量持久化摘要。

职责与边界
----------
1. 树结构的唯一真相永远是 `nodes` 与每个节点的 `parent_id`；索引只是 O(1) 加速层。
2. 增量维护：
   · leaves      所有叶子节点集合（api_branches 不必 O(N) 全表扫描）
   · depth       节点到根的深度（O(1) 查询，不必每次爬父链）
   · epoch_ts    ISO 时间戳解析缓存（避免 get_current_chain 每轮重复 fromisoformat）
   · by_role     按 role（system/user/assistant）分桶
   · by_speaker  按 metadata["speaker"] 分桶（群聊按角色查发言）
   · choices     GAL 选项节点（metadata["is_choice"] == True）
   · terms       中英文倒排检索索引（支持 search() 快速搜历史对话）
3. 序列化摘要（index 字段）：体积小、可独立校验；读档若缺失或节点数不匹配，
   静默按 nodes 全量重建，100% 向后兼容旧存档与安卓端。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple

INDEX_VERSION = 1

_EN_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
_ZH_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def iso_to_epoch(ts) -> float:
    """ISO 时间戳 → epoch 秒。解析不了就返回 0.0。"""
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(str(ts)).timestamp()
    except (ValueError, TypeError):
        return 0.0


def extract_terms(text: str) -> Set[str]:
    """抽取倒排索引词项：英文/数字词 + 中文 2-gram（单字中文也保留，防单字搜索漏召回）。"""
    s = (text or "").lower()
    if not s:
        return set()
    out: Set[str] = set(_EN_TOKEN_RE.findall(s))
    for run in _ZH_RUN_RE.findall(s):
        n = len(run)
        if n == 1:
            out.add(run)
        else:
            for i in range(n - 1):
                out.add(run[i:i + 2])
    return out


class TreeIndex:
    """TreeManager 的增量索引层（无外部依赖，可随时 rebuild）。"""

    def __init__(self):
        self.leaves: Set[str] = set()
        self.depth: Dict[str, int] = {}
        self.epoch_ts: Dict[str, float] = {}
        self.by_role: Dict[str, Set[str]] = {}
        self.by_speaker: Dict[str, Set[str]] = {}
        self.choices: Set[str] = set()
        self.terms: Dict[str, Set[str]] = {}
        self._node_terms: Dict[str, Set[str]] = {}
        self._node_speaker: Dict[str, str] = {}
        self._node_role: Dict[str, str] = {}

    def clear(self):
        self.leaves.clear()
        self.depth.clear()
        self.epoch_ts.clear()
        self.by_role.clear()
        self.by_speaker.clear()
        self.choices.clear()
        self.terms.clear()
        self._node_terms.clear()
        self._node_speaker.clear()
        self._node_role.clear()

    # ---------- 增量维护 ----------
    def _index_content_and_meta(self, node):
        nid = node.id
        role = node.role or ""
        old_role = self._node_role.get(nid)
        if old_role and old_role != role:
            bucket = self.by_role.get(old_role)
            if bucket:
                bucket.discard(nid)
        self.by_role.setdefault(role, set()).add(nid)
        self._node_role[nid] = role

        meta = node.metadata if isinstance(node.metadata, dict) else {}
        speaker = str(meta.get("speaker") or "").strip()
        old_sp = self._node_speaker.get(nid, "")
        if old_sp and old_sp != speaker:
            sb = self.by_speaker.get(old_sp)
            if sb:
                sb.discard(nid)
                if not sb:
                    self.by_speaker.pop(old_sp, None)
        if speaker:
            self.by_speaker.setdefault(speaker, set()).add(nid)
            self._node_speaker[nid] = speaker
        else:
            self._node_speaker.pop(nid, None)

        if meta.get("is_choice"):
            self.choices.add(nid)
        else:
            self.choices.discard(nid)

        self.epoch_ts[nid] = iso_to_epoch(getattr(node, "timestamp", None))

        # 倒排词项：跳过 system 提示词，只索引真实对话节点（控制索引体积）
        old_terms = self._node_terms.pop(nid, None)
        if old_terms:
            for t in old_terms:
                tb = self.terms.get(t)
                if tb:
                    tb.discard(nid)
                    if not tb:
                        self.terms.pop(t, None)
        if role != "system":
            new_terms = extract_terms(getattr(node, "content", "") or "")
            if new_terms:
                self._node_terms[nid] = new_terms
                for t in new_terms:
                    self.terms.setdefault(t, set()).add(nid)

    def on_add(self, node, parent_node=None):
        nid = node.id
        if parent_node is not None:
            self.leaves.discard(parent_node.id)
            p_depth = self.depth.get(parent_node.id, 0)
            self.depth[nid] = p_depth + 1
        else:
            self.depth[nid] = 0
        if not node.children_ids:
            self.leaves.add(nid)
        self._index_content_and_meta(node)

    def on_update(self, node):
        """原地修改节点正文或 metadata 后刷新索引。"""
        if node is None:
            return
        self._index_content_and_meta(node)

    def on_delete(self, node, parent_node=None):
        nid = node.id
        self.leaves.discard(nid)
        self.depth.pop(nid, None)
        self.epoch_ts.pop(nid, None)
        self.choices.discard(nid)

        role = self._node_role.pop(nid, node.role or "")
        rb = self.by_role.get(role)
        if rb:
            rb.discard(nid)

        sp = self._node_speaker.pop(nid, "")
        if sp:
            sb = self.by_speaker.get(sp)
            if sb:
                sb.discard(nid)
                if not sb:
                    self.by_speaker.pop(sp, None)

        old_terms = self._node_terms.pop(nid, None)
        if old_terms:
            for t in old_terms:
                tb = self.terms.get(t)
                if tb:
                    tb.discard(nid)
                    if not tb:
                        self.terms.pop(t, None)

        if parent_node is not None and not parent_node.children_ids:
            self.leaves.add(parent_node.id)

    def rebuild(self, tree):
        """从树节点全量重建索引（带环保护，时间复杂度 O(N)）。"""
        self.clear()
        nodes = getattr(tree, "nodes", None) or {}
        if not nodes:
            return
        # 迭代 BFS 计算深度（多根/孤儿也覆盖）
        roots = []
        root_id = getattr(tree, "root_id", None)
        if root_id and root_id in nodes:
            roots.append(root_id)
        for nid, n in nodes.items():
            if not n.parent_id or n.parent_id not in nodes:
                if nid not in roots:
                    roots.append(nid)
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(r, 0) for r in roots]
        head = 0
        while head < len(queue):
            nid, d = queue[head]
            head += 1
            if nid in visited or nid not in nodes:
                continue
            visited.add(nid)
            node = nodes[nid]
            self.depth[nid] = d
            if not node.children_ids:
                self.leaves.add(nid)
            self._index_content_and_meta(node)
            for cid in node.children_ids:
                if cid not in visited and cid in nodes:
                    queue.append((cid, d + 1))
        # 兜底：若存在孤立环节点未被根触达，也收进索引防止遗漏
        for nid, node in nodes.items():
            if nid in visited:
                continue
            self.depth[nid] = 0
            if not node.children_ids:
                self.leaves.add(nid)
            self._index_content_and_meta(node)

    # ---------- 查询 ----------
    def depth_of(self, node_id: str) -> int:
        return self.depth.get(node_id, 0)

    def epoch_of(self, node_id: str, fallback_ts=None) -> float:
        ts = self.epoch_ts.get(node_id)
        if ts is not None:
            return ts
        val = iso_to_epoch(fallback_ts)
        if node_id:
            self.epoch_ts[node_id] = val
        return val

    def has_conversation(self) -> bool:
        return bool(self.by_role.get("user") or self.by_role.get("assistant"))

    def search(self, nodes: Dict, query: str, role: Optional[str] = None,
               speaker: Optional[str] = None, limit: int = 20) -> List[str]:
        """基于倒排索引的快速检索：按相关度与时间倒序返回命中的 node_id 列表。"""
        q = (query or "").strip()
        if not q and not role and not speaker:
            return []
        cand: Optional[Set[str]] = None
        if role:
            cand = set(self.by_role.get(role, ()))
        if speaker:
            sp_set = set(self.by_speaker.get(speaker.strip(), ()))
            cand = sp_set if cand is None else (cand & sp_set)
        q_low = q.lower()
        q_terms = extract_terms(q)
        if q_terms:
            hit_sets = [self.terms.get(t, set()) for t in q_terms]
            if hit_sets:
                # 交集优先（精准命中）；交集为空则退回并集按命中词数排序
                inter = set.intersection(*hit_sets)
                term_cands = inter if inter else set.union(*hit_sets)
            else:
                term_cands = set()
            cand = term_cands if cand is None else (cand & term_cands)
        elif q:
            # 单字符英文等不进 2-gram 的短串：退回精确子串过滤
            base = cand if cand is not None else set(nodes.keys())
            cand = {nid for nid in base if nid in nodes and q_low in (nodes[nid].content or "").lower()}
        if not cand:
            return []
        # 若有查询串，验证子串或按命中词数打分排序
        scored: List[Tuple[int, float, str]] = []
        for nid in cand:
            node = nodes.get(nid)
            if node is None or node.role == "system":
                continue
            content_low = (node.content or "").lower()
            score = 0
            if q_low and q_low in content_low:
                score += 100
            if q_terms:
                nt = self._node_terms.get(nid, ())
                score += sum(1 for t in q_terms if t in nt)
            elif not q:
                score = 1
            if score > 0:
                scored.append((score, self.epoch_ts.get(nid, 0.0), nid))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [nid for _, _, nid in scored[:max(1, int(limit or 20))]]

    # ---------- 持久化摘要 ----------
    def to_summary(self) -> Dict:
        """导出轻量化可重建索引摘要（写入 history_tree["index"]）。"""
        return {
            "v": INDEX_VERSION,
            "node_count": len(self.depth),
            "leaves": sorted(self.leaves),
            "roles": {r: len(s) for r, s in self.by_role.items() if s},
            "choices": sorted(self.choices),
        }

    @staticmethod
    def summary_matches(summary, nodes: Dict) -> bool:
        if not isinstance(summary, dict):
            return False
        return (summary.get("v") == INDEX_VERSION
                and summary.get("node_count") == len(nodes))
