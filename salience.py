# -*- coding: utf-8 -*-
"""salience.py —— 记忆的「清晰度」：让保存下来的历史有损、有选择、且不可反推。

为什么要有这个文件
------------------
原来的 _fit_budget 是【按长度从新到旧填，填满就断】：
最近的全量进，更旧的全量压成摘要。中间那个状态 ——
「有的记得清清楚楚、有的完全没了、有的只剩模糊印象」—— 根本不存在。

而人的记忆恰恰长在中间那个状态上。记忆是【有损】的，而且丢失【不受控】：
注意力有时候不在，那段就没了。

所以这个模块干的是：给每条历史算一个清晰度，近窗全留，
远窗按清晰度抽几条，剩下的真的不要。

一条硬约束（用户早先提过）
--------------------------
遗忘必须【不可建模】。如果规则是"她忘了 20 条以前的"，用户很快能反推出规律，
那就不像人。做法：每个节点带一个【隐藏衰减率】，由 HASH_KEY 和节点 id 派生 ——
它是确定性的（同样的存档永远得到同样的结果，可测试、可复现），
但对用户不可见、不可猜。

这就是「不是随机，而是足够不一致以致无法推断」。

单位约定（踩过的坑）
--------------------
decay_per_day 的单位是【每天】，dt 的单位是【秒】。所以是
    dt / 86400.0
漏掉 /86400 的话，几秒钟就会把记忆全忘光。
"""
import hashlib
import threading
import time

# ---------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------- 参数
HASH_KEY = "dick-memory-v1-7f3a9c2e"

# 衰减率的标定方式：先定【想要的记忆寿命】，再反推参数。标定过程记下来，
# 免得以后有人凭感觉调：
#   第一版 DECAY_MIN=0.08 / DECAY_MAX=0.60、阈值=1.0
#     → 实测中位衰减率 0.264，平淡内容【半天】就掉到阈值以下。
#       角色会把两天前的所有事忘掉 —— 那不叫记忆，叫失忆。
#   第二版 阈值降到 0.35、衰减带收窄
#     → 平淡内容约 7 天、带情绪约 13 天到阈值。这个像人。
# 阈值单独说一下：1.0 太苛刻，因为【基线就是 1.0】—— 意思是"只有带情绪、
# 够长、或被重新提起过的才活得下去"。基线卡在阈值上不是判据，是bug。
DECAY_MIN = 0.02          # 最慢：每天损失 2%（几乎不忘）
DECAY_MAX = 0.20          # 最快：每天损失 20%
DECAY_PORTION = 0.22      # 只有这一部分节点是"快忘"的（健忘的人也只有一部分事忘得快）

EMOTION_WORDS = (
    "！", "？", "…", "笑", "哭", "生气", "喜欢", "爱", "怕", "疼", "想", "别",
    "第一次", "对不起", "谢谢", "等我", "再见", "答应", "永远", "讨厌", "恨",
)
EMOTION_PER_WORD = 0.15
EMOTION_MAX = 1.5

MENTION_BOOST_MAX = 2.0   # 被重新提起过 → 记得更牢（上限）
MENTION_WINDOW_DAYS = 7.0 # 提起的加成只在这段时间内有效

LONG_MSG_CHARS = 200      # 超过这个长度算"说了一大段"，本身就更值得记
KEEP_THRESHOLD = 0.35     # 清晰度低于这个值 = 已经忘了

# 记忆年龄与软件时间流速的关系。
#   "real" —— 按【现实】时间衰老（默认）。倍率不影响记忆寿命：
#             平淡内容约 10 天、带情绪约 15 天，先调哪个倍率都一样。
#   "flow" —— 按【那边】的时间衰老（年龄 × 倍率）。
#             实测代价极大：60 倍 → 平淡内容 4.7 小时；720 倍 → 23 分钟；
#             86400 倍 → 11 秒。等于把"有损记忆"变成"完全失忆"，
#             角色变成金鱼。所以默认不用。
# 想体验"她的日子比我快所以我忘得快"就改成 "flow"；
# 但注意那和"角色要记得住事情"是不可兼得的。
AGE_MODE = "real"

_lock = threading.Lock()
_mention_cache = {}


def hidden_decay(node_id):
    """该节点自己的隐藏衰减率（每天）。

    由 HASH_KEY 和 id 派生：确定性，但用户从外部看不出规律。
    只有约 DECAY_PORTION 的节点是快忘的 —— 如果所有节点一样快，
    "为什么这条记得那条忘了"就变得可预测了，那正是要避免的。
    """
    h = hashlib.sha256((HASH_KEY + "|" + str(node_id or "")).encode("utf-8")).digest()
    u = int.from_bytes(h[:8], "big") / float(1 << 64)      # [0,1)
    if u < DECAY_PORTION:
        # 快忘档：落在 DECAY_MAX 附近
        lo = DECAY_MAX * 0.6
        return lo + (DECAY_MAX - lo) * (u / DECAY_PORTION)
    # 慢忘档：铺满 DECAY_MIN..DECAY_MAX*0.6
    v = (u - DECAY_PORTION) / (1.0 - DECAY_PORTION)
    return DECAY_MIN + (DECAY_MAX * 0.6 - DECAY_MIN) * v


def emotion(text):
    """情绪强度 [0, EMOTION_MAX]。用便宜的形态信号，不调模型。"""
    if not text:
        return 0.0
    n = sum(1 for w in EMOTION_WORDS if w in text)
    return min(EMOTION_MAX, n * EMOTION_PER_WORD)


def mention_boost(node_id, now=None):
    """被重新提起带来的加成：提得越多记得越牢，但只在一段时间内有效。"""
    if not node_id:
        return 0.0
    now = now if now is not None else time.time()
    with _lock:
        hits = list(_mention_cache.get(node_id, ()))
    total = 0.0
    for t in hits:
        age_days = max(0.0, (now - t) / 86400.0)
        if age_days <= MENTION_WINDOW_DAYS:
            total += 1.0 - age_days / MENTION_WINDOW_DAYS
    return min(MENTION_BOOST_MAX, total)


def mark_mentioned(node_id, now=None):
    """记一次"被提起"。裁剪时对留下的节点调用。"""
    if not node_id:
        return
    with _lock:
        _mention_cache.setdefault(node_id, []).append(
            now if now is not None else time.time())


def reset_mentions():
    """清空提起记录（换角色/新会话时用）。"""
    with _lock:
        _mention_cache.clear()


def salience(message, now=None, scale=None):
    """一条消息的清晰度。> KEEP_THRESHOLD = 还记得。

    message 需要 message["_node_id"]（裁剪时不进 API 载荷，所以不影响发送）。
    没有 _node_id 的消息返回 0（无从判断，交给调用方兜底保留）。

    scale = 软件时间流速（世界那边比现实快多少倍）。

    默认 AGE_MODE="real" 时 scale 被【忽略】—— 记忆按现实时间衰老，
    所以倍率怎么调，记忆寿命都一样（约 10 天）。这是刻意的：
    实测把年龄乘上倍率会让 720 倍下的记忆只活 23 分钟，角色变金鱼。
    改成 AGE_MODE="flow" 才会按那边的时间衰老。
    """
    if not isinstance(message, dict):
        return 0.0
    nid = message.get("_node_id")
    if not nid:
        return 0.0
    now = now if now is not None else time.time()
    text = str(message.get("content") or "")

    s = 1.0
    s += emotion(text)
    if len(text) > LONG_MSG_CHARS:
        s += 0.30
    s += mention_boost(nid, now)

    # 时间衰减：单位是秒，除以 86400 换成"天"。
    try:
        elapsed = max(0.0, now - float(message.get("_ts") or now))
    except (TypeError, ValueError):
        elapsed = 0.0
    if scale is not None and AGE_MODE == "flow":
        try:
            elapsed *= float(scale)
        except (TypeError, ValueError):
            pass
    age_days = elapsed / 86400.0
    s *= (1.0 - hidden_decay(nid)) ** age_days
    return s


def select(messages, recent_window, budget_tokens, est_tokens,
           always_keep=None, now=None, scale=None):
    """挑出这次要放进上下文的历史。

    规则：
      · 最近 recent_window 条 → 无条件留（对话连贯性）
      · 更旧的 → 按清晰度从高到低填，清晰度低于阈值的【不填】（那就是忘了）
    清晰度高的旧消息可以挤在低清晰度的新消息前面 —— 这正是现实里会发生的事。

    返回 {"kept": [...], "recalled": [...], "forgotten": [...], "dropped": [...]}
      recalled  = 从远窗里被想起来的（本来会被丢掉的）
      forgotten = 远窗里清晰度太低、已经忘了的
      dropped   = 远窗里清晰度够、但预算塞不下的（下次还有机会）
    调用方只应对 dropped 走摘要 —— forgotten 是"真的忘了"，不该被摘要救回来。
    """
    if not messages:
        return {"kept": [], "recalled": [], "forgotten": [], "dropped": []}
    always_keep = set(always_keep or [])
    now = now if now is not None else time.time()
    n = len(messages)
    recent_window = max(0, int(recent_window))
    recent_start = max(0, n - recent_window)

    head, older = [], []
    for i, m in enumerate(messages):
        if i >= recent_start or i in always_keep or i == n - 1:
            head.append(m)
        else:
            older.append((i, m))

    head_tokens = sum(est_tokens(m.get("content", "")) for m in head)
    remaining = budget_tokens - head_tokens

    scored = []
    for i, m in older:
        scored.append((salience(m, now, scale), i, m))
    scored.sort(key=lambda x: (-x[0], x[1]))     # 清晰度高的优先，同分按原序

    recalled, forgotten, dropped = [], [], []
    for s, i, m in scored:
        if s < KEEP_THRESHOLD:
            forgotten.append((i, m, s))
            continue
        t = est_tokens(m.get("content", ""))
        if t <= remaining:
            recalled.append((i, m, s))
            remaining -= t
        else:
            dropped.append((i, m, s))

    # 按原始顺序还原，保证对话顺序不乱
    kept = sorted(recalled, key=lambda x: x[0])
    kept_msgs = [m for _, m, _ in kept] + head
    return {
        "kept": kept_msgs,
        "recalled": [{"i": i, "score": round(s, 4),
                      "content": str(m.get("content") or "")[:40]}
                     for i, m, s in kept],
        "forgotten": [{"i": i, "score": round(s, 4),
                       "content": str(m.get("content") or "")[:40]}
                      for i, m, s in forgotten],
        "dropped": [m for _, m, _ in dropped],
    }
