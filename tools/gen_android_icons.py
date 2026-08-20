# -*- coding: utf-8 -*-
"""从 web/index.html 的 ICONS 字典生成 Android VectorDrawable 资源 + Kotlin 映射。
用法: python tools/gen_android_icons.py
输出: DICK-Android/app/src/main/res/drawable/ic_*.xml + _android_icon_map.txt"""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()

# 提取 ICONS 字典体（var ICONS = { ... };）
m = re.search(r"var ICONS = \{(.*?)\n\};", html, re.S)
body = m.group(1)
entries = re.findall(r"'([^']+)': _ic\('(.*?)'\),?", body, re.S)
assert entries, "no ICONS entries found"

SLUGS = {
    "\U0001F4C2": "folder", "\U0001F6F0": "radio", "\u2795": "plus", "\u274C": "close",
    "\u2699": "settings", "\u2705": "check", "\U0001F9F0": "toolbox", "\U0001F4E4": "upload",
    "\U0001F5D1": "trash", "\U0001F511": "key", "\u26A0": "warn", "\U0001F30D": "globe",
    "\U0001F310": "globe", "\U0001F4BE": "save", "\U0001F9EE": "calc", "\U0001F524": "font",
    "\U0001F50C": "plug", "\U0001F50D": "search", "\u2B07": "download", "\U0001F4E5": "inbox",
    "\u2764": "heart", "\U0001F916": "robot", "\u2728": "sparkle", "\U0001F525": "flame",
    "\U0001F3AD": "users", "\U0001F9D1": "person", "\U0001F464": "person", "\U0001F4F7": "camera",
    "\U0001F517": "link", "\U0001F4C4": "doc", "\U0001F9F9": "clear", "\U0001F3A8": "droplet",
    "\u270F": "edit", "\U0001F4DA": "book", "\U0001F33F": "branch", "\U0001F4CA": "chart",
    "\U0001F4C8": "trend", "\U0001F3B2": "dice", "\U0001F9E0": "chip", "\U0001F3AE": "gamepad",
    "\u2702": "scissors", "\U0001F504": "refresh", "\U0001F5BC": "image", "\U0001F680": "rocket",
    "\U0001F527": "wrench", "\U0001F44B": "wave", "\U0001F4AC": "chat", "\U0001F3AF": "target",
}

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
    """把 ICONS 的 svg 内部 HTML 转成 pathData 列表"""
    out = []
    for pm in re.finditer(r'<path d="([^"]*)"/>', inner):
        out.append(pm.group(1))
    for cm in re.finditer(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"/>', inner):
        out.append(circle_path(float(cm.group(1)), float(cm.group(2)), float(cm.group(3))))
    for rm in re.finditer(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"(?: rx="([\d.]+)")?/>', inner):
        rx = float(rm.group(5)) if rm.group(5) else 0
        out.append(rect_path(float(rm.group(1)), float(rm.group(2)), float(rm.group(3)), float(rm.group(4)), rx))
    for lm in re.finditer(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)"/>', inner):
        out.append(line_path(float(lm.group(1)), float(lm.group(2)), float(lm.group(3)), float(lm.group(4))))
    return out

res_dir = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "res", "drawable")
os.makedirs(res_dir, exist_ok=True)

VEC_HEAD = ('<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '    android:width="24dp" android:height="24dp"\n'
            '    android:viewportWidth="24" android:viewportHeight="24">\n')
PATH = ('  <path\n      android:pathData="{d}"\n'
        '      android:strokeColor="#FF000000" android:strokeWidth="1.8"\n'
        '      android:strokeLineCap="round" android:strokeLineJoin="round"\n'
        '      android:fillColor="#00000000"/>\n')

map_lines = []
written = set()
missing = []
for emoji, inner in entries:
    if emoji not in SLUGS:
        missing.append(emoji)
        continue
    slug = SLUGS[emoji]
    paths = inner_to_paths(inner)
    if not paths:
        missing.append(emoji + "(no paths)")
        continue
    fname = f"ic_{slug}.xml"
    if slug in written:
        continue  # 同 slug 复用（globe/person 重复）
    written.add(slug)
    body_xml = "".join(PATH.format(d=p) for p in paths)
    with open(os.path.join(res_dir, fname), "w", encoding="utf-8") as f:
        f.write(VEC_HEAD + body_xml + "</vector>\n")
    map_lines.append(f'    "{emoji}" to R.drawable.ic_{slug},')

print(f"wrote {len(written)} drawables -> {res_dir}")
if missing:
    print("MISSING:", missing)
with open(os.path.join(ROOT, "_android_icon_map.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(map_lines) + "\n")
print("kotlin map -> _android_icon_map.txt")
