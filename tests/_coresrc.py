# -*- coding: utf-8 -*-
"""tests/_coresrc.py —— 让测试读"整个核心"（DICK_core.py + core_*.py）。

背景：核心引擎从 2991 行的单文件拆成了 DICK_core + core_tree/core_context/core_mech/
core_llm/core_fetch/core_prompt。闸门原本按单文件找 `persona_block` / `mode_block` /
`sycophancy_guard_text` / `notify_busy`，拆完就找不到了 —— 断言的对象其实是
"核心有没有接这条线"，不是"它在哪个文件"。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CORE_FILES = ["DICK_core.py", "core_tree.py", "core_context.py", "core_mech.py",
              "core_llm.py", "core_fetch.py", "core_prompt.py"]


def read():
    parts = []
    for f in CORE_FILES:
        p = os.path.join(ROOT, f)
        if os.path.isfile(p):
            parts.append(io.open(p, encoding="utf-8", errors="replace").read())
    return "\n".join(parts)
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌