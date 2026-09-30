# -*- coding: utf-8 -*-
"""从 web/index.html 的 ICONS 字典生成 Android VectorDrawable 资源 + Kotlin 映射。
用法: python tools/gen_android_icons.py
输出: DICK-Android/app/src/main/res/drawable/ic_*.xml + _android_icon_map.txt

槽位名（ic_xxx）直接取自 index.html 的 ICON_FILES —— 那里是唯一真相源。
（以前这里手抄了一份 SLUGS 表，第二批图标加进 index.html 后这里认不出来，
 就静默 skip 掉，手机上继续显示 emoji。别再抄第二份。）
"""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()

# 提取 ICONS 字典体（var <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ICONS = { ... };）
m = re.search(r"var ICONS = \{(.*?)\n\};", html, re.S)
body = m.group(1)
entries = re.findall(r"'([^']+)': _ic\('(.*?)'\),?", body, re.S)
assert entries, "no ICONS entries found"

# 槽位表：emoji → 槽位名（来自 ICON_FILES）
files = re.search(r"var ICON_FILES = \{(.*?)\n\};", html, re.S)
SLUGS = {}
if files:
    for em, ic in re.findall(r"'([^']+)'\s*:\s*'ic_([a-z0-9_]+)'", files.group(1)):
        SLUGS[em] = ic


def circle_path(cx, cy, r):
    return (f"M {cx-r} {cy} A {r} {r} 0 1 0 {cx+r} {cy} "
            f"A {r} {r} 0 1 0 {cx-r} {cy} Z")


def rect_path(x, y, w, h, rx=0):
    if rx:
        return (f"M {x+rx} {y} H {x+w-rx} A {rx} {rx} 0 0 1 {x+w} {y+rx} "
                f"V {y+h-rx} A {rx} {rx} 0 0 1 {x+w-rx} {y+h} H {x+rx} "
                f"A {rx} {rx} 0 0 1 {x} {y+h-rx} V {y+rx} A {rx} {rx} 0 0 1 {x+rx} {y} Z")
    return f"M {x} {y} H {x+w} V {y+h} H {x} Z"


def line_path(x1, y1, x2, y2):
    return f"M {x1} {y1} L {x2} {y2}"


def inner_to_paths(inner):
    """把 ICONS 的 svg 内部 HTML 转成 [(pathData, 是否填充), ...]

    path 的属性顺序不固定（实心图标是 <path fill="currentColor" d="..."/>），
    所以先整段取属性再挑 d —— 不能假设 <path d="..."/> 这种最简形态，否则实心图标整条丢掉。
    """
    out = []
    for pm in re.finditer(r'<path\b([^>]*?)/>', inner):
        attrs = pm.group(1)
        d = re.search(r'd="([^"]*)"', attrs)
        if not d:
            continue
        out.append((d.group(1), "currentColor" in attrs))
    for cm in re.finditer(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"([^>]*?)/>', inner):
        out.append((circle_path(float(cm.group(1)), float(cm.group(2)), float(cm.group(3))),
                    "currentColor" in cm.group(4)))
    for rm in re.finditer(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"(?: rx="([\d.]+)")?([^>]*?)/>', inner):
        rx = float(rm.group(5)) if rm.group(5) else 0
        out.append((rect_path(float(rm.group(1)), float(rm.group(2)),
                              float(rm.group(3)), float(rm.group(4)), rx),
                    "currentColor" in rm.group(6)))
    for lm in re.finditer(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"([^>]*?)/>', inner):
        out.append((line_path(float(lm.group(1)), float(lm.group(2)),
                              float(lm.group(3)), float(lm.group(4))),
                    "currentColor" in lm.group(5)))
    return out


res_dir = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "res", "drawable")
os.makedirs(res_dir, exist_ok=True)

VEC_HEAD = ('<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '    android:width="24dp" android:height="24dp"\n'
            '    android:viewportWidth="24" android:viewportHeight="24">\n')
PATH_STROKE = ('  <path\n      android:pathData="{d}"\n'
               '      android:strokeColor="#FF000000" android:strokeWidth="1.8"\n'
               '      android:strokeLineCap="round" android:strokeLineJoin="round"\n'
               '      android:fillColor="#00000000"/>\n')
PATH_FILL = ('  <path\n      android:pathData="{d}"\n'
             '      android:fillColor="#FF000000"/>\n')

map_lines = []
written = set()
missing = []
for emoji, inner in entries:
    slug = SLUGS.get(emoji)
    if not slug:
        missing.append(emoji)
        continue
    paths = inner_to_paths(inner)
    if not paths:
        missing.append(emoji + "(no paths)")
        continue
    if slug in written:
        # 只有【写文件】按槽位去重；映射行不能去重 —— 📂/📁、⭐/★、🎭/👥 这类别名
        # 共用同一个 drawable，但每个 emoji 都要有自己的映射行，少一行界面上就没人认它。
        map_lines.append(f'    "{emoji}" to R.drawable.ic_{slug},')
        continue
    written.add(slug)
    body_xml = "".join((PATH_FILL if filled else PATH_STROKE).format(d=d) for d, filled in paths)
    with open(os.path.join(res_dir, f"ic_{slug}.xml"), "w", encoding="utf-8") as f:
        f.write(VEC_HEAD + body_xml + "</vector>\n")
    map_lines.append(f'    "{emoji}" to R.drawable.ic_{slug},')

print(f"wrote {len(written)} drawables -> {res_dir}")
if missing:
    print("MISSING:", missing)
with open(os.path.join(ROOT, "_android_icon_map.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(map_lines) + "\n")
print("kotlin map -> _android_icon_map.txt")
