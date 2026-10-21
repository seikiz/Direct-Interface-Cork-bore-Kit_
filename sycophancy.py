# -*- coding: utf-8 -*-
"""反讨好守卫：她不必每轮都顺着说。

为什么需要（用户反馈）：
    「讨好反馈真的没啥用。」
讨好让反馈通道失效：无论你说什么都"对对对"，你就无法通过自己的行为影响关系，
这段关系也就没有重量。更糟的是，模型会越夸越空——**甜得没有信息量**。

做法（很克制，只做"这一轮"）：
  看最近几轮 AI 回复里的三种信号：
    · 连续同意：连着一轮轮都是"好的/当然/你说得对/确实"
    · 过度道歉：一句回复里多次"对不起/抱歉/是我不好"
    · 每轮都夸：几乎每轮都有"你真…/好厉害/太棒了"
  触发就注入一句**单轮**提醒：这一轮给点自己的看法，必要时可以不认同。
  不写进历史、不写进人设——它不是规则，是一次"别太顺"的提醒。

不做的事：
  · 不检测用户说什么（不评判用户）；
  · 不会因此变冷淡（陪伴感优先，只是别一味附和）。

验：tests/test_sycophancy_guard.py
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

AGREE = ("好的", "当然", "没问题", "你说得对", "确实", "是啊", "都听你的", "可以呀", "嗯嗯")
APOLOGY = ("对不起", "抱歉", "是我不好", "我错了", "别生气", "原谅我")
PRAISE = ("你真", "你好厉害", "太棒了", "好厉害", "真厉害", "你最好了", "真聪明")


def _texts(chain: List[Any]) -> List[str]:
    """从 chain（节点 dict 或对象）里取出 AI 回复文本。"""
    out = []
    for n in chain or []:
        if isinstance(n, dict):
            if n.get("role") == "assistant":
                out.append(str(n.get("content") or ""))
        else:
            if getattr(n, "role", "") == "assistant":
                out.append(str(getattr(n, "content", "") or ""))
    return [t for t in out if t.strip()]


def detect(turns: List[str]) -> Dict[str, Any]:
    """看最近几轮：连续同意次数 / 道歉命中数 / 夸奖轮数。"""
    turns = [t for t in (turns or []) if t and t.strip()]
    streak = 0
    for t in reversed(turns):
        if any(k in t for k in AGREE):
            streak += 1
        else:
            break
    apologies = sum(sum(t.count(k) for k in APOLOGY) for t in turns[-3:])
    praise_turns = sum(1 for t in turns[-3:] if any(k in t for k in PRAISE))
    return {"turns": len(turns), "agree_streak": streak,
            "apologies": apologies, "praise_turns": praise_turns,
            "praise_every_turn": len(turns) >= 3 and praise_turns >= len(turns[-3:])}


def guard_text(chain_or_turns: Any) -> str:
    """需要就返回一段单轮提醒；不需要返回空串（不改变正常对话）。"""
    turns = _texts(chain_or_turns) if chain_or_turns and not isinstance(chain_or_turns[0], str) else list(chain_or_turns or [])
    stats = detect(turns)
    reasons = []
    if stats["agree_streak"] >= 3:
        reasons.append("连着 %d 轮都顺着对方" % stats["agree_streak"])
    if stats["apologies"] >= 3:
        reasons.append("道歉说得太密")
    if stats["praise_every_turn"]:
        reasons.append("几乎每轮都在夸")
    if not reasons:
        return ""

    return (
        "\n【这一轮别一味顺着说】\n"
        "%s。人是有立场的：可以不同意、可以说\"我不太想\"、也可以只是安静一会儿。\n"
        "不需要变冷，只需要让\"你说的每句话都只会被同意\"这件事不成立——\n"
        "她可以有自己的偏好和一点小固执。\n" % "；".join(reasons)
    )
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌