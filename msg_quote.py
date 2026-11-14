# -*- coding: utf-8 -*-
"""msg_quote.py —— 引用对话：把"回复某条消息"变成模型能看懂的一小段上下文。

为什么单独一层
--------------
引用做错的两种常见方式：
  ① 只在前端画一个引用条，模型根本不知道你在回哪句 —— 那就只是装饰；
  ② 把被引用的整条消息再塞一遍 —— 上下文翻倍，长对话直接爆预算。

这里定的是**口径**：
  · 引用块只带「谁说的 + 摘要」（默认截 200 字，超出加省略号）；
  · 引用是**用户消息的附件**，不是新消息：树里只有一条节点，metadata 里存 quote；
  · 渲染与提示词共用同一份格式化逻辑（前端拿同一个字段自己画，避免两边跑偏）。
"""
from __future__ import annotations

import re

QUOTE_MAX = 200          # 引用摘要最大字数
ELLIPSIS = u"…"


def _clean(text, limit=QUOTE_MAX):
    s = re.sub(r"\s+", " ", (text or "")).strip()
    if len(s) > limit:
        s = s[:limit].rstrip() + ELLIPSIS
    return s


def make_quote(node_id, role, speaker=None, excerpt="", seq=None):
    """构造一条引用。

    node_id：被引用消息在树里的 id（回溯/定位用）
    role   ：'user' | 'assistant'
    speaker：显示名（群聊里是角色名；私聊里可以留空）
    excerpt：被引用消息的正文（会截断）
    """
    body = _clean(excerpt)
    if not body or not node_id:
        return None
    q = {"id": str(node_id), "role": role or "assistant", "excerpt": body}
    if speaker:
        q["speaker"] = str(speaker)
    if seq is not None:
        q["seq"] = seq
    return q


def who(quote):
    """引用块里显示的"谁"：发言者优先，其次按角色。"""
    if quote.get("speaker"):
        return quote["speaker"]
    return u"你" if quote.get("role") == "user" else u"对方"


def format_block(quote):
    """提示词里的引用块（单行、无多余空行，模型不容易把它当新消息）。"""
    if not quote or not quote.get("excerpt"):
        return ""
    return u"〔引用 %s：%s〕" % (who(quote), _clean(quote["excerpt"]))


def apply_quote(content, quote):
    """把引用块接到用户消息前面。没有引用就原样返回（零成本）。"""
    block = format_block(quote)
    if not block:
        return content or ""
    return block + u"\n" + (content or "")


def strip_quote(content):
    """反解：从带引用的文本里剥掉引用块（生成候选、二次编辑时用）。"""
    if not content:
        return ""
    return re.sub(r"^〔引用 [^〕]{1,120}〕\n", "", content, count=1)


def from_metadata(metadata):
    """从树节点 metadata 里取引用（老数据没有这个键，返回 None）。"""
    if not isinstance(metadata, dict):
        return None
    q = metadata.get("quote")
    if not isinstance(q, dict) or not q.get("excerpt"):
        return None
    return q
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌