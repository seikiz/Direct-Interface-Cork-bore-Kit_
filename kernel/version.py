# -*- coding: utf-8 -*-
"""kernel/version.py —— 四段版号（与 app_version.py 同一口径）

为什么内核也要有一份：
    manifest 校验必须能**离线、独立**判断 version 合不合法，不能反过来 import 业务层的
    app_version（那就违背依赖方向了）。所以这里只抄"四段号"这一条规则：
      `主.次.补.实验`，四段全数字；前两位不变 = 兼容。
    真正的产品版号仍然是根目录 version.json 唯一真相（app_version.py 负责），
    这里不读它、也不写它 —— 内核不该知道产品叫什么名字。
"""

import re

KERNEL_VERSION = "1.0.0.0"        # 内核自己的契约版本：manifest 契约变了才涨

_FOUR_PART = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def parse(text):
    """四段号 → (a, b, c, d)；不合法返回 None（**不做"补 0"**，本函数用于校验）"""
    s = str(text or "").strip()
    if not _FOUR_PART.match(s):
        return None
    try:
        return tuple(int(x) for x in s.split("."))
    except (TypeError, ValueError):
        return None


def is_valid(text):
    """manifest 里的 version 是否合法（四段、全数字）"""
    return parse(text) is not None


def compat_line(version):
    """兼容线 = 前两位（`1.0`）；内核与模块靠它判断"能不能一起用"。"""
    parts = parse(version)
    if not parts:
        return ""
    return "%d.%d" % (parts[0], parts[1])


def code_of(version):
    """四段号 → 单调递增整数（排序/比较用；算法与安卓 versionCode 同源）"""
    parts = parse(version)
    if not parts:
        return 0
    a, b, c, d = parts
    return a * 1000000 + b * 10000 + c * 100 + d
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌