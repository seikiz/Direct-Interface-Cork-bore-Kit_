# -*- coding: utf-8 -*-
"""
preference_export.py —— 把树里"已经在产生、但正在消失"的偏好信号接住

为什么必须现在做：
    偏好信号有时效性。每次重 roll 出来的兄弟节点都留在树上，而你最终停在哪一条
    就是一次隐式投票 —— 但那个信息只存在树的结构里，不导出就永远拿不到。
    而且它【只增不减】：今天不接，今天的数据以后补不回来。

它抽的是什么：
    每个"有 2 条以上 assistant 候选"的父节点，就是一次选择。
    在【当前链上】的那条 = 你选的（正样本）；同父的其他兄弟 = 你放弃的（负样本）。
    只有落在当前链上的分叉才能判定 —— 已经废弃的支线上，无从知道当初选了谁。

它顺手回答的一个关键问题：
    **我的启发式和你实际的选择，一致率多少？**
    这是"能不能在前瞻上用这个价值函数"的唯一实证依据。
    一致率低 → 先把价值函数弄好，别急着加搜索深度（否则就是烧钱放大错误）。

诚实的局限（别让这份数据显得比它实际更强）：
  · 稀疏：你只在不满时才滑动；满意时没有信号
  · 位置偏置：懒得滑直接用第一条 → 第一条被高估（所以记了 chosen_index）
  · 粒度粗：只知道"选了这条"，不知道"好在哪"
  · 单一口味：这是【你】的偏好，不是普遍偏好
"""

import json
import os
from typing import Dict, List, Optional

import tree_weight as tw


def _chain_ids(nodes: Dict, leaf_id: Optional[str]) -> List[str]:
    """从叶子往上取到根的 id 链（正序）"""
    out = []
    seen = set()
    nid = leaf_id
    while nid and nid in nodes and nid not in seen:
        seen.add(nid)
        out.append(nid)
        nid = (nodes[nid] or {}).get("parent_id")
    out.reverse()
    return out


def _text(nodes: Dict, nid: str) -> str:
    return str((nodes.get(nid) or {}).get("content") or "")


def _meta(nodes: Dict, nid: str) -> Dict:
    return dict((nodes.get(nid) or {}).get("metadata") or {})


def _context(nodes: Dict, chain: List[str], upto: str, window: int) -> List[Dict]:
    """取判定点之前的上下文，当作模型输入。

    必须【带上 system】—— 它本来就是这个模型输入的一部分。
    之前只取 user/assistant，结果"紧跟 system 的第一个分叉"上下文为空、
    整条被丢掉 —— 而第一个分叉恰恰是样本质量最高的一批（后面还没有偏）。
    """
    try:
        pos = chain.index(upto)
    except ValueError:
        return []
    # system 节点算【上下文】而不是<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌"上一轮"，所以把父节点自己也纳进来：
    # 父节点是 system 时（例如 sys → 开场白 这种分叉），chain[:pos] 是空的，
    # 不带父节点的话整条样本会被当成"没有上下文"丢掉。
    sysmsgs = [{"role": "system", "content": _text(nodes, n)}
               for n in chain[:pos + 1]
               if (nodes.get(n) or {}).get("role") == "system"]
    turns = [{"role": (nodes.get(n) or {}).get("role"), "content": _text(nodes, n)}
             for n in chain[:pos]
             if (nodes.get(n) or {}).get("role") in ("user", "assistant")]
    if window > 0:
        turns = turns[-window:]
    return sysmsgs + turns


def extract(nodes: Dict, leaf_id: Optional[str], role: str = "",
            window: int = 6, skip_greeting: bool = True) -> List[Dict]:
    """从一个对话树里抽出偏好样本。

    nodes    : {id: 节点字典}（存档里的 history_tree.nodes 就是这个形状）
    leaf_id  : 当前叶子（决定"选了哪条"）
    window   : 上下文取判定点之前多少轮
    """
    if not isinstance(nodes, dict) or not nodes:
        return []
    chain = _chain_ids(nodes, leaf_id)
    on_chain = set(chain)
    out = []
    for pid, pnode in nodes.items():
        if not isinstance(pnode, dict):
            continue
        kids = [c for c in (pnode.get("children_ids") or []) if c in nodes]
        ai_kids = [c for c in kids if (nodes[c] or {}).get("role") == "assistant"]
        if len(ai_kids) < 2:
            continue                      # 没有分叉 = 没有选择
        chosen = [c for c in ai_kids if c in on_chain]
        if len(chosen) != 1:
            # 0 条：这个分叉不在当前链上，当初选了谁无从知道
            # 多条：结构异常，宁可不记也别记错
            continue
        chosen = chosen[0]
        rejected = [c for c in ai_kids if c != chosen]
        if skip_greeting and any(_meta(nodes, c).get("greeting") for c in ai_kids):
            # 开场白节点的内容是【作者写的】，不是模型输出。
            # 只要候选里混着它，这一对的来源就不纯 → 整条跳过。
            # （宁可少记，也不能把作者的文字当成"模型生成的候选"喂进训练集。）
            continue
        ctx = _context(nodes, chain, pid, window)
        if not ctx:
            continue                      # 没有上下文，样本没法用
        cw = _meta(nodes, chosen).get(tw.WEIGHT_KEY) or {}
        out.append({
            "role": role,
            "parent_id": pid,
            "parent_role": (pnode or {}).get("role"),
            "context": ctx,
            "chosen": _text(nodes, chosen),
            "rejected": [_text(nodes, c) for c in rejected],
            "chosen_index": ai_kids.index(chosen),
            "n_candidates": len(ai_kids),
            "chosen_features": {
                "weight": cw.get("e"), "feasibility": cw.get("f"),
                "reasonableness": cw.get("r"),
                "drift": (_meta(nodes, chosen).get(tw.DRIFT_KEY) or {}).get("s"),
            },
            "rejected_features": [
                {"weight": (_meta(nodes, c).get(tw.WEIGHT_KEY) or {}).get("e"),
                 "drift": (_meta(nodes, c).get(tw.DRIFT_KEY) or {}).get("s")}
                for c in rejected
            ],
            "node_ids": {"chosen": chosen, "rejected": rejected},
        })
    return out


def _score_of(rec: Dict, key: str) -> Optional[float]:
    v = (rec or {}).get(key)
    if isinstance(v, dict):
        v = v.get("weight")
    return v if isinstance(v, (int, float)) else None


def summarize(records: List[Dict]) -> Dict:
    """统计，重点是【启发式与实际选择的一致率】。"""
    n = len(records)
    if not n:
        return {"samples": 0}
    pairs = 0
    agree = 0
    first_pos = 0
    multi = 0
    no_score = 0
    for r in records:
        cs = _score_of(r, "chosen_features")
        rs = [x.get("weight") for x in (r.get("rejected_features") or [])
              if isinstance(x.get("weight"), (int, float))]
        if r.get("chosen_index") == 0:
            first_pos += 1
        if r.get("n_candidates", 0) >= 3:
            multi += 1
        if cs is None or not rs:
            no_score += 1
            continue
        pairs += 1
        # 一致 = 你选的那条，启发式给的权重不低于所有被放弃的
        if cs >= max(rs) - 1e-9:
            agree += 1
    return {
        "samples": n,
        "scored_pairs": pairs,
        "agree": agree,
        "agreement": round(agree / pairs, 4) if pairs else None,
        "chosen_index_0": first_pos,
        "position_bias": round(first_pos / n, 4),
        "rejected_total": sum(len(r.get("rejected") or []) for r in records),
        "forks_with_3plus": multi,
        "unscored": no_score,
        "note": ("一致率是「能不能用这个价值函数做前瞻」的唯一实证依据。"
                 "一致率低就先改价值函数，别加搜索深度。"
                 if pairs else "还没打分过，先跑一次「⚖ 打分」再导出。"),
    }


def export_jsonl(records: List[Dict], path: str) -> int:
    """写 JSONL。返回写入条数。原子写：写一半崩了不会留下半个文件。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return len(records)


def scan_dir(save_dir: str, window: int = 6) -> Dict:
    """扫描整个存档目录里所有角色卡，抽出全部偏好样本。"""
    all_rec = []
    per_role = {}
    if not os.path.isdir(save_dir):
        return {"records": [], "by_role": {}, "sum": {"samples": 0}}
    for fn in sorted(os.listdir(save_dir)):
        if not fn.endswith(".json") or fn.startswith("."):
            continue
        try:
            with open(os.path.join(save_dir, fn), "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        tree = data.get("history_tree") or {}
        nodes = tree.get("nodes") or {}
        leaf = tree.get("current_leaf_id")
        if not nodes or not leaf:
            continue
        rec = extract(nodes, leaf, role=data.get("name") or fn[:-5], window=window)
        if rec:
            all_rec.extend(rec)
            per_role[data.get("name") or fn[:-5]] = len(rec)
    return {"records": all_rec, "by_role": per_role, "sum": summarize(all_rec)}
