# -*- coding: utf-8 -*-
"""app_version.py —— 版号的唯一真相（读根目录 `version.json`）。

为什么要有它
------------
改动之前版号散在 5 处：桌面欢迎语、窗口标题、前端控制台横幅各写死一个 "v2.0"，
安卓与播放器的 Gradle 各写死一个 "1.0"。于是"电脑上是 v2.0、手机上是 1.0"，
而且每次涨号得记着改五个地方 —— 漏一个就出现两个版本并存。

现在：`version.json` 是唯一真相，其余全部**派生**：
  · 桌面端运行时读这里（`display()` / `full()`），不再写死；
  · 安卓与播放器在 Gradle 配置阶段读同一个 json（versionName / versionCode 都算出来）；
  · `tools/bump_version.py` 是唯一改它的手；
  · `tests/test_version_consistency.py` 盯着"谁还在自己写版号"。

四段号的用法（用户定调）：`主.次.补.实验`；**前两位不变 = 兼容**，无法兼容直接进 2.0；
大功能涨次位、**补位只用来标记「加了官方可选插件」**、第四位是实验性版本；纯修补不涨号。
Android 的 versionCode 由四段算出来：`主*10^6 + 次*10^4 + 补*10^2 + 构建`（1.0.0.1 → 1000001）。
"""
import json
import os
import sys

FALLBACK = "1.0.0.1"


def _roots():
    """找 version.json：PyInstaller 解包目录优先，其次源码目录。"""
    out = []
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        out.append(mei)
    out.append(os.path.dirname(os.path.abspath(__file__)))
    return out


def _load():
    for d in _roots():
        p = os.path.join(d, "version.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and str(data.get("version") or "").strip():
                return data
        except Exception:
            continue
    return {}


_DATA = _load()

NAME = str(_DATA.get("name") or "DICK")
VERSION = str(_DATA.get("version") or FALLBACK).strip() or FALLBACK
GENERATION = str(_DATA.get("generation") or "").strip()


def parts(version=None):
    """四段号 → [int, int, int, int]（不足四段补 0；多余/非数字段忽略）。"""
    out = []
    for seg in str(version or VERSION).split("."):
        try:
            out.append(int(seg.strip()))
        except (TypeError, ValueError):
            break
    while len(out) < 4:
        out.append(0)
    return out[:4]


def code_of(version=None):
    """四段号 → Android 的 versionCode（单调递增，够用到 21 亿）。"""
    a, b, c, d = parts(version)
    return a * 1000000 + b * 10000 + c * 100 + d


# 写在函数后面：json 里没写 cod<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌e 时用四段号算出来（两边不可能对不上）
CODE = int(_DATA.get("code") or code_of(VERSION))


def display():
    """`v1.0.0.1` —— 用在窗口标题、控制台横幅这类地方。"""
    return "v" + VERSION


def compat_line(version=None):
    """兼容线 = 前两位（`1.0`）。**同一条线内互相兼容**，换线就是换承诺。"""
    a, b = parts(version)[:2]
    return "%d.%d" % (a, b)


def full():
    """`DICK v1.0.0.1（兼容线 1.0）` —— 用在欢迎语这类要报全名的地方。

    注意**不显示 generation（产品代 v2.0）**：那是"代"，跟"2.0 = 下一个不兼容纪元"
    撞号，两个数字并排出现只会让人以为是同一个东西。
    """
    return "%s %s（兼容线 %s）" % (NAME, display(), compat_line())


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(full())
    print("versionCode = %d" % CODE)
