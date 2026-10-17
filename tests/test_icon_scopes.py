# -*- coding: utf-8 -*-
"""图标作用域（scoped）审计：预览按钮用字体图标，但**不许**污染全局映射表。

为什么需要
----------
`icons/icons.json` 的全局 `icons` 段是「整个界面 + 正文」共用的：往里加一个 emoji，
卡片/世界卡正文里同样的 emoji 也会被一起换成字体图标。`web/gothic_frame.html` 顶部
那五个预览按钮（📜 🦇 ⛪ 🔥 💀）想用图标，就只能走**作用域**：只在标了
`data-icon-scope="gothic"` 的根内替换，别处一个文本节点都不碰。

这条链上最容易悄悄坏的三处（都是"界面上看得出来、测试看不出来"的类型）：
  · 图省事把 💀/⛪ 加进全局表 —— 正文被一起换掉，只有玩家看出来；
  · 生成器忘了输出 scoped 段 —— 按钮退回彩色 emoji，不报错；
  · 安卓产物被 scoped 污染 —— IconNames.kt 里多出正文根本不该有的映射。

跑法：utau_env\\Scripts\\python.exe -X utf8 tests\\test_icon_scopes.py
"""
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 这个脚本会打印 emoji（含非 GBK 字符）：GBK <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌控制台下会 UnicodeEncodeError 变红，
# 而"测试失败"其实只是控制台编码问题 —— 显式把 stdout 拧成 UTF-8。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
SRC = os.path.join(ROOT, "icons", "icons.json")
WEB_JS = os.path.join(ROOT, "web", "icons.js")
SCOPE_JS = os.path.join(ROOT, "web", "icon_scope.js")
GOTHIC = os.path.join(ROOT, "web", "gothic_frame.html")
INDEX = os.path.join(ROOT, "web", "index.html")
KT_OUT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                      "app", "IconNames.kt")
WEB_FONT = os.path.join(ROOT, "web", "fonts", "MaterialSymbolsOutlined.woff2")
AND_FONT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "res", "font",
                        "material_symbols_outlined.ttf")

# ---- 作用域 gothic 的五个预览按钮（icons.json 的 scoped.gothic） ----
GOTHIC_KEYS = [u"📜", u"🦇", u"⛪", u"🔥", u"💀"]
GOTHIC_WANT = {
    u"📜": "menu_book",
    u"🦇": "dark_mode",
    u"⛪": "church",
    u"🔥": "local_fire_department",
    u"💀": "skull",
}
# 刻意【不进】全局表的三个：它们在卡片/世界卡正文里很常见，进全局就会把正文一起换掉。
SCOPED_ONLY = [u"🦇", u"⛪", u"💀"]
# 反向例外：📜 与 🔥 历史上早已在全局表里（安卓 Dialogs.kt 的 IconText、网页 index.html、
# lang/strings.json 的「📜 滚动摘要」都在用）。把它们从全局删掉是**回归**：
# 安卓对话框与网页会退回彩色 emoji，tests/test_android_icons.py ⑥ 也会直接变红。
# 所以这里钉死「全局与作用域只允许这两个键重叠」，别再多、也别想着去删它们。
LEGACY_OVERLAP = {u"📜", u"🔥"}
# 全局表的条数：钉死，防"顺手加一条"或"顺手删一条"。
# 改这里 = 显式承认改了全局表，必须同时确认没有把 SCOPED_ONLY 混进去。
GLOBAL_COUNT = 123
NAMED_COUNT = 6

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


def main():
    print("=" * 62)
    print(u"图标作用域审计（scoped：只换预览按钮，不污染全局表 / 正文）")
    print("=" * 62)

    data = json.loads(read(SRC))
    icons = data.get("icons") or {}
    named = data.get("named") or {}
    scoped = data.get("scoped") or {}

    print(u"\n== ① 全局表：正文绝不能跟着变 ==")
    for e in SCOPED_ONLY:
        check(u"全局 icons 里没有 %s" % e, e not in icons,
              u"它只该出现在 scoped.gothic；进了全局就会把卡片/世界卡正文一起换掉")
    check(u"全局具名表也没被污染", not [k for k in named if k in GOTHIC_KEYS])
    check(u"全局 emoji 条数未变（%d）" % len(icons), len(icons) == GLOBAL_COUNT,
          u"实际 %d —— 改全局表必须显式改这条断言" % len(icons))
    check(u"具名条数未变（%d）" % len(named), len(named) == NAMED_COUNT, str(len(named)))
    # 📜/🔥 是历史遗留（安卓对话框与网页都在用），必须原样留在全局表里
    for e, want in ((u"📜", "history_edu"), (u"🔥", "local_fire_department")):
        got = (icons.get(e) or {}).get("name")
        check(u"%s 仍留在全局表（%s，历史遗留：删掉就是回归）" % (e, want), got == want, str(got))

    print(u"\n== ② scoped 段：五个按钮的映射都在 ==")
    check(u"icons.json 有 scoped 段", isinstance(scoped, dict) and bool(scoped))
    check(u"scoped 段带说明（_note）", bool(str(scoped.get("_note") or "").strip()))
    gothic = scoped.get("gothic") or {}
    # `_note` 之类是注释，不算映射条目
    gothic_pairs = dict((k, v) for k, v in gothic.items() if not str(k).startswith("_"))
    check(u"scoped.gothic 是映射", isinstance(gothic, dict) and bool(gothic))
    check(u"scoped.gothic 恰好 5 条（不含 _note 注释）", len(gothic_pairs) == 5,
          u"实际 %d：%s" % (len(gothic_pairs), list(gothic_pairs)))
    for e in GOTHIC_KEYS:
        check(u"scoped.gothic 有 %s" % e, e in gothic_pairs)
    bad = [k for k, v in gothic_pairs.items() if not re.match(r"^[a-z0-9_]+$", str(v))]
    check(u"scoped 的值都是合法图标名（_ 开头的是注释，不算条目）", not bad, u"问题条目：%s" % bad)
    diffs = [u"%s=%s(期望 %s)" % (e, gothic_pairs.get(e), n) for e, n in GOTHIC_WANT.items()
             if gothic_pairs.get(e) != n]
    check(u"五个 emoji 的图标名就是选定的那五个", not diffs, u"、".join(diffs))
    overlap = set(icons) & set(GOTHIC_KEYS)
    check(u"全局表与作用域只重叠 %s（📜/🔥 是历史遗留，其余不许进全局）"
          % u"、".join(sorted(LEGACY_OVERLAP)), overlap == LEGACY_OVERLAP,
          u"实际重叠：%s" % u"、".join(sorted(overlap)))

    print(u"\n== ③ 产物：只进 web/icons.js，不进 IconNames.kt ==")
    js = read(WEB_JS) if os.path.isfile(WEB_JS) else ""
    check(u"web/icons.js 在", os.path.isfile(WEB_JS))
    check(u"web/icons.js 有 window.DICK_ICONS_SCOPED", "window.DICK_ICONS_SCOPED" in js)
    missing_js = [e for e in GOTHIC_KEYS if (u'"%s": { n: "%s"' % (e, GOTHIC_WANT[e])) not in js]
    check(u"生成的 scoped 段里五个键都在（逐字比对）", not missing_js,
          u"缺：%s" % u"、".join(missing_js))
    check(u"生成的全局表仍是 DICK_ICONS / DICK_ICON_NAMES 两张",
          "window.DICK_ICONS =" in js and "window.DICK_ICON_NAMES =" in js)
    kt = read(KT_OUT) if os.path.isfile(KT_OUT) else ""
    check(u"IconNames.kt 在（安卓产物）", os.path.isfile(KT_OUT))
    # 安卓不该有作用域这回事：既没有那张表，也没有多出来的 emoji 行
    check(u"安卓产物里没有 scoped 表", "DICK_ICONS_SCOPED" not in kt and "scoped" not in kt)
    # 只数 ICON_NAME_BY_EMOJI 那张表（具名表 ICON_NAME_BY_KEY 在同文件里，别混进来）
    m_kt = re.search(r"val ICON_NAME_BY_EMOJI[^\n]*\n(.*?)\n\)", kt, re.S)
    kt_pairs = len(re.findall(u'^\\s+"[^"]+" to "', m_kt.group(1), re.M)) if m_kt else -1
    check(u"安卓 emoji 映射条数 == 全局条数（没被 scoped 撑大）",
          kt_pairs == len(icons), u"kt %d 条 / 全局 %d 条" % (kt_pairs, len(icons)))

    print(u"\n== ④ 字体里五个名字都要真的有（复用 gen_icons 的校验）==")
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import gen_icons as G
    except Exception as e:                     # pragma: no cover - 环境问题
        check(u"能导入 tools/gen_icons.py", False, str(e))
        G = None
    if G is not None:
        try:
            import brotli  # noqa: F401
            has_brotli = True
        except Exception:
            has_brotli = False
        want = sorted(set(GOTHIC_WANT.values()))
        for label, path, magic, need_brotli in ((u"网页 woff2", WEB_FONT, b"wOF2", True),
                                               (u"安卓 ttf", AND_FONT, b"\x00\x01\x00\x00", False)):
            if not os.path.isfile(path):
                check(u"%s 在仓库里" % label, False, os.path.relpath(path, ROOT))
                continue
            with open(path, "rb") as f:
                head = f.read(4)
            check(u"%s 文件头正确" % label, head == magic, repr(head))
            if need_brotli and not has_brotli:
                # 只在读 woff2 时需要 brotli；本机缺它就显式跳过这一份（ttf 那份照查，不许静默放过）
                print(u"   [SKIP] %s 的连字表：本机缺 brotli（pip install -r requirements-test.txt）"
                      % label)
                continue
            have = G.ligature_names(path)
            miss = [n for n in want if n not in have]
            check(u"%s 里 5 个作用域图标名全部命中（共 %d 个连字）" % (label, len(have)),
                  not miss, u"缺：%s" % u"、".join(miss))

    print(u"\n== ⑤ 运行时接线：只在该根内替换 ==")
    check(u"web/icon_scope.js 在", os.path.isfile(SCOPE_JS))
    scope_src = read(SCOPE_JS) if os.path.isfile(SCOPE_JS) else ""
    check(u"导出 iconifyScoped / iconifyScopedAll",
          "window.iconifyScoped =" in scope_src and "window.iconifyScopedAll =" in scope_src)
    check(u"只认作用域映射（不回落全局表：全文没有 DICK_ICONS 的正向读取）",
          "DICK_ICONS_SCOPED" in scope_src and not re.search(r"window\.DICK_ICONS\b(?!_)", scope_src))
    skips = [w for w in ("svg", "textarea", "[data-noicon]", "code", "pre") if w not in scope_src]
    check(u"跳过口径与 index.html 一致（svg/textarea/code/pre/[data-noicon]）", not skips,
          u"缺：%s" % skips)
    # 产物里 scoped 的值是 { n: 名字, p: "" }（与全局表同形）；把它当名字用就是豆腐块
    check(u"icon_scope.js 认得产物里 { n: 名字 } 的形态", "nameOf(" in scope_src and "v.n" in scope_src)
    idx = read(INDEX)
    check(u"index.html 的 _ICON_SKIP 让开了 [data-icon-scope]（否则全局先换掉、作用域失效）",
          "[data-noicon], [data-icon-scope]" in idx)
    check(u"index.html 引用了 icon_scope.js", 'src="icon_scope.js"' in idx)
    gothic_html = read(GOTHIC) if os.path.isfile(GOTHIC) else ""
    check(u"gothic_frame.html 引用 icons.js 与 icon_scope.js",
          'src="icons.js"' in gothic_html and 'src="icon_scope.js"' in gothic_html)
    check(u"gothic_frame.html 标了 data-icon-scope=\"gothic\"",
          'data-icon-scope="gothic"' in gothic_html)
    check(u"五个 emoji 仍以文本硬编码在按钮里（换掉的是渲染，不是数据）",
          all(e in gothic_html for e in GOTHIC_KEYS))
    check(u"gothic_frame.html 自带 @font-face 与 .ms（独立页不继承主界面的样式）",
          "@font-face" in gothic_html and ".ms{" in gothic_html
          and "MaterialSymbolsOutlined.woff2" in gothic_html)

    print(u"\n== ⑥ 生成器 --check 通过（json 与产物一致）==")
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_icons.py"), "--check"],
                          cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    check(u"gen_icons --check 通过", proc.returncode == 0,
          out.strip().replace("\n", " | ")[:300])
    check(u"--check 把作用域也数进去（输出里有「作用域」）", u"作用域" in out,
          out.strip().replace("\n", " | ")[:200])

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ICON_SCOPES_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
