# -*- coding: utf-8 -*-
"""界面文案 emoji 清零 —— 网页侧守护。

为什么需要
----------
2026-12 用户原话：**界面文案里一个 emoji 字符都不许有**，图标必须走内置的
Material Symbols 字体。之前的状态是"能显示成图标"：`web/index.html` 的 iconifyText
会在运行期把任意位置的 emoji 换成 `<span class="ms">名字</span>` —— 界面看着没问题，
但**源码/文案里仍然是 emoji 字符**，换个渲染路径（导出的 HTML、复制到剪贴板、
字号/字体没加载时）就露回彩色 emoji。

现在的规矩
----------
  · 源里写**图标名**，不写 emoji：文本位写 `[ic:名字]`（现成的静态标记语法，
    由 iconifyText 换成 `<span class="ms">`），文案表里的行首图标位写作
    `data-i18n-prefix="[ic:名字] "`（applyI18n 覆盖 textContent 时靠它带出图标）；
  · 不能渲染图标的地方（HTML 注释 / 标签属性 / native alert·confirm·prompt /
    CSS 注释 / `<option>`）**直接不许有 emoji**，只能写文字。

这条链上最容易悄悄坏的三处：
  · 有人又往界面里贴 emoji（"看着能用"就过）→ 本测试红；
  · `data-i18n` 元素的图标前缀被顺手删了 → 换语言后图标消失（本测试红）；
  · `[ic:名字]` 被写进属性里 → 用户直接看到 "[ic:folder]" 这种字面量（本测试红）。

跑法：utau_env\\Scripts\\python.exe -X utf8 tests\\test_no_emoji_ui.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WEB = os.path.join(ROOT, "web")
ICONS = os.path.join(ROOT, "icons", "icons.json")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PASS = 0
FAIL = 0

# 排版符号：交给字体直接画，不算 emoji（与 Ui.kt 的 TYPO<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌_GLYPHS、index.html 的 _ICON_SKIP 同口径）
TYPO = set(u"→←↑↓↔↻◀▶▸▾★☆·")
EMOJI = re.compile(u"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF"
                   u"\u2300-\u23FF\u2190-\u21FF\U0001F1E6-\U0001F1FF]")
ZW = re.compile(u"[\u200b\u200c\u200d\u200e\ufe0f\u20e3]")
MARKER = re.compile(u"\\[ic:([a-z0-9_]+)\\]")
NAME_OK = re.compile(u"^[a-z0-9_]+$")

# 有意排除（每条都必须写清理由；下面还有一条断言防止白名单偷偷变长）
EXCLUDE = {
    "web/icons.js": u"生成物：emoji → 图标名 的唯一数据表，键本来就是 emoji",
    "web/i18n.js": u"生成物：由 lang/strings.json 生成，那份表由 tests/test_i18n_langs.py 守",
    "web/gothic_frame.html": u"独立美术页：五个预览按钮的 emoji 由 data-icon-scope 渲染成图标"
                             u"（tests/test_icon_scopes.py ⑤ 钉死「数据仍是 emoji」）",
    "web/live2d/vendor/pixi.min.js": u"第三方库（压缩产物，非界面文案）",
    "web/icon_scope.js": u"作用域图标替换器本身：注释里提到 emoji 才举例",
}
# 整目录跳过：第三方 / 字体 / 图片 / 文档（文档不是界面文案）
SKIP_DIRS = {"node_modules", "live2d", "fonts", "icons", "gothic_img"}
BIN_EXT = {".woff2", ".ttf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".svg",
           ".mp3", ".wav", ".json", ".md"}


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


def emojis(s):
    return [c for c in EMOJI.findall(ZW.sub(u"", s)) if c not in TYPO]


def web_files(exts):
    out = []
    for dp, dirs, fs in os.walk(WEB):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(fs):
            if os.path.splitext(f)[1].lower() not in exts:
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            if rel in EXCLUDE:
                continue
            out.append((p, rel))
    return out


# ============================================================
#  判定器：按"渲染位置"判断一个 emoji 该不该存在
# ============================================================
def html_offenders(text):
    """HTML：注释/属性里的 emoji 一律违规；文本位也不许有（那该写 [ic:名字]）。"""
    bad = []
    # 1) 注释
    for m in re.finditer(u"<!--.*?-->", text, re.S):
        for c in emojis(m.group(0)):
            bad.append((text.count("\n", 0, m.start()) + 1, c, u"HTML 注释"))
    # 2) 裸文本 + 属性：把每行拆成 标签/文本 扫
    for i, line in enumerate(text.split("\n"), 1):
        for c in emojis(line):
            bad.append((i, c, u"HTML 里"))
    return bad


def js_offenders(text):
    """JS：字符串字面量里的 emoji 违规（注释不算界面文案）。"""
    bad = []
    i, n = 0, len(text)
    in_str = None
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            else:
                if ch not in TYPO and EMOJI.match(ZW.sub(u"", ch)):
                    bad.append((text.count("\n", 0, i) + 1, ch, u"JS 字符串"))
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
        i += 1
    return bad


def css_offenders(text):
    """CSS：注释之外的 emoji 才违规（content: "…" 这类会真的画出来）。"""
    bad = []
    stripped = re.sub(u"/\\*.*?\\*/", u"", text, flags=re.S)
    for i, line in enumerate(stripped.split("\n"), 1):
        for c in emojis(line):
            bad.append((i, c, u"CSS 内容"))
    return bad


def markers_in_attr(text):
    """`[ic:名字]` 只允许在文本位或 data-i18n-prefix 里；写进别的属性＝用户看到字面量。"""
    bad = []
    for i, line in enumerate(text.split("\n"), 1):
        for m in MARKER.finditer(line):
            before = line[:m.start()]
            lt, gt = before.rfind("<"), before.rfind(">")
            if lt > gt and 'data-i18n-prefix="' not in before[lt:]:
                bad.append((i, line.strip()[:80]))
    return bad


def lig_names(path):
    """字体里的连字名（= 能画出来的图标名）。表里找不到就是豆腐块/名字本身。"""
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
    print(u"界面文案 emoji 清零（网页侧：图标一律走 [ic:名字] / data-i18n-prefix）")
    print("=" * 62)

    # ---------------- ① 标记里的图标名必须真的能画出来 ----------------
    # `[ic:名字]` 现在有两种解析：具名表（go/sprite/play…）里查得到就用表里的字形，
    # 查不到就**把名字当连字名直接画**（见 index.html 的 _iconLookup）。
    # 后一种没有任何编译期检查，所以这里按字体连字表把关：名字不在字体里 = 界面上
    # 露出的是名字本身（"folder" 这几个字母），只有靠这条断言才拦得住。
    print(u"\n== ① 标记里的图标名必须在字体里真的有 ==")
    import json
    icons = json.loads(read(ICONS)).get("icons") or {}
    named_tbl = set(m.group(1) for m in
                    re.finditer(u'"([a-z0-9_]+)"\\s*:\\s*\\{', read(os.path.join(WEB, "icons.js"))))
    used = {}
    for p, rel in web_files({".html", ".js"}):
        for m in MARKER.finditer(read(p)):
            used.setdefault(m.group(1), set()).add(rel)
    check(u"页面里用了 [ic:名字] 标记（%d 个不同名字 / %d 个文件）"
          % (len(used), len(set().union(*used.values()) if used else set())), bool(used))
    badname = sorted(n for n in used if not NAME_OK.match(n))
    check(u"标记里的图标名都是合法小写/数字/下划线", not badname, u"、".join(badname[:6]))
    try:
        import fontTools  # noqa: F401
        have = lig_names(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "res",
                                      "font", "material_symbols_outlined.ttf"))
        miss = sorted(n for n in used if n not in named_tbl and n not in have)
        check(u"标记里的 %d 个图标名都能在字体里画出来（缺 %d 个）" % (len(used), len(miss)),
              not miss, u"字体里没有：%s" % u"、".join(miss[:8]))
    except Exception as e:      # pragma: no cover
        print(u"   [SKIP] 字体连字表查不了（%s）；pip install -r requirements-test.txt" % e)
    check(u"文案表里那几个具名标记仍在（go/play…）",
          any(n in named_tbl for n in used), u"具名表：%s" % sorted(named_tbl)[:6])

    # ---------------- ② HTML / JS / CSS 里 emoji = 0 ----------------
    print(u"\n== ② 页面 / 脚本 / 样式里 emoji 出现次数 = 0 ==")
    offenders = []
    for p, rel in web_files({".html"}):
        offenders += [(rel,) + x for x in html_offenders(read(p))]
    check(u"HTML 里 emoji = 0（%d 处）" % len(offenders), not offenders,
          u"；".join(u"%s:%d %s(%s)" % o for o in offenders[:6]))
    offenders = []
    for p, rel in web_files({".js"}):
        offenders += [(rel,) + x for x in js_offenders(read(p))]
    check(u"JS 字符串里 emoji = 0（%d 处）" % len(offenders), not offenders,
          u"；".join(u"%s:%d %s(%s)" % o for o in offenders[:6]))
    offenders = []
    for p, rel in web_files({".css"}):
        offenders += [(rel,) + x for x in css_offenders(read(p))]
    check(u"CSS 内容里 emoji = 0（%d 处）" % len(offenders), not offenders,
          u"；".join(u"%s:%d %s(%s)" % o for o in offenders[:6]))

    # ---------------- ③ 标记不许掉进属性里 ----------------
    print(u"\n== ③ [ic:名字] 只出现在文本位 / data-i18n-prefix 里 ==")
    bad = []
    for p, rel in web_files({".html", ".js"}):
        bad += [(rel,) + x for x in markers_in_attr(read(p))]
    check(u"没有标记写进标签属性（%d 处）" % len(bad), not bad,
          u"；".join(u"%s:%d %s" % b for b in bad[:5]))

    # ---------------- ④ data-i18n 元素的图标前缀 ----------------
    print(u"\n== ④ data-i18n 元素的图标前缀（换语言后图标不能丢）==")
    RE_UNIT = re.compile(u"<([a-zA-Z][a-zA-Z0-9]*)"
                         u"((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>([^<]*)", re.S)
    RE_I18N = re.compile(u'data-i18n="([A-Za-z_][A-Za-z0-9_]*)"')
    RE_PRE = re.compile(u'data-i18n-prefix="\\[ic:[a-z0-9_]+\\] "')
    prefixed, missing = 0, []
    for p, rel in web_files({".html"}):
        text = read(p)
        for m in RE_UNIT.finditer(text):
            head, txt = m.group(2), m.group(3)
            if not RE_I18N.search(head):
                continue
            if RE_PRE.search(head):
                prefixed += 1
            elif MARKER.search(txt):
                missing.append((rel, text.count("\n", 0, m.start()) + 1,
                                RE_I18N.search(head).group(1)))
    check(u"有带图标前缀的 data-i18n 元素（%d 个）" % prefixed, prefixed > 0)
    check(u"文本里带 [ic:] 的 data-i18n 元素都补了前缀（漏 %d 个）" % len(missing), not missing,
          u"；".join(u"%s:%d %s" % x for x in missing[:6]))

    # ---------------- ⑤ 判定器自检（该红必须红） ----------------
    print(u"\n== ⑤ 判定器自检 ==")
    samples = [
        (u'<button class="btn">\U0001F4C2 存档列表</button>', html_offenders, True,
         u"HTML 文本位贴 emoji"),
        (u'<title="\U0001F50D 搜索">', html_offenders, True, u"HTML 属性里贴 emoji"),
        (u'<!-- \U0001F4D6 面板 -->', html_offenders, True, u"HTML 注释里的 emoji"),
        (u'<button>[ic:folder] 存档列表</button>', html_offenders, False, u"标记不算 emoji"),
        (u"el.innerHTML = '\u2705 已保存';", js_offenders, True, u"JS 字符串里的 emoji"),
        (u"// \u2705 已保存（注释不是文案）", js_offenders, False, u"JS 注释里不算"),
        (u"var a = '[ic:save] 保存';", js_offenders, False, u"JS 里的标记不算"),
        (u'.x{ content: "\u2705"; }', css_offenders, True, u"CSS 内容里的 emoji"),
        (u"/* \u2705 说明 */ .x{color:red}", css_offenders, False, u"CSS 注释里不算"),
        (u'<button title="[ic:save]">x</button>', markers_in_attr, True, u"标记写进属性"),
        (u'<button data-i18n-prefix="[ic:save] ">[ic:save] 保存</button>', markers_in_attr, False,
         u"前缀属性里的标记是合法的"),
    ]
    for code, fn, should_hit, why in samples:
        got = bool(fn(code))
        check(u"判定器自检：%s → %s" % (why, u"判红" if should_hit else u"放行"),
              got == should_hit)

    # ---------------- ⑥ 白名单不许偷偷变长 ----------------
    print(u"\n== ⑥ 排除清单（每条都要有理由，且不许变长）==")
    check(u"排除清单不超过 5 条（现在 %d 条）" % len(EXCLUDE), len(EXCLUDE) <= 5,
          u"、".join(sorted(EXCLUDE)))
    check(u"排除清单每条都写了理由", all(str(v).strip() for v in EXCLUDE.values()))
    check(u"排除的每个文件都真的存在",
          all(os.path.isfile(os.path.join(ROOT, k)) for k in EXCLUDE),
          u"、".join(k for k in EXCLUDE if not os.path.isfile(os.path.join(ROOT, k))))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("NO_EMOJI_UI_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
