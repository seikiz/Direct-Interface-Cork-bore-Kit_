# -*- coding: utf-8 -*-
"""mem_policy.py —— 上下文策略：窗口多大、什么时候压缩、哪些消息不算数。

为什么单独一层
--------------
现在 `core_prompt._fit_budget` 只有一道闸：**token 预算**。它能防爆，但防不住两件事：
  ① 长段落把预算吃满时，前面几十条短消息被整段丢掉（丢的往往是"刚发生的事"）；
  ② 没有"够久没动就整理一次"的机制，摘要永远是"被挤掉才写"。

所以这里补的是**条数闸**与**时机**，token 预算仍留在原地当最后一道保险：

  窗口     每轮只送最近 24~36 条（按场景取，默认 30），更早的进压缩
  阈值     私聊 32 条、群聊 48 条 —— 群聊人多话密，压太早角色会失忆
  空闲     距上次压缩超过 2 小时，且有新内容，就整理一次
  失败消息 发送失败/未送达的不进上下文（也不计入条数）

场景判定
--------
本层不猜场景，由调用方传 mem_scene 的 'private' / 'group'。
默认规则（供调用方参考）：选中角色数 > 1 → group，否则 private。
"""
from __future__ import annotations

WINDOW_MIN = 24
WINDOW_MAX = 36
WINDOW_DEFAULT = 30
THRESHOLDS = {"private": 32, "group": 48}
IDLE_SECONDS = 2 * 3600          # 2 小时
FAIL_STATES = ("failed", "error", "aborted", "cancelled", "unsent")


def scene_for(selected_roles):
    """默认判定：多选 = 群聊，单选 = 私聊。调用方可以不采用这个规则。"""
    n = len(selected_roles or ())
    return "group" if n > 1 else "private"


def is_failed(msg):
    """消息是否算"没送出去"。

    认三种记法：布尔字段 failed、状态字符串、以及带 error 且没有正文的。
    """
    if not isinstance(msg, dict):
        return False
    if msg.get("failed") is True:
        return True
    state = msg.get("status") or msg.get("state")
    if isinstance(state, str) and state.lower() in FAIL_STATES:
        return True
    if msg.get("error") and not (msg.get("content") or "").strip():
        return True
    return False


def effective(messages):
    """过滤掉没送出去的消息。返回新列表，不改原对象。"""
    return [m for m in (messages or []) if not is_failed(m)]


def window_size(scene, requested=None):
    """窗口条数：夹在 24~36 之间；群聊默认取大一点。"""
    if requested is None:
        requested = WINDOW_DEFAULT + (2 if scene == "group" else 0)
    try:
        n = int(requested)
    except (TypeError, ValueError):
        n = WINDOW_DEFAULT
    return max(WINDOW_MIN, min(WINDOW_MAX, n))


def threshold_for(scene):
    return THRESHOLDS.get(scene, THRESHOLDS["private"])


def needs_compress(count, scene):
    """按条数判断要不要压。"""
    return count > threshold_for(scene)


def needs_idle_compress(last_compress_ts, now, has_new=True):
    """距上次压缩超过 2 小时且这期间有新内容 → 整理一次。"""
    if not has_new:
        return False
    if last_compress_ts in (None, 0):
        return True
    try:
        return (float(now) - float(last_compress_ts)) >= IDLE_SECONDS
    except (TypeError, ValueError):
        return False


def split(messages, scene, requested=None):
    """把消息切成 (window, dropped)。

    window  —— 这一轮真正送进上下文的部分（最后 N 条）
    dropped —— 更早的部分（要送进摘要/归档的原材料）
    入参里的失败消息直接丢弃，不进任何一边。
    """
    msgs = effective(messages)
    n = window_size(scene, requested)
    if len(msgs) <= n:
        return msgs, []
    return msgs[-n:], msgs[:-n]


def plan(messages, scene, last_compress_ts=None, now=None, requested=None):
    """一次性给出"这一轮该怎么处理历史"的决定（纯计算，无副作用）。

    返回 window/dropped/compress/reason/kept/dropped_count。
    """
    msgs = effective(messages)
    win, dropped = split(msgs, scene, requested)
    reasons = []
    if dropped:
        reasons.append("超出窗口 %d 条（丢弃 %d）" % (window_size(scene, requested), len(dropped)))
    if needs_compress(len(msgs), scene):
        reasons.append("总数 %d 超过 %s 阈值 %d" % (len(msgs), scene, threshold_for(scene)))
    if now is not None and needs_idle_compress(last_compress_ts, now, bool(msgs)):
        reasons.append("距上次压缩超过 2 小时")
    return {
        "scene": scene,
        "window": win,
        "dropped": dropped,
        "kept": len(win),
        "dropped_count": len(dropped),
        "compress": bool(reasons),
        "reason": "；".join(reasons),
    }


def should_send(msg):
    """是否把这条消息放进上下文（失败的不放）。"""
    return not is_failed(msg)
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌