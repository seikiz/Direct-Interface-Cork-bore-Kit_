# -*- coding: utf-8 -*-
"""modules/codex/constants.py —— CODEX 格式的常量与文件分类（最底层，谁都能用）

搬家来源：`codex_core.py` 的 `CODEX_VERSION` / `SUBDIRS` / `_EXT_KIND` / `_NAME_KIND` /
`classify_file`，**一字未改**。

`CODEX_FORMAT = "codex/1.0"` 没搬进来：它在原文件里只出现在定义处（没写进包、也没校验，
tests/test_compat_surface.py 专门钉住了这一点）。那个字面量留在仓库根 `codex_core.py`
门面里，免得"常量声明了却没人用"这个现状被这次搬家悄悄改掉。
"""

import os
import re
import types


CODEX_VERSION = "1.0"


SUBDIRS = ("sprites", "bg", "bgm", "voice")

# 两张查表都是**只读的**（ARCHITECTU<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌RE.md 十一：块里不许有模块级可变全局 ——
# 状态要挂在服务实例上。这两张是格式常量，不是状态，所以用只读视图/meta 元组搬过来，
# 既保留"唯一一份真相"，也让"谁能改它"这件事在类型上就不成立）。
_EXT_KIND = types.MappingProxyType({
    ".png": "sprites", ".jpg": "sprites", ".jpeg": "sprites", ".webp": "sprites", ".gif": "sprites",
    ".mp3": "bgm", ".wav": "bgm", ".ogg": "bgm", ".flac": "bgm",
    ".mp4": "voice", ".m4a": "voice",
})


_NAME_KIND = (
    (re.compile(r"(voice|配音|声|セリフ|せりふ|音声)", re.I), "voice"),
    (re.compile(r"(bgm|music|音乐|音楽|曲|theme)", re.I), "bgm"),
    (re.compile(r"(bg|背景|back|room|school|夜景|教室|海岸|駅|駅前)", re.I), "bg"),
    (re.compile(r"(sprite|立绘|立絵|表情|face|表情差分)", re.I), "sprites"),
)


def classify_file(name):
    """按文件名猜资源类别（sprites/bg/bgm/voice）；无法识别返回 None"""
    base = os.path.basename(name or "").lower()
    stem = os.path.splitext(base)[0]
    for pat, kind in _NAME_KIND:
        if pat.search(stem):
            return kind
    ext = os.path.splitext(base)[1]
    return _EXT_KIND.get(ext)
