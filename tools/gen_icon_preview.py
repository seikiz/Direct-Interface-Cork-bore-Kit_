# -*- coding: utf-8 -*-
"""把图标唯一真相渲染成一张总览页，用来肉眼过一遍。

用法: python tools/gen_icon_preview.py
输出: _icons_preview.html（用浏览器打开；文件以下划线开头，已被 .gitignore 忽略）

图标现在是 Material Symbols（字体渲染）：形状由图标库决定，不再需要"看手绘 path 歪没歪"，
但**挑名字**这件事仍然只能看 —— 这个页面就是"看一眼"的地方：每行显示 字形（用随包字体渲染）/
图标名 / 对应的 emoji / 旧 png 槽位，好比对哪个 emoji 选错了图标。
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 让 `import seiki_mark` 找得到（水印工具在仓库根，脚本从 tools/ 里跑）
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SRC = os.path.join(ROOT, "icons", "icons.json")
OUT = os.path.join(ROOT, "_icons_preview.html")

data = json.loads(io.open(SRC, encoding="utf-8").read())
icons, named = data["icons"], data["named"]

ROW = (u"<tr><td class='ms'>%s</td><td class='name'>%s</td><td class='emo'>%s</td>"
       u"<td class='png'>%s</td><td class='note'>%s</td></tr>")

rows = [ROW % (v["name"], v["name"], emo, v.get("png") or u"", v.get("note") or u"")
        for emo, v in sorted(icons.items(), key=lambda kv: kv[1]["name"])]
named_rows = [ROW % (v["name"], v["name"], u"[ic:%s]" % k, v.get("png") or u"", v.get("note") or u"")
              for k, v in sorted(named.items())]

page = u"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>图标总览 · Material Symbols</title>
<style>
 body{ background:#111; color:#e5e7eb; font:14px/1.6 system-ui,"Segoe UI","Microsoft YaHei"; padding:24px; }
 h1{ font-size:18px; margin:0 0 4px; } h2{ font-size:15px; margin-top:24px; color:#93c5fd; }
 p.hint{ color:#9ca3af; font-size:12px; max-width:900px; }
 @font-face{ font-family:'Material Symbols Outlined'; font-style:normal; font-weight:300;
   font-display:block; src:url('web/fonts/MaterialSymbolsOutlined.woff2') format('woff2'); }
 .ms{ font-family:'Material Symbols Outlined'; font-size:26px; line-height:1;
   font-feature-settings:'liga'; color:#f59e0b; }
 table{ border-collapse:collapse; } th{ text-align:left; color:#93c5fd; font-size:12px; padding:2px 10px; }
 td{ border-bottom:1px solid #1f2937; padding:4px 10px; vertical-align:middle; }
 .name{ font-family:ui-monospace,Consolas,monospace; color:#e5e7eb; }
 .emo{ font-size:18px; } .png{ color:#9ca3af; font-family:ui-monospace,monospace; font-size:12px; }
 .note{ color:#fca5a5; font-size:12px; max-width:460px; }
</style></head><body>
<h1>图标总览 · Material Symbols Outlined（wght 300，随包字体）</h1>
<p class="hint">唯一真相 <b>icons/icons.json</b>；换图标 = 改里面的 name，再跑
<b>python tools/gen_icons.py</b>。共 %d 个 emoji 条目 + %d 个具名条目。
字形直接用随包 woff2 渲染 —— 看到方块就说明那个名字在字体里不存在
（<b>tests/test_android_icons.py</b> 会因此变红）。</p>
<h2>emoji → 图标</h2>
<table><tr><th>字形</th><th>图标名</th><th>emoji</th><th>png 槽位</th><th>注解</th></tr>
%s</table>
<h2>具名（正文里写 [ic:名字]）</h2>
<table><tr><th>字形</th><th>图标名</th><th>标记</th><th>png 槽位</th><th>注解</th></tr>
%s</table>
</body></html>
""" % (len(icons), len(named), u"\n".join(rows), u"\n".join(named_rows))

with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(page)
# 生成物也带仓库水印（tests/test_seiki_mark.py 会扫到根目录这个文件）：
# 直接用仓库那把 CLI（cmd_mark），别自己拼注释——它的锚点规则与格式只有一份。
try:
    import seiki_mark as SM
    SM.cmd_mark([OUT], None, False)
except Exception as e:
    print(u"[warn] 水印没嵌上：%s" % e)
print(u"[写] %s（%d 个 emoji + %d 个具名）" % (os.path.basename(OUT), len(icons), len(named)))
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌