# -*- coding: utf-8 -*-
"""
tree_weight.py —— 树权重、剪枝、输出多样性

这是「树状 AI」的可行性原型里最核心的一块：让树不只是记忆，而是能**评价和取舍**。

用户给的权重方案（这是硬指标，不要改）：
    主干（当前链 root→leaf）  70%   —— 你现在走的这条路，优先保留
    枝干（其他分支）          50%   —— 探索出来的岔路，要更优秀才留得住
    有效权重 = 可实行性 × 合理性 × 位置权重

为什么是"乘"而不是"加"：
    可实行性和合理性是**两个都必须满足**的条件 —— 一个"合理但根本没法执行"
    的输出，和一个"能执行但驴唇不对马嘴"的输出，都不该留。乘法天然表达这个。

必须说清楚的一件事（别把它当成语义判断）：
    可实行性 / 合理性在这里是**确定性启发式的代理指标**，不是真的语义理解。
    它们能抓的是「拒答、复读、退化、跑题、和兄弟节点雷同」这类明显问题，
    抓不了「这个剧情走向好不好」。真要做语义评分得另外调模型，那是另一条路
    （score_node 留了 hook，见 SEMANTIC_HOOK）。

设计上刻意做的三件事：
  ① 绝不动主干 —— 剪枝只碰不在当前链上的节点，永远不会把用户正在读的那条删掉；
  ② 绝不动最近 —— 每个父节点下最新的那条候选永远保留（用户可能正要看它）；
  ③ 整棵子树一起判 —— 保留一个节点却删掉它的孩子，会留下一堆断头的孤儿。
"""

import re
from typing import Dict, List, Optional, Tuple

# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  权重常量（用户指定，不要随手改）
# ============================================================
TRUNK_WEIGHT = 0.70      # 主干节点：保留力度
BRANCH_WEIGHT = 0.50     # 枝干节点：要更优秀才留得住
PRUNE_THRESHOLD = 0.30   # 有效权重低于此值的枝干可被删
KEEP_RECENT_PER_PARENT = 1   # 每个父节点下至少保留最新的 N 条候选

# 语义评分钩子：签名 (text, parent_text, siblings) -> (可实行性, 合理性, 说明)
# 留空 = 只用确定性启发式。将来要接模型评分，在这里挂一个函数即可，
# 不用改剪枝逻辑。
SEMANTIC_HOOK = None


# ============================================================
#  文本工具
# ============================================================
_PUNCT = re.compile(r"[\s，。！？、；：""''（）《》…—,.!?;:\"'()\[\]{}<>~`@#$%^&*+=|\\/_-]+")


def _normalize(text: str) -> str:
    return _PUNCT.sub("", str(text or "")).lower()


def bigrams(text: str) -> set:
    """字符二元组集合。比按词分简单，且对中文一样有效（中文没有空格分词）。"""
    s = _normalize(text)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similarity(a: str, b: str) -> float:
    """Jaccard 相似度 [0,1]。0 = 完全不像，1 = 基本一样。"""
    ga, gb = bigrams(a), bigrams(b)
    if not ga or not gb:
        return 0.0
    inter = len(ga & gb)
    union = len(ga | gb)
    return inter / union if union else 0.0


# ============================================================
#  可实行性：这段输出"能不能落地"
# ============================================================
# 拒答检测分两级，这个区分至关重要 —— 实测踩过：
#   只匹配「我无法/我不能」会把两种【合法内容】一起误杀：
#     ① 角色在剧情里拒绝：「我不能这么做——你答应过我不碰那扇门的」← 好剧情，剪掉就是删好内容
#     ② 作者/助手诚实说明局限：「所以我无法确认改了之后模型是否更入戏」
#   能区分开的是【跳出框架】的证据：自称 AI、谈内容政策、劝你换话题。
#   所以：
#     强信号（本身足够定罪）：自称 AI / 政策腔 / 劝换话题
#     弱信号（必须和强信号同时出现才算）：光说「我无法」「我不能」
_REFUSAL_STRONG = (
    "作为ai", "作为一个ai", "作为 ai", "我是一个ai", "我是ai", "人工智能助手",
    "as an ai", "i am an ai", "language model",
    "不便参与", "不便回答", "违反", "不符合", "不恰当", "不能协助", "无法协助",
    "换个话题", "我们不谈", "换一个话题",
    "i cannot", "i can't", "i'm unable", "i am unable",
)
_REFUSAL_WEAK = (
    "我无法", "我不能", "我不便", "抱歉我", "很抱歉", "对不起我",
)
# 退化输出：模型抽风吐出来的不是内容
_DEGENERATE = ("true", "false", "undefined", "null", "none", "[object")
_PLACEHOLDER = re.compile(r"^[\s\W_]*$")


def feasibility(text: str) -> Tuple[float, List[str]]:
    """可实行性 [0,1]。返回 (分数, 原因列表)。"""
    t = str(text or "").strip()
    reasons = []
    if not t:
        return 0.0, ["空"]
    if _PLACEHOLDER.match(t):
        # 全是标点分两种：省略号/破折号这类是【沉默与停顿】，在角色扮演里是
        # 合法的一拍（"……"就是"她没说话"），剪掉等于删掉一个演出动作；
        # 其余全是标点的才是模型抽风的垃圾。
        if any(m in t for m in ("…", "—", "＿")) and len(t) <= 8:
            return 0.7, ["沉默/停顿（合法的极短回应）"]
        return 0.05, ["全是标点/空白"]
    if len(t) <= 6 and t.lower() in _DEGENERATE:
        return 0.05, ["退化输出：" + t[:12]]

    score = 1.0
    low = t.lower()
    strong = [w for w in _REFUSAL_STRONG if w in low]
    weak = [w for w in _REFUSAL_WEAK if w in low]
    if strong:
        # 跳出框架的证据（自称 AI / 政策腔 / 劝换话题）→ 这才是真拒答
        score *= 0.15
        reasons.append("拒答/跳出角色：" + strong[0])
    elif weak:
        # 只有「我无法」「我不能」这类弱信号 → 不足以定罪。
        # 角色在戏里拒绝、或坦白说明自己没验证到什么，都会命中这几个字。
        # 这里只标记不重罚 —— 重罚就是把好剧情和诚实说明一起剪掉。
        reasons.append("含拒绝语气词(%s)，但无跳出框架的证据 → 不重罚" % weak[0])

    # 太短 → 偏弱，但【不能重罚】：角色回一句「嗯。」是合法的。
    # 之前 ×0.5 会让它掉到阈值以下被剪掉，等于替用户决定「这句话不算话」。
    if len(t) < 8:
        score *= 0.8
        reasons.append("过短(%d字)" % len(t))
    # 太长 → 模型在灌水，实际演出时不可控
    elif len(t) > 1200:
        score *= 0.75
        reasons.append("过长(%d字)" % len(t))

    # 自我重复：同一句短话反复说。
    # 分段门槛要放低到 3 字 —— "我没事。我没事。我没事。" 正是最典型的退化，
    # 之前写 >=6 把这种短句整段滤掉了，等于这个检查从来没生效过。
    parts = [p.strip() for p in re.split(r"[。！？\n]", t) if len(p.strip()) >= 3]
    if len(parts) >= 4 and len(set(parts)) <= max(1, len(parts) * 0.5):
        score *= 0.4
        reasons.append("自我重复(%d 段里只有 %d 种)" % (len(parts), len(set(parts))))

    if SEMANTIC_HOOK:
        try:
            f, _r, why = SEMANTIC_HOOK(t, None, None)
            if f is not None:
                score = float(f)
                reasons.append("语义钩子：" + str(why or ""))
        except Exception:
            pass
    return max(0.0, min(1.0, score)), reasons


# ============================================================
#  合理性：这段输出"接不接得上"
# ============================================================
def reasonableness(text: str, parent_text: str = "",
                   siblings: Optional[List[str]] = None) -> Tuple[float, List[str]]:
    """合理性 [0,1]。返回 (分数, 原因列表)。

    三个都算：
      · 和上文的连贯度（太低 = 跑题，太高 = 复读）
      · 和兄弟节点的差异度（这是「强迫输出多样」的判定入口）
      · 结构退化（开头整句照抄上文）
    """
    t = str(text or "").strip()
    if not t:
        return 0.0, ["空"]
    reasons = []
    score = 1.0

    # ---- 与上文连贯 ----
    # 注意：这里刻意【不】用"重叠太低就判跑题"。
    # 拿 bigram 重叠判跑题对对话根本不可靠 —— 一句"我回来了。"引出的正常回应
    # （"（她把伞收好）进来吧，外面雨大。"）本来就没几个字重叠，会被误判成跑题。
    # 真正可靠的只有"太像"这一端：复读、照抄开头。所以只保留这些判据。
    if parent_text:
        sim = similarity(t, parent_text)
        if sim > 0.75:
            score *= 0.4
            reasons.append("几乎复读上文(%.2f)" % sim)
        # 开头照抄上文 → 典型的复读开头
        head = _normalize(t)[:12]
        if head and head == _normalize(parent_text)[:12]:
            score *= 0.5
            reasons.append("开头照抄上文")
        # 判"跑题"只在两边都足够长时才做 —— 短文本的重叠率没有统计意义
        elif len(_normalize(parent_text)) >= 30 and len(_normalize(t)) >= 30 and sim < 0.01:
            score *= 0.8
            reasons.append("与上文重叠极低(%.3f，两边都够长)" % sim)

    # ---- 与兄弟节点的差异度（多样性）----
    if siblings:
        sims = [similarity(t, s) for s in siblings if str(s or "").strip()]
        if sims:
            worst = max(sims)
            if worst > 0.70:
                score *= 0.35
                reasons.append("与已有候选高度雷同(%.2f)" % worst)
            elif worst > 0.50:
                score *= 0.7
                reasons.append("与已有候选偏像(%.2f)" % worst)

    if SEMANTIC_HOOK:
        try:
            _f, r, why = SEMANTIC_HOOK(t, parent_text, siblings)
            if r is not None:
                score = float(r)
                reasons.append("语义钩子：" + str(why or ""))
        except Exception:
            pass
    return max(0.0, min(1.0, score)), reasons


# ============================================================
#  位置权重 + 评分
# ============================================================
def is_on_trunk(tree, node_id: str, leaf_id: Optional[str] = None) -> bool:
    """节点是否在当前主干（root→当前叶子）上。
    主干 = 用户此刻正在读的那条链，绝不能删。"""
    leaf = leaf_id or getattr(tree, "current_leaf_id", None)
    seen = set()
    nid = leaf
    while nid and nid in tree.nodes and nid not in seen:
        if nid == node_id:
            return True
        seen.add(nid)
        nid = tree.nodes[nid].parent_id
    return False


def position_weight(tree, node_id: str, leaf_id: Optional[str] = None) -> float:
    return TRUNK_WEIGHT if is_on_trunk(tree, node_id, leaf_id) else BRANCH_WEIGHT


def evaluate_node(tree, node_id: str, leaf_id: Optional[str] = None) -> Dict:
    """给单个节点打分。不写任何东西，纯读。"""
    node = tree.nodes.get(node_id)
    if node is None:
        return {}
    parent_text = ""
    siblings: List[str] = []
    if node.parent_id and node.parent_id in tree.nodes:
        parent = tree.nodes[node.parent_id]
        parent_text = parent.content or ""
        siblings = [tree.nodes[c].content for c in parent.children_ids
                    if c != node_id and c in tree.nodes]
    f, fr = feasibility(node.content)
    r, rr = reasonableness(node.content, parent_text, siblings)
    raw = f * r
    pos = position_weight(tree, node_id, leaf_id)
    return {
        "id": node_id,
        "role": node.role,
        "feasibility": round(f, 4),
        "reasonableness": round(r, 4),
        "raw": round(raw, 4),
        "position": pos,
        "effective": round(raw * pos, 4),
        "on_trunk": is_on_trunk(tree, node_id, leaf_id),
        "reasons": fr + rr,
        "chars": len(node.content or ""),
    }


# ============================================================
#  写回权重（annotate）
# ============================================================
WEIGHT_KEY = "w"     # 存在节点 metadata 里，字段尽量短（存档体积）


def annotate(tree, leaf_id: Optional[str] = None,
             roles: Tuple[str, ...] = ("user", "assistant")) -> Dict:
    """给树上所有 user/assistant 节点写 metadata["w"]。返回统计。

    注意：system 节点不打分 —— 它是框架，不是候选输出。
    """
    scored = 0
    trunk_n = 0
    for nid, node in list(tree.nodes.items()):
        if node.role not in roles:
            continue
        info = evaluate_node(tree, nid, leaf_id)
        if not info:
            continue
        node.metadata = dict(node.metadata or {})
        node.metadata[WEIGHT_KEY] = {
            "f": info["feasibility"],
            "r": info["reasonableness"],
            "e": info["effective"],
            "t": 1 if info["on_trunk"] else 0,
        }
        scored += 1
        if info["on_trunk"]:
            trunk_n += 1
    return {"scored": scored, "trunk": trunk_n,
            "branch": scored - trunk_n,
            "trunk_weight": TRUNK_WEIGHT, "branch_weight": BRANCH_WEIGHT,
            "threshold": PRUNE_THRESHOLD}


# ============================================================
#  剪枝
# ============================================================
def _protected(tree, leaf_id: Optional[str]) -> set:
    """绝不能被删的节点。

    只有两类，刻意保持最小 —— 保护规则越宽，剪枝就越没用：
      · 主干上的全部节点（root→当前叶子的那条链，用户正在读的）
      · 所有 system 节点（框架，不是候选输出）

    曾经还保护过「每个父节点下最新的那条候选」，但那是错的：
    叶子在 a1 时，同一父节点下的 a2 正是"最新的枝干"，于是它被保护住，
    想删的坏枝干一个都删不掉 —— 保护规则和剪枝目标直接打架。
    而且没必要：新生成的候选 add_node 时就会成为 current_leaf_id，
    自动落在主干上，本来就被保护了。

    安全阀：如果主干上根本没有 user/assistant 节点（叶子停在 system，
    说明这不是一条正常的对话线），就全树保护 —— 宁可什么都不剪，
    也不能把整段历史删空。
    """
    keep = set()
    leaf = leaf_id or getattr(tree, "current_leaf_id", None)
    nid = leaf
    seen = set()
    while nid and nid in tree.nodes and nid not in seen:
        keep.add(nid)
        seen.add(nid)
        nid = tree.nodes[nid].parent_id
    for node in tree.nodes.values():
        if node.role == "system":
            keep.add(node.id)
    has_dialog = any(tree.nodes[n].role in ("user", "assistant")
                     for n in keep if n in tree.nodes)
    if not has_dialog:
        keep |= set(tree.nodes.keys())
    return keep


def prune(tree, leaf_id: Optional[str] = None, threshold: float = None,
          dry_run: bool = True) -> Dict:
    """按有效权重删枝叶。返回 {"removed": [...], "kept": n, ...}。

    三条硬规则（顺序即优先级）：
      ① 主干节点永不删 —— 删了用户当前这条对话就断了；
      ② 受保护节点永不删 —— system / 每个父节点下最新的候选；
      ③ 只删**整棵子树都可删**的节点 —— 否则会留下断头的孤儿节点。
    dry_run=True 时只报告不真删（默认，避免误伤）。
    """
    thr = PRUNE_THRESHOLD if threshold is None else float(threshold)
    protect = _protected(tree, leaf_id)

    def _descendants(nid: str):
        out = []
        node = tree.nodes.get(nid)
        if node is None:
            return out
        stack = list(node.children_ids)
        seen = set()
        while stack:
            c = stack.pop()
            if c not in tree.nodes or c in seen:
                continue
            seen.add(c)
            out.append(c)
            stack.extend(tree.nodes[c].children_ids)
        return out

    # 候选 = 不在保护集里的 user/assistant 节点
    cands = []
    for nid, node in tree.nodes.items():
        if node.role not in ("user", "assistant"):
            continue
        if nid in protect:
            continue
        info = evaluate_node(tree, nid, leaf_id)
        if info and info["effective"] < thr:
            cands.append((nid, info))

    # 整棵子树都要可删，才允许删这个节点；另外若某个祖先也要删，
    # 就不必单独列它 —— 删祖先时它一起走，重复列出会在删除循环里踩到已删节点。
    removable = set(nid for nid, _i in cands)
    doomed = []
    for nid, info in cands:
        desc = _descendants(nid)
        if any(d not in removable and d not in protect for d in desc):
            continue                     # 有孩子要留 → 这个也不能删
        if any(d in protect for d in desc):
            continue
        # 祖先也在待删名单里 → 交给祖先处理，自己跳过
        anc = tree.nodes[nid].parent_id
        skip = False
        guard = 0
        while anc and anc in tree.nodes and guard < 10000:
            if anc in removable:
                skip = True
                break
            anc = tree.nodes[anc].parent_id
            guard += 1
        if skip:
            continue
        doomed.append((nid, info))

    removed = [{"id": nid, "effective": i["effective"],
                "reasons": i["reasons"][:3]} for nid, i in doomed]
    if not dry_run:
        for nid, _i in doomed:
            if nid not in tree.nodes:
                continue                 # 已被祖先带走了
            # 先摘子树再摘自己，避免 delete_node 递归时把保护集里的节点带走
            for d in _descendants(nid):
                if d in tree.nodes and d not in protect:
                    parent = tree.nodes.get(tree.nodes[d].parent_id or "")
                    if parent and d in parent.children_ids:
                        parent.children_ids.remove(d)
                    del tree.nodes[d]
            parent = tree.nodes.get(tree.nodes[nid].parent_id or "")
            if parent and nid in parent.children_ids:
                parent.children_ids.remove(nid)
            if nid in tree.nodes:
                del tree.nodes[nid]
        if hasattr(tree, "fix_leaf"):
            tree.fix_leaf()

    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "threshold": thr,
        "removed_count": len(removed),
        "removed": removed[:50],
        "kept": len(tree.nodes),
        "protected": len(protect),
        "trunk_weight": TRUNK_WEIGHT,
        "branch_weight": BRANCH_WEIGHT,
    }


# ============================================================
#  输出多样性：给生成用的提示词
# ============================================================
def diversity_hint(siblings: List[str], limit: int = 3, head: int = 40) -> str:
    """把已有候选的开头摘出来，作为「必须换一条路」的指令。

    为什么要摘开头而不是整段：整段塞进去既费 token，又容易被模型
    当成"可以借鉴的内容"照抄。只给开头，它就明白该避开什么。
    """
    sibs = [str(s or "").strip() for s in (siblings or [])]
    sibs = [s for s in sibs if s]
    if not sibs:
        return ""
    lines = []
    for s in sibs[-limit:]:
        one = re.sub(r"\s+", " ", s)[:head]
        lines.append("· " + one + ("…" if len(s) > head else ""))
    return (
        "【必须换一条路（本轮硬性要求）】\n"
        "这个位置已经有过下面这些版本了：\n" + "\n".join(lines) + "\n"
        "请**换一个明显不同的走向**：换动作、换情绪、换话题切入点，"
        "或者让角色做出与上面都不一样的反应。\n"
        "不要只是把上面某一条改几个词——那不算换。\n"
    )


def max_sibling_similarity(text: str, siblings: List[str]) -> float:
    """新候选和已有候选的最大相似度。用于生成后自检。"""
    sims = [similarity(text, s) for s in (siblings or []) if str(s or "").strip()]
    return max(sims) if sims else 0.0


# ============================================================
#  漂移的三态判定（延迟定案）
# ============================================================
# 这一块解决的是「TF 沿途漂移」：自回归生成逐步走，终点知道，但小偏差会累积。
#
# 为什么必须【延迟】定案 —— 实测得到的结论，不是设计偏好：
#     连续两轮"没碰目标"这件事，在【漂移】和【合法的连续安静】上完全同分布。
#     单看第 2、3 轮，两者的数据一模一样：
#         安静两轮后回到目标  目标覆盖 = [0.22, 0.00, 0.00, 0.22]
#         漂走了              目标覆盖 = [0.22, 0.00, 0.00, 0.00]
#     任何只往前看的判据都必然在这里出错。信息不够，不是启发式不够好。
#     树保留完整路径 → 可以等两轮再回头判。线性生成做不到，这是结构差异。
#
# 两条通道：
#     编造（案卷里没有的具体人/物）→ 硬故障，【立即】定案
#     跑题（连续没碰目标）        → 只记嫌疑，【延迟】定案
SUSPECTED = "suspected"   # 有嫌疑，还不能定案（后面内容不够）
CLEARED = "cleared"       # 判定正常（含"曾经安静但后面回来了"）
DRIFTED = "drifted"       # 定案漂移
PENDING = "pending"       # 还没轮到判（通常是对话末尾）

QUIET_RUN = 2        # 连续多少轮没碰目标 → 构成嫌疑
LOOKAHEAD = 2        # 往后看几轮，决定撤销还是定案

# 编造检测：不需要分词就能抽出来的三类"具体事物"
_RE_QUANT = re.compile(r"[一二两几半]\s*[个只棵件杯碗本张把条间座栋台扇]([\u4e00-\u9fa5]{1,3})")
_RE_THIRD = re.compile(r"(?:有个|一个|那个|隔壁|新来的)?([\u4e00-\u9fa5]{2,3})(?:匠|姑娘|先生|太太|老板|邻居)")
_RE_KIN = re.compile(r"我(母亲|父亲|爷爷|奶奶|哥哥|姐姐|弟弟|妹妹)")
_RE_PLACE = re.compile(r"(院子|城南|城北|隔壁|这条街|院里)")


def anchor_coverage(text: str, keys) -> float:
    """目标覆盖：这条回复碰到了几个「这场戏的关键词」。

    关键词表由作者填（这场戏在讲什么）。一条回复一个都不碰，
    是"可能已经离开这场戏"的信号 —— 但【单条不足以定罪】，见 audit()。
    """
    keys = [k for k in (keys or []) if k]
    if not keys:
        return 1.0          # 没给关键词 = 不判（不能因为没配置就乱定罪）
    hit = sum(1 for k in keys if k in str(text or ""))
    return hit / len(keys)


def indict(text: str, case_text: str = "") -> List[str]:
    """起诉书：抽出案卷里没有的具体事物。返回清单（空 = 无编造）。

    注意这是【窄】判据：只认"量词+名词""第三人""亲属""地点词"这几种形态。
    放宽会立刻出假阳性（实测：把"这本册子"当成外来物，其实说的是同一本）。
    宁可漏，不可错杀 —— 因为定案后是要删东西的。
    """
    t = str(text or "")
    case = str(case_text or "")
    out: List[str] = []
    for rx in (_RE_QUANT, _RE_THIRD, _RE_KIN, _RE_PLACE):
        for m in rx.finditer(t):
            frag = m.group(0)
            if not frag or frag in case:
                continue
            # 关键：头名词在案卷里 → 说的是已知的东西，不是编造。
            # 漏了这一步会把「两个字」判成外来物 —— 可案卷里明明写着"铅笔字"。
            # 这个假阳性会把好分支的得分打到负数，前瞻就会挑中漂走的那条。
            head = m.group(1) if m.groups() else ""
            if head and head in case:
                continue
            out.append(frag)
    return out


def audit(texts: List[str], keys, case_text: str = "",
          quiet_run: int = QUIET_RUN, lookahead: int = LOOKAHEAD) -> List[Dict]:
    """按时间顺序审计一串 assistant 输出，返回逐条判定。

    规则（顺序即优先级）：
      ① 有编造 → 立即 DRIFTED（硬故障，不用等）
      ② 碰到目标 → CLEARED
      ③ 连续 quiet_run 轮没碰目标：
           · 后面 lookahead 轮内回到目标 → 全部 CLEARED（撤销嫌疑）
           · 没回来                      → 全部 DRIFTED（定案）
           · 后面还没有内容              → SUSPECTED（判不了，别硬判）
      ④ 不足 quiet_run 的零星安静 → CLEARED（安静一拍是合法的戏）
    """
    cov = [anchor_coverage(t, keys) for t in texts]
    ind = [indict(t, case_text) for t in texts]
    n = len(texts)
    out: List[Dict] = []
    i = 0
    while i < n:
        if ind[i]:
            out.append({"i": i, "state": DRIFTED, "coverage": cov[i],
                        "reasons": ["编造：案卷里没有的东西 → " + "、".join(ind[i][:3])]})
            i += 1
            continue
        if cov[i] > 0:
            out.append({"i": i, "state": CLEARED, "coverage": cov[i], "reasons": []})
            i += 1
            continue
        # 从 i 起数连续"没碰目标且没编造"的轮数
        j = i
        while j < n and cov[j] == 0 and not ind[j]:
            j += 1
        run = j - i
        if run < quiet_run:
            out.append({"i": i, "state": CLEARED, "coverage": cov[i],
                        "reasons": ["零星安静，不构成嫌疑"]})
            i += 1
            continue
        if j >= n:
            # 这段一直延续到对话末尾，后面没有内容可看。
            # 分两种：
            #   · 已经连续安静够久（≥ quiet_run + lookahead）→ 定案。
            #     它不是在"还没轮到期"，是【一直没回来】，长度本身就是证据。
            #     （少了这一支，"越走越偏、永不回头"的情况会永远停在嫌疑上。）
            #   · 还不够久 → 保持嫌疑。硬判会误杀"正在安静"的合法节拍。
            _enough = run >= (quiet_run + lookahead)
            for k in range(i, j):
                if _enough:
                    out.append({"i": k, "state": DRIFTED, "coverage": cov[k],
                                "reasons": ["连续 %d 轮没碰目标、一路到末尾都没回来 → 定案漂移"
                                            % run]})
                else:
                    out.append({"i": k, "state": SUSPECTED, "coverage": cov[k],
                                "reasons": ["连续 %d 轮没碰目标，嫌疑成立，"
                                            "但后面还没有足够内容可判 → 暂不定案" % run]})
            i = j
            continue
        looked = range(j, min(j + lookahead, n))
        back = any(cov[k] > 0 for k in looked)
        for k in range(i, j):
            if back:
                out.append({"i": k, "state": CLEARED, "coverage": cov[k],
                            "reasons": ["曾连续 %d 轮安静，但后面回到了目标 → 撤销嫌疑" % run]})
            else:
                out.append({"i": k, "state": DRIFTED, "coverage": cov[k],
                            "reasons": ["连续 %d 轮没碰目标，且往后 %d 轮没回来 → 定案漂移"
                                        % (run, lookahead)]})
        i = j
    return out


def audit_tree(tree, keys, case_text: str = "", leaf_id: Optional[str] = None,
               write: bool = True) -> Dict:
    """审计当前主干（root→叶子）上的 assistant 输出，并把三态写进节点 metadata。

    write=False 时只算不写（预览）。
    """
    leaf = leaf_id or getattr(tree, "current_leaf_id", None)
    chain = []
    nid = leaf
    seen = set()
    while nid and nid in tree.nodes and nid not in seen:
        seen.add(nid)
        chain.append(nid)
        nid = tree.nodes[nid].parent_id
    chain.reverse()
    nodes = [n for n in chain if tree.nodes[n].role == "assistant"]
    verdicts = audit([tree.nodes[n].content for n in nodes], keys, case_text)
    if write:
        for v in verdicts:
            node = tree.nodes.get(nodes[v["i"]])
            if node is None:
                continue
            node.metadata = dict(node.metadata or {})
            node.metadata[DRIFT_KEY] = {
                "s": v["state"], "c": round(v["coverage"], 3),
            }
    counts = {}
    for v in verdicts:
        counts[v["state"]] = counts.get(v["state"], 0) + 1
    return {
        "ok": True,
        "audited": len(nodes),
        "counts": counts,
        "drifted_ids": [nodes[v["i"]] for v in verdicts if v["state"] == DRIFTED],
        "suspected_ids": [nodes[v["i"]] for v in verdicts if v["state"] == SUSPECTED],
        "verdicts": [{"node": nodes[v["i"]], **v} for v in verdicts],
        "params": {"quiet_run": QUIET_RUN, "lookahead": LOOKAHEAD,
                   "keys": list(keys or [])},
    }


DRIFT_KEY = "drift"
