# -*- coding: utf-8 -*-
"""人物卡的 N 种模式：**GAL 攻略** 与 **乙女·梦向** 分开，各走各的默认。

为什么分开（用户反馈的原话）：
    "人物卡可以设定为 N 个模式，两个分开，没有备注，但是陪伴感强需要保留，
     女性疑似需要更多的情感反馈。"
    · N 个模式：模式是可扩展的表，不是 if/else 堆出来的；
    · 两个分开：GAL 是"我在攻略谁"，乙女/梦向是"我们两个人的故事"——
      同一个人物卡，两种演法**不该共用一套默认**（GAL 要钩子、要推进；
      乙女要留白、要情绪到位）；
    · 没有备注：模式是**一个字段**，不需要用户写一段说明去解释"我要什么感觉"；
    · 陪伴感必须保留：模式只调整"怎么演"，绝不削减"在场感"；
    · 女性疑似需要更多情感反馈：情感反馈有独立开关与强度档，
      默认对乙女/梦向开"高"，对 GAL 开"轻"——但都**不关掉**。

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
        "perspective": "second",
        "emotion": "light",
        "hints": [
            "【这一场怎么演】",
            "你在追求对方，节奏由你带，一次只推进一小步。",
            "每轮留一个能接话的钩子：一句问话、一个动作、一个还没说完的念头。",
        ],
    },
    "otome": {
        "label": "乙女 · 梦向",
        "perspective": "second",
        "emotion": "high",
        "hints": [
            "【这一场怎么演】",
            "这是你们两个人的故事，不是一场攻略。",
            "先把「此刻」写实：语气、小动作、那句没说出口的话。",
            "推进可以慢，情绪要到位；一次只做一件事，留白给她。",
        ],
    },
    "trpg": {
        "label": "跑团",
        "perspective": "third",
        "emotion": "light",
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
    """这个模式的默认视角/情感强度（前端切模式时可用它预填表单）。"""
    mid = resolve_mode(mode)
    if not mid:
        return {}
    spec = MODES[mid]
    return {"mode": mid, "perspective": spec["perspective"], "emotional": spec["emotion"],
            "label": spec["label"]}
