# -*- coding: utf-8 -*-
"""玩家角色卡 → 系统提示里的人设块（乙女 / 梦女梦男向优化）。

两条反馈一起满足：
    ① "现在多少有点侧重于 GAL 玩家了" → 称呼/代词/视角/关系要在提示里；
    ② "原有的陪伴感很强" → **这份提示不能把模型变成念规则的机器**。

所以这里写成**一段温热的介绍**，不是规则清单：
    · 不出现"性别：""外貌："这种字段标签，也不带编号；
    · 没填的字段整行不出现（轻卡保持轻，陪伴感不被稀释）；
    · 代词/称呼用"她会…""她喜欢被叫作…"这种叙述口吻；
    · 唯一那句边界写成请求（"台词留给她自己说"），不写禁令；
    · 禁忌写成"她不太想被写到的：…"，是她的偏好，不是审核清单。

验：tests/test_player_persona.py（含"温度守卫"：否定句 ≤2、不许出现字段式冒号）
"""
from __future__ import annotations

from typing import Any, Dict, List

# 视角 → 一句轻提示（不写成规则条款）。s<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌econd 是乙女/梦向的默认（"你"）。
PERSPECTIVE_HINT = {
    "second": "（你写她的时候，用「你」称呼她。）",
    "first": "（她以「我」自称；她的台词仍由她自己说。）",
    "third": "（叙述里可以用第三人称写她。）",
}


def _text(persona: Dict[str, Any], *keys: str) -> str:
    """按顺序取第一个非空字符串字段（兼容旧键名）。"""
    for k in keys:
        v = persona.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _list(persona: Dict[str, Any], *keys: str) -> List[str]:
    """取列表型字段（字符串按标点/换行拆开也接受）。"""
    for k in keys:
        v = persona.get(k)
        if isinstance(v, str) and v.strip():
            parts = [x.strip() for x in v.replace("，", ",").replace("、", ",").replace("\n", ",").split(",")]
            return [x for x in parts if x]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
    return []


def persona_block(persona: Dict[str, Any] | None) -> str:
    """把玩家角色卡拼成系统提示里的一小段；没有卡就返回空串（旧行为不变）。"""
    if not isinstance(persona, dict) or not persona:
        return ""

    name = _text(persona, "name", "char_name") or "玩家"
    pronoun = _text(persona, "pronoun", "pron")
    address = _text(persona, "address", "call_me")
    relationship = _text(persona, "relationship", "relation")
    perspective = _text(persona, "perspective", "pov") or "second"
    gender = _text(persona, "gender")
    identity = _text(persona, "identity", "occupation")
    appearance = _text(persona, "appearance")
    background = _text(persona, "background", "description")
    speech = _text(persona, "speech_style", "speech")
    personality = _list(persona, "personality")
    taboo = _list(persona, "taboo", "boundaries", "禁忌")

    # 第一句像"介绍一个人"，不是"填表"：名字后面自然接性别/身份
    intro = name
    if gender and identity:
        intro += "，%s，%s" % (gender, identity)
    elif gender:
        intro += "，%s" % gender
    elif identity:
        intro += "，%s" % identity

    lines = ["", "【正在和你说话的人】", intro + "。"]
    if appearance:
        lines.append("%s。" % appearance.rstrip("。"))
    traits = "、".join(personality)
    if traits and speech:
        lines.append("%s，%s。" % (traits, speech.rstrip("。")))
    elif traits:
        lines.append("%s。" % traits)
    elif speech:
        lines.append("%s。" % speech.rstrip("。"))
    if background:
        lines.append("%s。" % background.rstrip("。"))
    if relationship:
        lines.append("你们现在是「%s」。" % relationship)
    if address:
        lines.append("她喜欢被叫作「%s」。" % address)
    if pronoun:
        lines.append("提到她的时候，用「%s」。" % pronoun)

    lines.append(PERSPECTIVE_HINT.get(perspective, PERSPECTIVE_HINT["second"]))
    # 边界只有一句，写成请求：把台词的份量还给用户
    lines.append("她的台词和心事，留给她自己说。")
    if taboo:
        lines.append("她不太想被写到的：%s。" % "、".join(taboo))
    return "\n".join(lines) + "\n"
