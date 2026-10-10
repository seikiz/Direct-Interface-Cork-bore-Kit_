# -*- coding: utf-8 -*-
"""
ranker.py —— 平民化训练：在你自己的偏好数据上，fit 一个排序器

为什么这个不需要服务器：
    你不需要训一个"懂语义的裁判"。你需要的是**把手上那些特征按你的口味重新配权重**。
    我现在的判据里，70/50、0.30 阈值、0.4/0.6 端点权重 —— **全是我猜的**。
    你有几百条偏好对之后，这些数字可以**从你的数据里拟合出来**。
    那是个线性模型：**几秒钟、笔记本 CPU、纯 numpy、不装任何东西**。

诚实的定位（别把它当成 PRM）：
    这个排序器**不看语义**，它只学"我那些手搓特征里，哪些对你重要、重要多少"。
    · 它比现在强的地方：权重是**你的**，不是我猜的
    · 它比现在弱的地方：和启发式一样，只能看你手搓出来的那十几个量
    · 真正"懂语义"的裁判（PRM）要另一条路，而且要先有数据 —— 就是这份数据

所以顺序是：**先收数据 → 训这个排序器 → 它告诉你哪些特征真的有用 → 再决定要不要上 PRM。**
"""

import json
import math
import os
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

import tree_weight as tw

MODEL_VERSION = 1
MIN_PAIRS = 40           # 少于这个数就别训了（会是噪声，不是信号）
DEF_EPOCHS = 400
DEF_LR = 0.05
L2 = 1e-3                # 正则：样本少的时候必须压住权重


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  特征（全部确定性、零成本、不需要模型）
# ============================================================
FEATURE_NAMES = [
    "len",            # 长度（归一化）
    "coverage",       # 本场目标覆盖
    "confab",         # 编造外来事物
    "refusal",        # 拒答/跳出角色
    "parent_sim",     # 与上文相似度
    "sib_max_sim",    # 与兄弟最大相似度（多样性）
    "repetition",     # 自我重复
    "dialogue",       # 对白密度（引号/「」）
    "action",         # 动作密度（（））
    "punct",          # 标点丰富度
    "ask",            # 结尾是否留问/留口子
    "para",           # 分段数
]

_RE_QUOTE = re.compile(r"[「『\"“]([^」』\"”]{1,80})[」』\"”]")
_RE_ACTION = re.compile(r"[（(][^）)]{1,60}[）)]")
_RE_ENDQ = re.compile(r"[?？]\s*$")


def features(text: str, parent_text: str = "", siblings: Optional[List[str]] = None,
             keys=None, case_text: str = "") -> np.ndarray:
    """把一条回复变成 12 维特征向量。全部是本地计算，零 API 调用。"""
    t = str(text or "")
    n = max(len(t), 1)
    sibs = [str(x) for x in (siblings or []) if str(x or "").strip()]

    # 自我重复：分句里不同句子的占比
    parts = [p.strip() for p in re.split(r"[。！？\n]", t) if len(p.strip()) >= 3]
    rep = 0.0
    if len(parts) >= 4:
        rep = 1.0 - (len(set(parts)) / len(parts))

    f_feas, _why = tw.feasibility(t)
    refusal = 1.0 if f_feas <= 0.2 else 0.0

    vals = [
        min(len(t) / 400.0, 1.0),                       # len
        float(tw.anchor_coverage(t, keys)) if keys else 0.0,
        min(len(tw.indict(t, case_text)) / 3.0, 1.0),   # confab
        refusal,
        1.0 - float(tw.similarity(t, parent_text)) if parent_text else 0.0,
        max([tw.similarity(t, s) for s in sibs] or [0.0]),   # sib_max_sim
        rep,
        min(len(_RE_QUOTE.findall(t)) / max(n / 60.0, 1.0), 1.0),
        min(len(_RE_ACTION.findall(t)) / max(n / 60.0, 1.0), 1.0),
        min(len(set(c for c in t if c in "，。！？…—、；：（）「」")) / 10.0, 1.0),
        1.0 if _RE_ENDQ.search(t) else 0.0,
        min(t.count("\n") / 4.0, 1.0),
    ]
    return np.array(vals, dtype=np.float64)


def feature_row(rec: Dict, keys=None, case_text: str = "") -> Tuple[np.ndarray, np.ndarray]:
    """从一条偏好样本里取出（正样本特征, 负样本特征矩阵）。"""
    ctx = rec.get("context") or []
    parent = ""
    for m in reversed(ctx):
        if m.get("role") == "assistant":
            parent = str(m.get("content") or "")
            break
    sibs = [str(x) for x in (rec.get("rejected") or [])]
    pos = features(rec.get("chosen"), parent, sibs, keys, case_text)
    negs = [features(x, parent, [c for c in sibs if c != x], keys, case_text)
            for x in sibs]
    return pos, np.array(negs) if negs else np.zeros((0, len(FEATURE_NAMES)))


# ============================================================
#  数据准备度（训之前先看够不够，别训出个噪声模型）
# ============================================================
def readiness(records: List[Dict]) -> Dict:
    n = len(records)
    pos_pairs = sum(len(r.get("rejected") or []) for r in records)
    idx0 = sum(1 for r in records if r.get("chosen_index") == 0)
    lens = [len(str(r.get("chosen") or "")) for r in records]
    warns = []
    if n < MIN_PAIRS:
        warns.append("偏好对只有 %d 条，建议至少 %d 条再训（现在训出来是噪声）"
                     % (n, MIN_PAIRS))
    if n and idx0 / n > 0.7:
        warns.append("有 %.0f%% 的样本你选的是第一条 —— 位置偏置很重。"
                     "模型会学成『第一条好』而不是『这条好』" % (idx0 / n * 100))
    if lens and (sum(lens) / len(lens)) < 30:
        warns.append("正样本平均只有 %.0f 字，样本可能偏短" % (sum(lens) / len(lens)))
    return {
        "samples": n,
        "pairs": pos_pairs,
        "chosen_index_0_ratio": round(idx0 / n, 4) if n else 0,
        "ready": n >= MIN_PAIRS,
        "need_more": max(0, MIN_PAIRS - n),
        "warnings": warns,
    }


# ============================================================
#  训练：成对 logistic（BPR 风格），纯 numpy SGD
# ============================================================
def train(records: List[Dict], keys=None, case_text: str = "",
          epochs: int = DEF_EPOCHS, lr: float = DEF_LR,
          holdout: float = 0.2, seed: int = 7) -> Dict:
    """在偏好对上训练线性排序器。返回 {"ok", "w", "acc", "n_pairs", ...}

    损失：对每对 (正, 负) 用 logistic 让 score(正) > score(负)。
    这是排序任务的标准做法，比"回归到 1/0"更贴合"哪条更好"这个语义。
    """
    rd = readiness(records)
    if not rd["ready"]:
        return {"ok": False, "err": "样本不够：%d 条（至少 %d）"
                                    % (rd["samples"], MIN_PAIRS),
                "readiness": rd}

    X_pos, X_neg = [], []
    for r in records:
        if not str(r.get("chosen") or "").strip():
            continue
        p, negs = feature_row(r, keys, case_text)
        if negs.shape[0] == 0:
            continue
        X_pos.append(p)
        X_neg.append(negs)
    if not X_pos:
        return {"ok": False, "err": "样本里没有可用的成对数据", "readiness": rd}

    rng = np.random.default_rng(seed)
    order = rng.permutation(len(X_pos))
    n_hold = max(1, int(len(order) * holdout)) if len(order) >= 10 else 0
    test_idx = set(order[:n_hold].tolist())
    tr = [i for i in range(len(X_pos)) if i not in test_idx]

    w = np.zeros(len(FEATURE_NAMES), dtype=np.float64)
    for _ep in range(epochs):
        for i in rng.permutation(tr):
            p, negs = X_pos[i], X_neg[i]
            # 每轮随机取一个负样本（成对 SGD）
            for j in rng.permutation(negs.shape[0]):
                d = p - negs[j]
                z = float(np.dot(w, d))
                # dL/dz = -sigmoid(-z)
                g = -1.0 / (1.0 + math.exp(min(max(z, -30.0), 30.0)))
                w -= lr * (g * d + L2 * w)

    def acc_on(idxs):
        if not idxs:
            return None
        good = tot = 0
        for i in idxs:
            sp = float(np.dot(w, X_pos[i]))
            for neg in X_neg[i]:
                tot += 1
                if sp > float(np.dot(w, neg)):
                    good += 1
        return round(good / tot, 4) if tot else None

    return {
        "ok": True,
        "version": MODEL_VERSION,
        "features": list(FEATURE_NAMES),
        "w": [round(float(x), 6) for x in w],
        "train_acc": acc_on(tr),
        "holdout_acc": acc_on(list(test_idx)) if test_idx else None,
        "n_pairs": int(sum(x.shape[0] for x in X_neg)),
        "n_samples": len(X_pos),
        "epochs": epochs,
        "readiness": rd,
    }


def score(w, text: str, parent_text: str = "", siblings=None, keys=None,
          case_text: str = "") -> Optional[float]:
    """用训好的权重给一条回复打分（映射到 0~1）。"""
    if w is None:
        return None
    try:
        v = features(text, parent_text, siblings, keys, case_text)
        z = float(np.dot(np.asarray(w, dtype=np.float64), v))
        return round(1.0 / (1.0 + math.exp(-max(min(z, 30.0), -30.0))), 4)
    except Exception:
        return None


def save(model: Dict, path: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load(path: str) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            m = json.load(f)
        if not isinstance(m, dict) or not m.get("w") or len(m["w"]) != len(FEATURE_NAMES):
            return None
        # 模型里本来就写了 version（MODEL_VERSION），但以前**不看它** —— 于是"特征数一样、
        # 含义变了"的模型会被当成好的用（排序结果悄悄失真）。缺 version 的老模型按 1 收下
        # （兼容线内认老数据），显式写了别的版本才拒绝。
        if m.get("version") not in (None, MODEL_VERSION):
            return None
        return m
    except Exception:
        pass
    return None


def explain(model: Dict, top: int = 6) -> List[Tuple[str, float]]:
    """按权重绝对值排序，看模型到底在用什么。这是"我猜的权重 vs 你的权重"的对照表。"""
    try:
        w = model.get("w") or []
        names = model.get("features") or FEATURE_NAMES
        pairs = sorted(zip(names, [float(x) for x in w]),
                       key=lambda kv: -abs(kv[1]))
        return pairs[:top]
    except Exception:
        return []
