# -*- coding: utf-8 -*-
"""time_scale.py —— 软件时间流速：世界那边过得比现实快多少倍。

为什么要这个
------------
AI 恋人要有时间感。但靠用户一条条输入去推进时间太麻烦 ——
所以用【倍率】把现实的流逝放大：现实过 1 秒，那边过 N 秒。

倍率的实际含义（用"一轮对话大约 30 秒"折算，只是方便理解，
代码里不依赖这个假设）：
    60      → 一轮约 30 分钟
    720     → 一轮约 6 小时     （默认）
    3600    → 一轮约 1 天
    21600   → 一轮约 1 周
    86400   → 一轮约 1 个月
    604800  → 一轮约 7 个月（半年）

一个不显然、但必须知道的后果
----------------------------
流速【同时加快记忆的衰老】。因为记忆的年龄 = 现实流逝 × 倍率：
    现实里隔了 1 分钟没说话，在 86400 倍下那边已经过了一天 ——
    角色就该像隔了一天那样忘事。
    倍率 720 时：记忆寿命从"约 10 天"变成"约 20 分钟"。
    倍率 86400 时：几秒钟就忘。

这不是 bug，是"她的日子比你的快"的直接推论。倍率开得越高，
角色越像活在快进里 —— 也正是"活人感"的来源。
想把记忆留住就用低倍率（10 或 60），想让时间飞逝就接受她健忘。

世界卡不用改：倍率是内置设置，独立于任何卡。
"""
import os
import json
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_NAME = "time_scale.json"

DEFAULT_SCALE = 720.0
MIN_SCALE = 10.0            # 用户定的下限：一秒相当于那边 10 秒
MAX_SCALE = 10_000_000.0    # 上限：再高就纯属数值游戏了

# (倍率, 名称)  —— 名称按"<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌一轮约 30 秒"折算，方便用户理解
PRESETS = (
    (10, "10倍 · 缓慢"),
    (60, "60倍 · 一轮约 30 分钟"),
    (720, "720倍 · 一轮约 6 小时"),
    (3600, "3600倍 · 一轮约 1 天"),
    (21600, "21600倍 · 一轮约 1 周"),
    (86400, "86400倍 · 一轮约 1 个月"),
    (604800, "604800倍 · 一轮约 7 个月"),
)

_lock = threading.Lock()
_cache = None


def config_path():
    """跟着 exe/工程走，和存档同目录（便携版约定）"""
    return os.path.join(ROOT, CONFIG_NAME)


def clamp(scale):
    try:
        v = float(scale)
    except (TypeError, ValueError):
        return DEFAULT_SCALE
    if v != v:              # NaN
        return DEFAULT_SCALE
    return max(MIN_SCALE, min(MAX_SCALE, v))


def load():
    """读流速设置；读不到就用默认值。缓存，避免每轮都读盘。"""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
    val = DEFAULT_SCALE
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        val = clamp(d.get("scale", DEFAULT_SCALE))
    except Exception:
        val = DEFAULT_SCALE
    with _lock:
        _cache = val
    return val


def save(scale):
    val = clamp(scale)
    global _cache
    with _lock:
        _cache = val
    try:
        tmp = config_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"scale": val}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, config_path())
    except Exception:
        pass
    return val


ROUND_SECONDS = 30.0        # 折算用：一轮对话大约现实 30 秒。只用于人话描述。


def per_round_text(scale=None):
    """这个倍率下，一轮对话大约推进多少世界时间。给表盘中央显示用。

    不吸附也能用 —— 表盘停在 158 倍时会显示"一轮约 79 分钟"，
    比只认预设档有用得多。
    """
    s = clamp(scale if scale is not None else load())
    sec = s * ROUND_SECONDS
    if sec < 60:
        return "一轮约 %d 秒" % round(sec)
    if sec < 3600:
        return "一轮约 %d 分钟" % round(sec / 60.0)
    if sec < 86400:
        return "一轮约 %.1f 小时" % (sec / 3600.0)
    days = sec / 86400.0
    if days < 30:
        return "一轮约 %.1f 天" % days
    months = days / 30.0
    if months < 24:
        return "一轮约 %.1f 个月" % months
    return "一轮约 %.1f 年" % (months / 12.0)


def describe(scale=None):
    """给界面/日志看的一句话。"""
    s = clamp(scale if scale is not None else load())
    for mul, name in PRESETS:
        if abs(s - mul) < 0.5:
            return name
    return "%.4g 倍 · %s" % (s, per_round_text(s))


def virtual_age_seconds(real_seconds, scale=None):
    """现实流逝了多少秒 → 那边过了多少秒。"""
    s = clamp(scale if scale is not None else load())
    try:
        r = float(real_seconds)
    except (TypeError, ValueError):
        r = 0.0
    if r != r:
        r = 0.0
    return max(0.0, r) * s


# ---------------------------------------------------------------- 表盘刻度
# 为什么用对数：MIN=10、MAX=1000万，跨 6 个数量级。线性表盘 98% 的行程
# 都浪费在前几档上，指针稍微一动就是几百万倍，没法用。
# 对数刻度下每转一格 = ×10，人对量级的感知本来也是对数的，手感才对。
import math as _math


def scale_to_pos(scale):
    """倍率 → 表盘位置 [0,1]。对数刻度。"""
    s = clamp(scale)
    lo = _math.log10(MIN_SCALE)
    hi = _math.log10(MAX_SCALE)
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (_math.log10(s) - lo) / (hi - lo)))


def pos_to_scale(pos):
    """表盘位置 [0,1] → 倍率。纯对数换算，不吸附。
    吸附到预设档是界面层的事（松手时调 nearest_preset）。"""
    try:
        p = float(pos)
    except (TypeError, ValueError):
        p = 0.0
    if p != p:              # NaN
        p = 0.0
    p = max(0.0, min(1.0, p))
    lo = _math.log10(MIN_SCALE)
    hi = _math.log10(MAX_SCALE)
    return clamp(10.0 ** (lo + (hi - lo) * p))


def nearest_preset(scale, tolerance=0.05):
    """倍率离哪个预设最近（相对容差）。不在任何预设附近就返回 None。"""
    s = clamp(scale)
    best, bd = None, None
    for mul, name in PRESETS:
        d = abs(_math.log10(s) - _math.log10(float(mul)))
        if bd is None or d < bd:
            best, bd = mul, d
    if bd is not None and bd <= tolerance:
        return best
    return None


def dial_marks():
    """表盘上的刻度标记：每个预设的位置 + 名称，给界面画刻度用。"""
    out = []
    for mul, name in PRESETS:
        out.append({"scale": mul, "name": name, "pos": round(scale_to_pos(mul), 4)})
    return out
