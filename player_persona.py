# -*- coding: utf-8 -*-
"""玩家角色卡 → 系统提示里的人设块（乙女 / 梦女梦男向优化的核心）。

为什么单独成文件：
  ① DICK_core.py 有行数棘轮（2991，只许降），提示词拼装从里面搬出来正好减行；
  ② 这段逻辑要能被单测直接调用（tests/test_player_persona.py），不必起整个 Core。

**这次到底改了什么**（用户反馈「太 GAL 了，乙女/梦女向不够」）：
  · 以前只写 name/background/appearance/speech/personality/notes，
    然后一句"请以「X」称呼用户" —— 模型很容易把玩家写成第三人称、或者写成"她"。
  · 现在把"**怎么称呼、用什么代词、什么视角、和角色什么关系、哪些不能写**"都显式写进提示：
      - 视角：second（"你"）/ first（"我"）/ third（ta 的代词）——乙女与梦向默认第二人称；
      - 称呼：角色该叫你什么（宝贝/学长/名字…）；
      - 代词：她/他/ta，缺省用"你"，**绝不擅自按角色性别反推**；
      - 关系：你们现在是什么关系（恋人/青梅/主从…），决定尺度与亲密度；
      - 禁忌：明确"不要写"的东西（雷点）。
  · 这些都是**可选字段**：老存档没有就照旧，不改变既有行为。
"""
from __future__ import annotations

from typing import Any, Dict, List

# 视角 → 给模型的写法要求。seco<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌nd 是乙女/梦向的默认（"你"）。
PERSPECTIVE_RULES = {
    "second": "用第二人称「你」指代玩家角色（像对着本人说话），不要改用第三人称。",
    "first": "玩家角色以第一人称「我」行动；你（AI）仍是角色本人，不要替玩家写「我」的台词。",
    "third": "叙述里可以用第三人称指代玩家角色，但代词必须用指定的那个，不要自行改成别的。",
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
    """把玩家角色卡拼成系统提示里的一段；没有卡就返回空串（不影响旧行为）。"""
    if not isinstance(persona, dict) or not persona:
        return ""

    name = _text(persona, "name", "char_name") or "玩家"
    pronoun = _text(persona, "pronoun", "pron") or ""
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

    out = ["", "【玩家角色（由用户本人扮演，不是你的角色）】", "名字：%s" % name]
    if gender:
        out.append("性别：%s" % gender)
    if identity:
        out.append("身份：%s" % identity)
    if appearance:
        out.append("外貌：%s" % appearance)
    if personality:
        out.append("性格：%s" % "、".join(personality))
    if speech:
        out.append("说话风格：%s" % speech)
    if background:
        out.append("背景：%s" % background)
    if relationship:
        out.append("与你的关系：%s（亲密度与尺度以此为准）" % relationship)

    # 称呼与代词：乙女/梦女最在意的两件事
    if address:
        out.append("称呼：请直接称呼 TA 为「%s」。" % address)
    if pronoun:
        out.append("代词：提到 TA 时用「%s」，不要擅自换成别的性别代词。" % pronoun)

    rule = PERSPECTIVE_RULES.get(perspective, PERSPECTIVE_RULES["second"])
    out.append("视角：%s" % rule)
    out.append("边界：不要替 %s 发言、不要替他做决定；他的台词与动作留给用户自己写。" % name)
    if taboo:
        out.append("禁忌（不要写的方向）：%s" % "、".join(taboo))
    return "\n".join(out) + "\n"
