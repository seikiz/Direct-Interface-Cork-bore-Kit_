# -*- coding: utf-8 -*-
"""text_shield.py —— 用户输入的"括号保护"。

现象（用户报的 bug）：
    玩家打 `(摸摸头)没事啦`，发出去之后气泡里变成 `摸摸头没事啦`
    —— 括号被吃掉了，里面的字还在。

为什么专门做一个模块：
    "括号"是最容易被各种清洗规则误伤的一类字符：
      · 正则规则（RM/去动作/去说明）经常用 `[（(].*?[）)]`
      · 各种"去掉括号说明"的启发式也会顺手把它当噪声
    而括号在角色扮演里**不是噪声**：`(摸摸头)` 是动作描写，是玩家表达的一部分。

本模块只做两件事（都很小、都能测）：
    lost_brackets(before, after)   —— 判断括号是不是变少了（返回 (少了几个, 具体丢的字符)）
    shield / unshield              —— 需要"临时藏起来"时，把括号换成私有区字符，处理完再换回来

调用点（错了就会误伤正常内容，所以刻意保守）：
    · 桌面：`_apply_regex_pipeline(scope="user")` —— 某条规则会吃括号就**跳过它**并打印是哪个 id
    · 安卓：`RegexEngine.apply(scope="user")`   —— 同上
    · 两端都在最后一步做一次"括号诊断"，输入输出对不上就打印，下次一眼定位

验：tests/test_text_shield.py
"""
from __future__ import annotations

BRACKETS = "（）()"

# 私有区占位（不会被任何清洗规<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌则/正则命中，也不会显示出来）
_TO = {"（": "\ue000", "）": "\ue001", "(": "\ue002", ")": "\ue003"}
_FROM = {v: k for k, v in _TO.items()}


def _counts(text):
    return {c: (text or "").count(c) for c in BRACKETS}


def lost_brackets(before, after):
    """括号是不是变少了？返回 (丢的数量, 丢的字符列表)；没丢返回 (0, [])。"""
    a, b = _counts(before), _counts(after)
    lost = [(c, a[c] - b[c]) for c in BRACKETS if a[c] > b[c]]
    return (sum(n for _, n in lost), [c for c, _ in lost]) if lost else (0, [])


def shield(text):
    """把括号换成私有区字符（处理期间不会被误伤）。"""
    if not text:
        return text
    for src, dst in _TO.items():
        text = text.replace(src, dst)
    return text


def unshield(text):
    """换回真括号。"""
    if not text:
        return text
    for src, dst in _FROM.items():
        text = text.replace(src, dst)
    return text


def keeps_user_text(apply_rule, text, rule_id=""):
    """跑一条规则，但**不许它吃掉括号**。

    apply_rule: 无参函数，返回处理后的文本
    返回 (结果, 是否被拦下)；被拦下时结果 = 原文。
    """
    try:
        out = apply_rule()
    except Exception:
        return text, False
    if not isinstance(out, str):
        return text, False
    lost, _chars = lost_brackets(text, out)
    if lost:
        if rule_id:
            print("[括号保护] 规则 %r 会吃掉 %d 个括号，已跳过（用户输入不改写）" % (rule_id, lost))
        return text, True
    return out, False
