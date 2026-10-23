# -*- coding: utf-8 -*-
"""tests/_websrc.py —— 让前端闸门读"整个前端"（index.html + web/js/*.js）。

背景：index.html 里 3310 行的内联脚本拆成了 web/js/chat-inline-*.js，
但闸门还在只读 index.html（例如"不再内联三段 T = {...}""_ICON_SKIP 让开作用域"
"前端用 state 带回的版号"）。断言对象是"前端有没有这么做"，不是"写在哪一行"。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read():
    parts = []
    idx = os.path.join(ROOT, "web", "index.html")
    if os.path.isfile(idx):
        parts.append(io.open(idx, encoding="utf-8", errors="replace").read())
    js_dir = os.path.join(ROOT, "web", "js")
    if os.path.isdir(js_dir):
        for f in sorted(os.listdir(js_dir)):
            if f.endswith(".js") and f.startswith("chat-inline"):
                parts.append(io.open(os.path.join(js_dir, f), encoding="utf-8", errors="replace").read())
    return "\n".join(parts)
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌