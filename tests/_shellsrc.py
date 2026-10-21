# -*- coding: utf-8 -*-
"""tests/_shellsrc.py —— 让测试读"整个壳层"（Kit.py + shell_*.py）而不是单个文件。

背景：血洗把 Kit.py 拆成 Kit.py + shell_ws/shell_codex/shell_go/shell_host/shell_api_*。
而这些闸门原本断言"后端有 api_xxx"/"api_state 暴露 opening_loading"——
方法搬走后单看 Kit.py 就找不到，于是误红。

**这不是放宽规则**：断言的对象是"壳层有没有这个门面"，不是"它在哪个文件里"。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read():
    parts = []
    kit = os.path.join(ROOT, "Direct-Interface Cork-bore Kit.py")
    if os.path.isfile(kit):
        parts.append(io.open(kit, encoding="utf-8", errors="replace").read())
    for f in sorted(os.listdir(ROOT)):
        if f.startswith("shell_") and f.endswith(".py"):
            parts.append(io.open(os.path.join(ROOT, f), encoding="utf-8", errors="replace").read())
    return "\n".join(parts)
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌