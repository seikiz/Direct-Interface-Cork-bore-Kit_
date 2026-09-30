# -*- coding: utf-8 -*-
"""安卓端图标系统审计：emoji ↔ drawable 必须一一对得上。

为什么需要
----------
安卓的 emoji→drawable 映射由 web/index.html 的 ICONS 生成（tools/gen_android_icons.py）。
这条链上任何一环漏了，界面上就继续显示彩色 emoji —— 而且只有用户点进那个界面才发现。
Web 端有 tests/test_icons.js 把关，安卓这一侧以前什么都没有：
真发生过「第二批图标加进 index.html，生成器认不出来就静默 skip」的事。

跑法：python tests/test_android_icons.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UI = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java",
                  "com", "dick", "app", "Ui.kt")
JAVA_DIR = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java")
RES_DIR = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "res", "drawable")
INDEX = os.path.join(ROOT, "web", "index.html")

# 排版符号：和 Ui.kt 里 TYPO_GL<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌YPHS 一个口径（交给字体渲染，不换图标）
TYPO = set(u"→←↑↓↔↻◀▶▸▾★☆·")
ZW = re.compile(u"[\u200b\u200c\u200d\u200e\ufe0f]")
EMOJI = re.compile(u"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF"
                   u"\u2300-\u23FF\u2190-\u21FF\U0001F1E6-\U0001F1FF]")
MAP_LINE = re.compile(u'^    "([^"]+)" to R\\.drawable\\.(ic_[a-z0-9_]+),', re.M)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def kotlin_files():
    out = []
    for dirpath, _dirs, files in os.walk(JAVA_DIR):
        for f in files:
            if f.endswith(".kt"):
                out.append(os.path.join(dirpath, f))
    return out


def main():
    print("=" * 62)
    print(u"安卓端图标系统审计")
    print("=" * 62)
    if not os.path.isfile(UI):
        print(u"找不到 %s" % UI)
        return 1
    ui = io.open(UI, encoding="utf-8").read()

    emoji_to_res = dict(MAP_LINE.findall(ui))
    res_names = set(emoji_to_res.values())

    print(u"\n== ① 映射引用的 drawable 必须真的存在 ==")
    have = set(f[:-4] for f in os.listdir(RES_DIR) if f.endswith(".xml"))
    missing = sorted(n for n in res_names if n not in have)
    check(u"全部 %d 个映射都有对应 drawable" % len(res_names), not missing,
          u"缺文件：%s" % "、".join(missing))

    print(u"\n== ② 生成了的 drawable 不该是孤儿 ==")
    orphan = sorted(n for n in have if n.startswith("ic_") and n not in res_names)
    check(u"没有无人引用的 ic_*.xml", not orphan, u"孤儿：%s" % "、".join(orphan))

    print(u"\n== ③ 映射必须都在 web 的 ICONS 里（两边同源）==")
    idx = io.open(INDEX, encoding="utf-8").read()
    icons_block = re.search(r"var ICONS = \{(.*?)\n\};", idx, re.S)
    icons = set(re.findall(u"'([^']+)': _ic\\(", icons_block.group(1))) if icons_block else set()
    drifted = sorted(e for e in emoji_to_res if e not in icons)
    check(u"映射里的 %d 个 emoji 都在 ICONS 中" % len(emoji_to_res), not drifted,
          u"ICONS 里没有：%s" % " ".join(drifted))

    print(u"\n== ④ 安卓界面里行首 emoji 都要有图标 ==")
    gap = {}
    total = 0
    str_re = re.compile(u'"([^"\n]*)"')
    for path in kotlin_files():
        text = io.open(path, encoding="utf-8", errors="ignore").read()
        for m in str_re.finditer(text):
            s = ZW.sub(u"", m.group(1))
            hit = EMOJI.search(s)
            if not hit:
                continue
            if s[:hit.start()].strip():
                continue  # 只看行首
            total += 1
            e = hit.group(0)
            if e in TYPO or e in emoji_to_res:
                continue
            gap.setdefault(e, 0)
            gap[e] += 1
    detail = u"、".join(u"%s x%d" % (k, gap[k]) for k in sorted(gap, key=lambda k: -gap[k]))
    check(u"行首 emoji（%d 处）都有图标" % total, not gap, u"露出来的：%s" % detail)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
