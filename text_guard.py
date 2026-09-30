# -*- coding: utf-8 -*-
"""
text_guard.py —— 不可见字符防线

为什么必须过滤零宽字符（不是洁癖，是真危害）：
  ① 白烧 token：几千个零宽字符就是几千 token，用户界面上什么都看不见，钱却花了；
  ② 卡死前端：浏览器/WebView 要逐字排版，长串不可见字符会直接把渲染拖死；
  ③ 藏提示词注入：正文里夹一段看不见的指令，人眼审不出来；
  ④ 绕过过滤：把敏感词中间插零宽字符，关键词匹配立刻失效。

策略（关键是别误伤正常内容）：
  · 双向控制符 / 标签字符 / 软连字符这些**没有正常用途**的 → 一律删；
  · ZWJ(U+200D)/ZWNJ(U+200C) 在 emoji 组合(👨‍👩‍👧)和部分文字里是**合法的** →
    少量保留，一旦数量超标（典型的字符炸弹）就判定为攻击，全删。
"""

import unicodedata

# ---- 一律删除：这些字符<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌在聊天里没有正当用途 ----
ALWAYS_STRIP = {
    "\u200b",  # 零宽空格
    "\u2060",  # 词连接符
    "\ufeff",  # 零宽不换行空格 / BOM
    "\u00ad",  # 软连字符
    "\u034f",  # 组合字形连接符
    "\u180e",  # 蒙古文元音分隔符
    "\u061c",  # 阿拉伯字母标记
    "\u200e", "\u200f",                        # LRM / RLM 方向标记
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",   # 双向嵌入 / 覆盖
    "\u2066", "\u2067", "\u2068", "\u2069",    # 双向隔离
    "\u2061", "\u2062", "\u2063", "\u2064",    # 不可见运算符
}

# ---- 有条件保留：少量是合法的（emoji / 文字连写），超标就判为炸弹 ----
CONDITIONAL = {
    "\u200c",  # 零宽非连接符
    "\u200d",  # 零宽连接符（emoji 组合必需）
}

# ---- 标签字符区 U+E0000–U+E007F：整块不可见，典型夹带通道 ----
TAG_RANGE = range(0xE0000, 0xE0080)

# 判定为"字符炸弹"的阈值
BOMB_TOTAL = 24          # 不可见字符总数超过这个数
BOMB_RATIO = 0.12        # 或者占全文比例超过这个数（但要配合下面的绝对下限）
BOMB_RATIO_MIN_COUNT = 8  # 占比规则的绝对下限：短句里 1~7 个不算炸弹（emoji/软连字符都可能）

# 其他不可见/格式化类别（Cf = format），兜底用
def _is_format_char(ch):
    return unicodedata.category(ch) == "Cf"


def _classify(text):
    """统计文本里的不可见字符"""
    always = {}
    cond = {}
    tags = 0
    other_cf = {}
    for ch in text:
        if ch in ALWAYS_STRIP:
            always[ch] = always.get(ch, 0) + 1
        elif ch in CONDITIONAL:
            cond[ch] = cond.get(ch, 0) + 1
        elif ord(ch) in TAG_RANGE:
            tags += 1
        elif _is_format_char(ch) and ch not in ("\u00a0",):
            other_cf[ch] = other_cf.get(ch, 0) + 1
    return always, cond, tags, other_cf


def scan(text):
    """只体检不改动：返回不可见字符的分布情况"""
    if not isinstance(text, str):
        return {"total": 0, "chars": len(text or ""), "always": {}, "cond": {},
                "tags": 0, "other_cf": {}, "ratio": 0.0, "bomb": False}
    text = text.replace("\u00a0", " ")          # NBSP 先当普通空格看（类别是 Zs，不属于 Cf）
    always, cond, tags, other_cf = _classify(text)
    total = sum(always.values()) + sum(cond.values()) + tags + sum(other_cf.values())
    n = max(len(text), 1)
    ratio = total / n
    cond_total = sum(cond.values())
    # 注意：占比规则要配一个绝对下限。
    # 否则「正常+软连字符+文字」这种 5 字短句里 1 个不可见字符就占 20%，
    # 会被误报成"炸弹"——短消息本来就容易触发比例。
    bomb = bool(total and (total > BOMB_TOTAL
                           or (total >= BOMB_RATIO_MIN_COUNT and ratio > BOMB_RATIO)))
    # 少量 ZWJ 属于正常（emoji 组合），不算炸弹
    if total and total <= 6 and sum(always.values()) == 0 and tags == 0 \
            and sum(other_cf.values()) == 0 and cond_total == total:
        bomb = False
    return {"total": total, "chars": len(text), "always": always, "cond": cond,
            "tags": tags, "other_cf": other_cf, "ratio": round(ratio, 4), "bomb": bomb}


def sanitize(text, keep_legit_zwj=True):
    """清洗文本。返回 (干净文本, 报告)。
    报告里有 removed / kinds / bomb，界面可以据此提示用户。
    非字符串原样返回，绝不抛异常。"""
    if not isinstance(text, str) or not text:
        return text, {"removed": 0, "kinds": [], "bomb": False, "changed": False}

    # NBSP 先规整成普通空格：它的类别是 Zs（分隔符）不是 Cf，
    # 不这样处理的话 scan 数不到它，会走"无需清洗"的提前返回。
    if "\u00a0" in text:
        text = text.replace("\u00a0", " ")

    info = scan(text)
    if info["total"] == 0:
        return text, {"removed": 0, "kinds": [], "bomb": False, "changed": False}

    strip_cond = info["bomb"] or not keep_legit_zwj
    out = []
    removed = 0
    for ch in text:
        if ch in ALWAYS_STRIP or ord(ch) in TAG_RANGE:
            removed += 1
            continue
        if ch in CONDITIONAL and strip_cond:
            removed += 1
            continue
        if _is_format_char(ch) and ch not in CONDITIONAL:
            removed += 1
            continue
        out.append(ch)

    clean = "".join(out)
    kinds = []
    if info["always"]:
        kinds.append("零宽/方向控制符 %d 个" % sum(info["always"].values()))
    if info["cond"]:
        kinds.append("零宽连接符 %d 个" % sum(info["cond"].values()))
    if info["tags"]:
        kinds.append("隐藏标签字符 %d 个" % info["tags"])
    if info["other_cf"]:
        kinds.append("其他不可见格式符 %d 个" % sum(info["other_cf"].values()))
    return clean, {
        "removed": removed,
        "kinds": kinds,
        "bomb": info["bomb"],
        "ratio": info["ratio"],
        "before": info["chars"],
        "after": len(clean),
        "changed": removed > 0,
    }


def summary(report):
    """把报告变成一句给用户看的话；没删东西返回空串"""
    if not report or not report.get("changed"):
        return ""
    if report.get("bomb"):
        return ("⚠ 检测到零宽字符炸弹：已剔除 %d 个不可见字符（原文 %d 字 → %d 字）。"
                "这类字符会白烧 token 并可能卡住界面。" %
                (report["removed"], report.get("before", 0), report.get("after", 0)))
    return "（已顺带清理 %d 个不可见字符：%s）" % (
        report["removed"], "、".join(report.get("kinds") or ["不可见字符"]))
