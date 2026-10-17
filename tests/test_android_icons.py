# -*- coding: utf-8 -*-
"""图标系统审计：Material Symbols 两端一致（唯一真相 icons/icons.json）。

为什么需要
----------
图标从"手写内联 SVG + 108 个生成 VectorDrawable"换成了 **Material Symbols 字体渲染**：
网页端 `@font-face` + 连字（`<span class="ms">名字</span>`），安卓端同一份字体走 Compose。
唯一真相是 `icons/icons.json`（emoji → 图标名），两端产物由 `tools/gen_icons.py` 生成。

这条链上最容易悄悄坏的两处：
  · **图标名在字体里不存在** —— 界面上就是空白/豆腐块，而且只有点进那个界面才发现；
  · 产物过期（改了 json 忘了生成）—— 两端各显示一套，正是"两端漂"的老毛病。

跑法：python tests/test_android_icons.py
"""
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 这个脚本会打印图标名与 emoji（含 ↺ 这类非 GBK 字<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌符）：GBK 控制台下会 UnicodeEncodeError
# 变红，而"测试失败"其实只是控制台编码问题。显式把 stdout 拧成 UTF-8（与 test_space_core.py 一致）。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
SRC = os.path.join(ROOT, "icons", "icons.json")
WEB_JS = os.path.join(ROOT, "web", "icons.js")
KT_OUT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                      "app", "IconNames.kt")
WEB_FONT = os.path.join(ROOT, "web", "fonts", "MaterialSymbolsOutlined.woff2")
AND_FONT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "res", "font",
                        "material_symbols_outlined.ttf")
LICENSE = os.path.join(ROOT, "web", "fonts", "LICENSE")
INDEX = os.path.join(ROOT, "web", "index.html")
# 2026-11 阶段1：页面里的 <style> 已原样拆到 web/styles/（按层叠顺序 link 进来）。
# @font-face 与 .ms 现在住在 CSS 文件里，所以"网页端有没有换成字体渲染"要看页面 + 样式两边。
WEB_STYLES = os.path.join(ROOT, "web", "styles")


def web_front():
    """index.html + web/styles/*.css 拼起来的文本（检查前端特征串用）。"""
    parts = [read(INDEX)]
    if os.path.isdir(WEB_STYLES):
        for fn in sorted(os.listdir(WEB_STYLES)):
            if fn.endswith(".css"):
                parts.append(read(os.path.join(WEB_STYLES, fn)))
    return u"\n".join(parts)
UI = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "Ui.kt")
JAVA_DIR = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java")
DRAW_DIR = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "res", "drawable")

# 排版符号：与 Ui.kt / web 的 _ICON_SKIP 一个口径（交给字体渲染，不换图标）
TYPO = set(u"→←↑↓↔↻◀▶▸▾★☆·")
ZW = re.compile(u"[\u200b\u200c\u200d\u200e\ufe0f]")
EMOJI = re.compile(u"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF"
                   u"\u2300-\u23FF\u2190-\u21FF\U0001F1E6-\U0001F1FF]")

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


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def kotlin_files():
    out = []
    for dirpath, _dirs, files in os.walk(JAVA_DIR):
        for f in files:
            if f.endswith(".kt") and os.path.abspath(os.path.join(dirpath, f)) != os.path.abspath(KT_OUT):
                out.append(os.path.join(dirpath, f))
    return out


def ligs(path):
    """字体里的连字名（键=首字形；underscore 还原成 _）。"""
    from fontTools.ttLib import TTFont
    f = TTFont(path, lazy=True)
    try:
        gsub = f["GSUB"].table
        out = set()
        for fr in gsub.FeatureList.FeatureRecord:
            if fr.FeatureTag not in ("rlig", "liga"):
                continue
            for i in fr.Feature.LookupListIndex:
                for st in gsub.LookupList.Lookup[i].SubTable:
                    real = getattr(st, "ExtSubTable", st)
                    for first, arr in (getattr(real, "ligatures", None) or {}).items():
                        for l in arr:
                            out.add((first + "".join(l.Component)).replace("underscore", "_"))
        return out
    finally:
        f.close()


def main():
    print("=" * 62)
    print(u"图标系统审计（Material Symbols，两端同一份真相）")
    print("=" * 62)

    print(u"\n== ① 唯一真相 icons/icons.json ==")
    check(u"icons/icons.json 在", os.path.isfile(SRC))
    data = json.loads(read(SRC))
    icons, named = data.get("icons") or {}, data.get("named") or {}
    check(u"emoji 条数正常（%d）" % len(icons), len(icons) >= 120, str(len(icons)))
    check(u"具名条数正常（%d）" % len(named), len(named) >= 3, str(len(named)))
    bad = [k for k, v in list(icons.items()) + list(named.items())
           if not isinstance(v, dict) or not re.match(r"^[a-z0-9_]+$", str(v.get("name") or ""))]
    check(u"每条都有合法图标名（小写/数字/下划线）", not bad, u"问题条目：%s" % bad[:6])
    check(u"写了风格口径（_style）", bool(str(data.get("_style") or "").strip()))

    print(u"\n== ② 名字必须在字体里真的有（这条是地基）==")
    try:
        import fontTools  # noqa: F401
    except Exception:
        check(u"fontTools 可用（requirements-test.txt 里有 fonttools）", False,
              u"装一下：pip install -r requirements-test.txt")
        fontTools = None
    try:
        import brotli  # noqa: F401
        has_brotli = True
    except Exception:
        # brotli 只在读 **woff2** 时需要；缺它就把这一份显式跳过（CI 装了 brotli，会全查）
        has_brotli = False
    check(u"brotli 已声明在 requirements-test.txt（读 woff2 要用）",
          "brotli" in read(os.path.join(ROOT, "requirements-test.txt")))
    names = sorted(set([v["name"] for v in icons.values()] + [v["name"] for v in named.values()]))
    for label, path, magic in ((u"网页 woff2", WEB_FONT, b"wOF2"),
                               (u"安卓 ttf", AND_FONT, b"\x00\x01\x00\x00")):
        if not os.path.isfile(path):
            check(u"%s 在仓库里" % label, False, os.path.relpath(path, ROOT))
            continue
        with open(path, "rb") as f:
            head = f.read(4)
        check(u"%s 存在且文件头正确" % label, head == magic,
              u"%s (%r)" % (os.path.relpath(path, ROOT), head))
        if fontTools is None:
            continue
        if magic == b"wOF2" and not has_brotli:
            print(u"   [SKIP] %s 的连字表：本机缺 brotli（pip install -r requirements-test.txt）；"
                  u"安卓 ttf 那份仍然照查" % label)
            continue
        have = ligs(path)
        miss = [n for n in names if n not in have]
        check(u"%s 里 %d 个图标名全部命中（共 %d 个连字）" % (label, len(names), len(have)),
              not miss, u"缺：%s" % u"、".join(miss[:8]))
    check(u"LICENSE 在（Apache-2.0）", os.path.isfile(LICENSE))

    print(u"\n== ③ 产物由生成器出、且是最新的 ==")
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_icons.py"), "--check"],
                          cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    check(u"gen_icons --check 通过（产物与 json 一致）", proc.returncode == 0,
          out.strip().replace("\n", " | ")[:300])
    check(u"web/icons.js 在", os.path.isfile(WEB_JS))
    check(u"IconNames.kt 在（安卓产物）", os.path.isfile(KT_OUT))
    kt = read(KT_OUT) if os.path.isfile(KT_OUT) else ""
    check(u"生成的 Kotlin 带「生成物」抬头", u"生成物" in kt and u"别手改" in kt)
    check(u"生成的 Kotlin 两张表都在",
          "val ICON_NAME_BY_EMOJI" in kt and "val ICON_NAME_BY_KEY" in kt)
    js = read(WEB_JS) if os.path.isfile(WEB_JS) else ""
    check(u"web/icons.js 两张表都在",
          "DICK_ICONS" in js and "DICK_ICON_NAMES" in js)
    # 抽一个键逐字比对（防"生成器写了个空表"）——两端产物各比一次
    probe = sorted(icons.items())[0]
    want_js = u'"%s": { n: "%s"' % (probe[0], probe[1]["name"])
    want_kt = u'"%s" to "%s"' % (probe[0], probe[1]["name"])
    check(u"抽样一致（js）：%s → %s" % (probe[0], probe[1]["name"]), want_js in js,
          js[:120].replace("\n", " "))
    check(u"抽样一致（kt）：%s → %s" % (probe[0], probe[1]["name"]), want_kt in kt,
          kt[:120].replace("\n", " "))

    print(u"\n== ④ 网页端已换成字体渲染 ==")
    idx = read(INDEX)
    front = web_front()
    check(u"没有残留的内联 SVG 图标字典", "var ICONS = {" not in idx)
    check(u"没有残留的 ICON_FILES / NAMED_ICONS / ICONS_BY_SLUG",
          not any(s in idx for s in ("var ICON_FILES", "var NAMED_ICONS", "ICONS_BY_SLUG")))
    check(u"引用了 icons.js", "icons.js" in idx)
    check(u"有 @font-face 指向随包字体",
          "@font-face" in front and "fonts/MaterialSymbolsOutlined.woff2" in front)
    check(u"有 .ms 图标样式（连字渲染）", ".ms{" in front and "liga" in front)
    check(u"替换逻辑走图标名（<span class=\"ms\">）", 'class="ms"' in idx)
    check(u"缺失名字时回退原 emoji（不显示空白）", "_iconEntry(emoji)" in idx or "return emoji" in idx)

    print(u"\n== ⑤ 安卓端已换成字体渲染 ==")
    ui = read(UI)
    check(u"Ui.kt 用生成的图标名表", "ICON_NAME_BY_EMOJI" in ui)
    check(u"Ui.kt 定义了字体与 MsIcon", "MaterialSymbols" in ui and "fun MsIcon(" in ui)
    check(u"Ui.kt 里没有旧的 drawable 映射", "EMOJI_RES" not in ui and "R.drawable.ic_" not in ui)
    check(u"IconText 两条路径都用 MsIcon", ui.count("MsIcon(") >= 3, str(ui.count("MsIcon(")))
    left = []
    for dirpath, _d, files in os.walk(DRAW_DIR):
        for f in files:
            if f.startswith("ic_") and f.endswith(".xml"):
                left.append(f)
    check(u"旧的 res/drawable/ic_*.xml 已删干净", not left, u"还剩 %d 个" % len(left))
    for stale in ("tools/gen_android_icons.py", "_android_icon_map.txt"):
        check(u"旧工具/映射表已删：%s" % stale, not os.path.isfile(os.path.join(ROOT, stale)))

    print(u"\n== ⑥ 安卓界面里行首 emoji 都要有图标 ==")
    gap, total = {}, 0
    str_re = re.compile(u'"([^"\n]*)"')
    for path in kotlin_files():
        text = io.open(path, encoding="utf-8", errors="ignore").read()
        for m in str_re.finditer(text):
            s = ZW.sub(u"", m.group(1))
            hit = EMOJI.search(s)
            if not hit or s[:hit.start()].strip():
                continue
            total += 1
            e = hit.group(0)
            if e in TYPO or e in icons:
                continue
            gap[e] = gap.get(e, 0) + 1
    detail = u"、".join(u"%s x%d" % (k, gap[k]) for k in sorted(gap, key=lambda k: -gap[k]))
    check(u"行首 emoji（%d 处）都有图标" % total, not gap, u"露出来的：%s" % detail)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ICONS_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
