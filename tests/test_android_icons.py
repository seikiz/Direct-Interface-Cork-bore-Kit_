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


# ---------------- ⑦ 的判定器（句子中间 emoji 会不会露成彩色） ----------------
# 内容类消费方：这些是**内容**（聊天消息正文由模型/用户填），不是 UI 图标，允许带 emoji。
# 每条都必须写清理由 —— 白名单只该给"内容不是图标"的地方。
CONTENT_CONSUMERS = {
    "ChatMsg": "聊天消息对象（正文是内容，不是 UI 图标）",
}
# I18n.t 这类只是「取文案」的中转壳，真正的消费方在更外层
TRANSPARENT_CALLS = ("t", "format", "trim", "toString")
STR_LIT = re.compile(r'"((?:[^"\\]|\\.)*)"')
CALL_NAME = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*$")
FUN_HEAD = re.compile(r"^\s*(?:private\s+|internal\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _walk_kt(base):
    out = []
    for dirpath, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in ("build", ".gradle"))
        for fn in sorted(files):
            if fn.endswith(".kt"):
                out.append(os.path.join(dirpath, fn))
    return out


def _ui_strings(text):
    """[(行号, 字面量内容, 起点)] —— 只认双引号字符串（够用：UI 文案都是双引号）。"""
    for m in STR_LIT.finditer(text):
        yield text.count("\n", 0, m.start()) + 1, m.group(1), m.start()


def _first_string(text):
    for _line, s, pos in _ui_strings(text):
        return s, pos
    return None


def _consumer_of(text, pos, depth_limit=4):
    """字面量往外第一层「非透明壳」的调用名 → (名字, 是不是直接调用)。

    例：`Body(I18n.t("k", "…🚀"))` → ("Body", False)；
        `Text("…🚀")`            → ("Text", True)。
    """
    i, depth, found = pos - 1, 0, []
    while i > 0 and len(found) < depth_limit:
        c = text[i]
        if c == ")":
            depth += 1
        elif c == "(":
            if depth == 0:
                m = CALL_NAME.search(text[max(0, i - 60):i + 1])
                if m:
                    found.append(m.group(1))
            else:
                depth -= 1
        i -= 1
    real = [n for n in found if n not in TRANSPARENT_CALLS]
    if not real:
        return (found[0] if found else "?"), True
    return real[0], len(real) == len(found)


def _plain_text_wrappers(text):
    """文件里「自己包一层纯 Text」的小函数名集合（ApiGuideScreen 的 Body/SecTitle 那种）。

    判据：函数体里有 `Text(`，但**没有**任何一个会替换图标的组件
    （IconText / DickTag / DickTextButton / DickActionButton / DickLoading /…）。
    """
    funcs, cur, buf = set(), None, []
    for line in text.split("\n"):
        m = FUN_HEAD.match(line)
        if m:
            if cur is not None:
                funcs.add((cur, "\n".join(buf)))
            # 函数体可能和签名写在同一行（`fun Body(s: String) { Text(s) }`），
            # 所以签名那行的剩余部分也算进函数体，别漏掉单行小函数。
            cur, buf = m.group(1), [line[m.end():]]
            continue
        if cur is not None:
            buf.append(line)
    if cur is not None:
        funcs.add((cur, "\n".join(buf)))
    out = set()
    for name, body in funcs:
        if "Text(" not in body:
            continue
        if any(k in body for k in ("IconText(", "DickTag(", "DickTextButton(",
                                   "DickActionButton(", "DickButton(", "DickLoading(",
                                   "DickEmptyState(", "MsIcon(")):
            continue
        out.add(name)
    return out


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

    # ------------------------------------------------------------------
    # ⑦ 句子中间的 emoji（2026-12 用户重申「图标都换成谷歌那种」）
    # ------------------------------------------------------------------
    # 先纠正一个容易搞错的前提：IconText **不只处理行首** —— splitEmojiSegments 会把
    # 任意位置的 emoji 换成 Material 图标（InlineTextContent），所以「句中有 emoji」本身
    # 不是毛病。真正会露成彩色 emoji 的只有三条路：
    #   ① emoji 在 IconNames 里**没有名字** → IconText 跳过它，原样显示彩色 emoji；
    #   ② 这段文字走的是**纯 Text**（Text/BasicText 直贴字面量）→ 没有任何人替换；
    #   ③ 这段文字走的是「自己包一层 Text 的小函数」（ApiGuideScreen 的 Body/SecTitle
    #      就是这种）→ 同样没人替换，而且只看 `Text("…")` 是扫不到的。
    # 三条都守死之后，句中 emoji 只可能落在「会替换成图标」的组件里，也就是用户要的那种。
    # （不写成「除行首出现次数 = 0」：那会把 200 多处**已经正常显示成图标**的句中图标
    #   一起判死，等于为了指标砍功能。）
    print(u"\n== ⑦ 句子中间的 emoji：有图标名 + 不被纯 Text 吞掉 ==")
    ui_dir = os.path.join(JAVA_DIR, "com", "dick", "app", "ui")
    bad_nomap, bad_plain, bad_wrapper = [], [], []
    ui_total = 0
    for p in _walk_kt(ui_dir):
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        text = io.open(p, encoding="utf-8", errors="ignore").read()
        plain_funcs = _plain_text_wrappers(text)
        for line, s, pos in _ui_strings(text):
            hits = [e.group(0) for e in EMOJI.finditer(ZW.sub(u"", s))]
            hits = [e for e in hits if e not in TYPO]
            if not hits:
                continue
            ui_total += 1
            miss = [e for e in hits if e not in icons]
            if miss:
                bad_nomap.append((rel, line, u"、".join(miss), s[:40]))
            consumer, direct = _consumer_of(text, pos)
            if direct and consumer in ("Text", "BasicText"):
                bad_plain.append((rel, line, consumer, s[:50]))
            elif consumer in plain_funcs and consumer not in CONTENT_CONSUMERS:
                bad_wrapper.append((rel, line, consumer, s[:50]))
    check(u"UI 里带 emoji 的字面量（%d 处）的 emoji 都有图标名" % ui_total, not bad_nomap,
          u"；".join(u"%s:%d %s" % (r[0], r[1], r[2]) for r in bad_nomap[:6]))
    check(u"没有 emoji 直接贴在 Text/BasicText 里（%d 处）" % len(bad_plain), not bad_plain,
          u"；".join(u"%s:%d %s(%s)" % (r[0], r[1], r[2], r[3]) for r in bad_plain[:5]))
    check(u"没有 emoji 被「自己包的纯 Text 函数」吞掉（%d 处）" % len(bad_wrapper),
          not bad_wrapper,
          u"；".join(u"%s:%d %s(%s)" % (r[0], r[1], r[2], r[3]) for r in bad_wrapper[:5]))
    check(u"内容类白名单 ≤3（现在 %d 个：%s）"
          % (len(CONTENT_CONSUMERS), u"、".join(sorted(CONTENT_CONSUMERS))),
          len(CONTENT_CONSUMERS) <= 3)
    check(u"白名单里的 ChatMsg 是聊天内容（写得出来理由）",
          CONTENT_CONSUMERS.get("ChatMsg", u"").strip() != u"")

    # 判定器自检：拿已知样本喂进去，该红必须红（防止把判定改成"什么都能过"）
    samples = [
        (u'@Composable fun A() { Text("点 🚀 开始") }', u"Text 直贴", True),
        (u'@Composable\nfun B(s: String) { Text(s) }\n@Composable\nfun C() { B("点 🚀 开始") }',
         u"自己包的纯 Text 函数", True),
        (u'@Composable fun D() { IconText("点 🚀 开始") }', u"IconText", False),
        (u'@Composable fun E() { DickTag("❤ 好感") }', u"DickTag", False),
        (u'@Composable fun F() { ChatMsg("系统", "点 🚀 开始") }', u"ChatMsg（聊天内容）", False),
    ]
    for code, why, should_fail in samples:
        one = _first_string(code)
        if one is None:
            check(u"判定器自检：%s 里找得到字符串" % why, False, code)
            continue
        s, pos = one
        plain_funcs = _plain_text_wrappers(code)
        consumer, direct = _consumer_of(code, pos)
        got = ((direct and consumer in ("Text", "BasicText")) or
               (consumer in plain_funcs and consumer not in CONTENT_CONSUMERS))
        check(u"判定器自检：%s → %s" % (why, u"判红" if should_fail else u"放行"),
              got == should_fail, u"consumer=%s direct=%s got=%s" % (consumer, direct, got))

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ICONS_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
