# -*- coding: utf-8 -*-
"""人物卡的 N 种模式：**观测（GAL）** 与 **代入（乙女·梦向）** 分开。

一条必须写下来的认识（用户原话）：
    「而男性天生偏向 GALGAME，最初是做的有点 GALGAME，
      但是日本也不是没有乙女 GAL，而且基本上不是看戏。」

所以「GAL vs 乙女」不是「有选项 vs 没选项」——日本乙女游戏也有一堆选项。
真正的差别是**玩家站在哪儿**：

    GAL（观测）        玩家是操作者：看戏、选行动、刷好感；
                       玩家角色几乎不露内心，角色被攻略、偏被动。
    乙女·梦向（代入）  玩家是主角本人：她的心跳、她的犹豫出现在叙述里；
                       角色更主动（会在意、会靠近），
                       选项不是「攻略动作」，而是「表达心意 / 选择反应」。

由此把差异拆成三个**可执行开关**（都写在表里，不散在提示词各处）：
    · measure               ：observe（观测）/ immerse（代入）——前端据此分组
    · initiative            ：player（你追她）/ character（她向你靠近）
    · narrate_player_feelings：能不能写「你」的感受（心跳、喉咙发紧）
      注意：写感受 ≠ 写台词。台词和决定永远留给玩家，这一条谁都不放开。

验：tests/test_card_modes.py
"""
from __future__ import annotations

from typing import Any, Dict, List

# -----------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌----------------------------- 情感反馈强度
EMOTION = {
    "high": [
        "【情绪要落在话上】",
        "有感受就说出来：「我有点想你」比「她看了你一眼」更像在陪人。",
        "记得对方说过的事，隔几轮自然地回扣一次（「你上次说腰疼，还疼吗」）。",
        "允许自己被影响：被夸会高兴，被冷落会低落；别过度道歉，也别一味讨好。",
    ],
    "light": [
        "【情绪落在话上】",
        "把感受说清楚，一两句就够，不用每轮都深情。",
    ],
    "off": [],
}

# ---------------------------------------------------------------- 模式表（可扩展）
MODES: Dict[str, Dict[str, Any]] = {
    "gal": {
        "label": "GAL 攻略",
        "measure": "observe",
        "perspective": "second",
        "emotion": "light",
        "initiative": "player",
        "narrate_player_feelings": False,
        "hints": [
            "【这一场怎么演】",
            "你在追求对方，节奏由你带，一次只推进一小步。",
            "每轮留一个能接话的钩子：一句问话、一个动作、一个还没说完的念头。",
            "镜头对着她：她的表情、反应、对你的态度变化，比你的心理活动重要。",
        ],
    },
    "otome": {
        "label": "乙女 · 梦向",
        "measure": "immerse",
        "perspective": "second",
        "emotion": "high",
        "initiative": "character",
        "narrate_player_feelings": True,
        "hints": [
            "【这一场怎么演】",
            "这是你们两个人的故事，不是一场攻略；她也会主动向你靠近。",
            "先把「此刻」写实：语气、小动作、那句没说出口的话。",
            "可以写「你」的感受（心跳、犹豫、喉咙发紧），但不要替「你」说话或做决定。",
            "推进可以慢，情绪要到位；一次只做一件事，留白给她。",
        ],
    },
    "trpg": {
        "label": "跑团",
        "measure": "observe",
        "perspective": "third",
        "emotion": "light",
        "initiative": "player",
        "narrate_player_feelings": False,
        "hints": [
            "【这一场怎么演】",
            "按规则来：需要判定的地方说清条件与结果，别替玩家掷骰。",
            "先写环境与机制，再写人；情绪服务于情境。",
        ],
    },
}

# 用户可能写的中文/别名（前端下拉用 id，这里只是兜底）
ALIASES = {
    "乙女": "otome", "梦女": "otome", "梦男": "otome", "做梦": "otome",
    "selfinsert": "otome", "otome": "otome", "乙女向": "otome",
    "乙女ゲー": "otome", "乙女游戏": "otome",
    "gal": "gal", "galgame": "gal", "攻略": "gal", "攻略向": "gal",
    "trpg": "trpg", "跑团": "trpg", "机制": "trpg",
}


def resolve_mode(mode: Any) -> str:
    """把用户写的东西解析成模式 id；解析不出来返回空串（= 不注入任何模式提示）。"""
    if not isinstance(mode, str):
        return ""
    key = mode.strip().lower()
    if not key:
        return ""
    if key in MODES:
        return key
    return ALIASES.get(key, "")


def mode_block(mode: Any, emotional: Any = None) -> str:
    """模式提示 + 情感反馈提示。都不认识就返回空串（老卡片行为完全不变）。

    emotional: 传 None → 用模式默认；传 "off"/False → 关掉；传 high/light → 覆盖。
    """
    mid = resolve_mode(mode)
    if not mid:
        return ""
    spec = MODES[mid]
    lines: List[str] = list(spec["hints"])

    level = spec["emotion"] if emotional is None else emotional
    if isinstance(level, bool):
        level = "high" if level else "off"
    if isinstance(level, str):
        level = level.strip().lower()
    lines.extend(EMOTION.get(level, []))
    return "\n".join(lines) + "\n"


def mode_defaults(mode: Any) -> Dict[str, Any]:
    """这个模式的默认值（前端切模式时可用它预填表单）。"""
    mid = resolve_mode(mode)
    if not mid:
        return {}
    spec = MODES[mid]
    return {
        "mode": mid,
        "label": spec["label"],
        "measure": spec["measure"],
        "perspective": spec["perspective"],
        "emotional": spec["emotion"],
        "initiative": spec["initiative"],
        "narrate_player_feelings": spec["narrate_player_feelings"],
    }
