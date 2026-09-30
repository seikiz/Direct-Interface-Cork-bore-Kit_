# -*- coding: utf-8 -*-
"""把 web/index.html 的 ICONS 渲染成一张总览页，用来肉眼过一遍手绘 SVG。

用法: python tools/gen_icon_preview.py
输出: _icons_preview.html（用浏览器打开；文件以下划线开头，已被 .gitignore 忽略）

图标是手写的 path，形状对不对只能看 —— 这个页面就是"看一眼"的地方：
哪个图形画歪了、认不出来，照着下面的槽位名（ic_xxx）去 ICONS 里改那一行即可。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = io.open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()

SVG_HEAD = ("<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' "
            "stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>")

body = re.search(r"var ICONS = \{(.*?)\n\};", html, re.S)
assert body, "no ICONS block"
entries = re.findall(r"'([^']+)': _ic\('(.*?)'\),?", body.group(1), re.S)

files = re.search(r"var ICON_FILES = \{(.*?)\n\};", html, re.S)
slug = {}
if files:
    for em, ic in re.findall(r"'([^']+)'\s*:\s*'ic_([a-z0-9_]+)'", files.group(1)):
        slug[em] = ic

named = re.search(r"var NAMED_ICONS = \{(.*?)\n\};", html, re.S)
named_entries = re.findall(r"([a-z_]+): _ic\('(.*?)'\)", named.group(1), re.S) if named else []

cells = []
for em, inner in entries:
    cells.append("<figure class=c>%s%s</svg><figcaption>%s<br><b>ic_%s</b></figcaption></figure>"
                 % (SVG_HEAD, inner, em, slug.get(em, "-")))
for name, inner in named_entries:
    cells.append("<figure class=c>%s%s</svg><figcaption>[ic:%s]<br><b>具名</b></figcaption></figure>"
                 % (SVG_HEAD, inner, name))

page = ("<!doctype html><meta charset=utf-8><title>DICK 图标总览</title><style>"
        "body{background:#12161c;color:#c8d6e5;font:13px/1.5 system-ui,'Microsoft YaHei';padding:24px}"
        "h1{font-size:16px;font-weight:600;margin:0 0 4px}"
        "p{color:#8a93a3;margin:0 0 20px}"
        ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:10px}"
        "figure{margin:0;padding:10px 6px;border:1px solid #2a323d;border-radius:10px;text-align:center}"
        "svg{width:28px;height:28px;color:#e6edf5}"
        "figcaption{margin-top:6px;font-size:10px;color:#8a93a3;word-break:break-all}"
        "b{color:#7aa2b8;font-weight:500}</style>"
        "<h1>DICK 图标总览（%d 个）</h1>"
        "<p>ICONS 字典的全部图形，随主题用 currentColor 上色。"
        "哪个画得不对，按下面的槽位名去 web/index.html 改对应那一行。</p>"
        "<div class=g>%s</div>" % (len(cells), "".join(cells)))

out = os.path.join(ROOT, "_icons_preview.html")
io.open(out, "w", encoding="utf-8").write(page)
print("wrote %s with %d icons" % (out, len(cells)))
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌