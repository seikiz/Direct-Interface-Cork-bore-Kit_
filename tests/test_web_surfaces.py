# -*- coding: utf-8 -*-
"""容器底色令牌化守卫：网页端"弹窗/浮层/工具条不跟主题走"这件事，变成一条会红的断言。

为什么需要
----------
安卓那边的同类 bug 根因是：主题只映射了 `surface`，而弹窗取的是 `surfaceContainerHigh`，
没映射 → 落回 Material3 默认的淡紫，于是"弹窗白得像硬编码"。网页端的等价病灶是
**容器底色不来自令牌**，只有两种长法：

  ① 硬编码 hex/rgba  —— `.modal{background:rgba(0,0,0,.55)}`、`#mechbar … {background:#f87171}`；
  ② 令牌 + 一个**只有暗色一份**的兜底 —— `background:var(--bubble,#161b22)`。

第 ② 种最阴：它看起来走了令牌，但 `#161b22` 是**暗色值的第二份手写副本**。一旦 `--bubble`
取不到值（拼错、生成物没加载、别名被删），整块表面就退回暗色 —— 浅色主题下"外白内黑"。
本轮把这 **24 处**兜底值全删了（`web/js/screens/*.js` 18 处 + `web/screens/*.html` 6 处；这不是
改观感：`web/theme.css` 里被引用的变量都有定义，兜底值是死代码；第 ④ 段有断言钉住"引用的变量
都定义着"），并把 **8 处"暗色副本"字面量**换成语义令牌（5 处容器底色 + 1 处裁剪框线 + 2 处
边框/选中框，第 ⑨ 段逐条证明暗色取值与原来逐字节相同）。

口径（很窄，故意的）
--------------------
只扫 **表面底色**，只认 `background` / `background-color` 两个属性：
  · `web/screens/*.html` —— 片段里的行内 style（`.modal-box`、`#trpgBar`、`#galEditor` …）；
  · `web/styles/**/*.css` —— 规则体里的声明（`.modal-box`、`.dd-overlay`、`.prow`、`.ach-toast` …）；
  · `web/js/screens/*.js` —— `cssText` 里拼出来的行内 style（codex 节点图 / gal 画布的行）。
不进来、也不该进来的：
  · `web/index.html` —— 外壳，已经没有一行 `<style>`（第 ⑪ 段钉住这一点），剩下的行内 style
    由 `tools/ui_snapshot.py` 逐字节守恒；它的容器表面写法与片段同源。
  · `background-image` / `box-shadow` / `border` —— 本测试只管底色。投影统一是黑色半透明
    （画面变深，两套主题都成立）；`border` 在报告里逐条盘过，但不当闸门。
  · 生成物（`theme.css` / `icons.js` / `i18n.js`）—— 它们本来就该全是令牌，扫它等于自己跟自己比。
  · SVG/画布里的 `fill=` / `stroke=`（围棋棋盘、节点图连线）—— 那是"这一屏自己画的画"，
    不是容器底色（`#241d15` 的木纹棋盘在浅色主题下也不该变白）。

判定规则
--------
一条底色声明**合规** ⇔ 它的值里没有颜色字面量（`#rgb/#rrggbb/rgb()/rgba()/hsl()/hsla()`）。
`var(--surface)`、`var(--bg)`、`color-mix(in srgb, var(--warn) 14%, var(--bubble))`、
`radial-gradient(circle, var(--line) 1px, transparent 1px)`、`transparent`、`none` 全合规。

不合规的必须落在下面两处之一，且**都只许缩短**：
  · **围栏**（源码内，带理由）—— `contrast-skip:<理由>` … `/contrast-skip`。
    复用 `tools/audit_contrast.py` 已有的那两个理由（`fixed-dark` / `badge`）：
    "这一片自带纯黑画布/同色相徽标，本来就不跟主题走"。HTML 用 `<!-- -->` 起止，
    JS 里用 `//` 写（`audit_contrast` 只认 HTML 注释，所以 JS 围栏不改它的文字对比度判定）。
  · **白名单**（本文件内，≤5 条，每条必须写 reason 与"为什么不能令牌化"）——
    装的是"改了就一定动暗色观感、而观感本轮不许动"的已知欠债。每条还钉了命中条数（n），
    少一条或多一条都红：这就是"只许缩短"的棘轮。

为什么反向验证不用临时目录
--------------------------
本机 `tempfile.gettempdir()` 会退化成**当前目录**（仓库根那堆 `tmp*` 就是历史上这么留下的），
所以抽取逻辑被写成纯函数 `decls_from_text(rel, kind, text)`：第 ⑩ 段把三条 `background:#fff`
喂给它，走的**就是**扫仓库的同一条代码路径，不落盘、不留垃圾。

跑法：utau_env\\Scripts\\python.exe -X utf8 tests\\test_web_surfaces.py
"""
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
THEME_CSS = os.path.join(ROOT, "web", "theme.css")
TOKENS_JSON = os.path.join(ROOT, "design", "tokens.json")

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


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  扫描范围（三层：屏片段 / 样式 / 屏脚本）
# ============================================================
SKIP_BASENAMES = {"theme.css", "icons.js", "i18n.js"}      # 生成物，与 audit_contrast 同口径
LAYERS = ("web/screens", "web/styles", "web/js/screens")


def scan_files(root):
    """返回 [(绝对路径, 相对路径, 类型)]；类型 ∈ html / css / js。"""
    out = []
    for layer in LAYERS:
        base = os.path.join(root, layer.replace("/", os.sep))
        if not os.path.isdir(base):
            continue
        if layer.endswith("styles"):
            names = []
            for d, _sub, fns in os.walk(base):
                for fn in sorted(fns):
                    names.append(os.path.join(d, fn))
        else:
            names = [os.path.join(base, fn) for fn in sorted(os.listdir(base))]
        for path in sorted(names):
            fn = os.path.basename(path)
            if fn in SKIP_BASENAMES:
                continue
            if fn.endswith(".html"):
                kind = "html"
            elif fn.endswith(".css"):
                kind = "css"
            elif fn.endswith(".js"):
                kind = "js"
            else:
                continue
            out.append((path, os.path.relpath(path, root).replace(os.sep, "/"), kind))
    return out


# ============================================================
#  颜色字面量判定
# ============================================================
RE_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(", re.I)
# 前缀类里必须有 `"` 和 `'`：行内 style 的第一条声明长这样 —— style="background:#fff"
# （2026-11 反向验证抓到的漏扫：`class="…" style="background:#fff"` 前面是引号，
#  只写 [;{\s] 的话它整条都扫不到，闸门就成了摆设）。
RE_BG = re.compile(r"(?:^|[;{\"'\s])(background(?:-color)?)\s*:\s*([^;}\"']*)", re.I)
RE_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
RE_VAR = re.compile(r"var\(\s*--([\w-]+)\s*(?:,([^)]*))?\)")


def is_token_only(value):
    """值里没有颜色字面量 → 全是令牌/关键字/渐变。空值算不合规。"""
    v = (value or "").strip()
    if not v:
        return False
    return RE_LITERAL.search(v) is None


def var_names(value):
    """一条值里引用的所有 CSS 变量名（去掉 -- 前缀）。"""
    return [m.group(1) for m in RE_VAR.finditer(value or "")]


# ============================================================
#  围栏：contrast-skip:<理由> … /contrast-skip
# ============================================================
RE_FENCE_BEGIN = re.compile(r"contrast-skip:(fixed-dark|badge)\b")
FENCE_END = "/contrast-skip"
FENCE_REASONS = ("fixed-dark", "badge")


def fences_of(text):
    """逐行扫围栏 → ({行号: 理由|None}, [(起, 止, 理由)], [配对错误])。"""
    per_line = {}
    regions = []
    problems = []
    cur = None
    start = 0
    for i, ln in enumerate(text.split("\n"), 1):
        m = RE_FENCE_BEGIN.search(ln)
        if FENCE_END in ln and cur is None:
            problems.append(u"第 %d 行：只有结束没有开始" % i)
            per_line[i] = None
            continue
        if m and cur is None:
            cur, start = m.group(1), i
            per_line[i] = cur
            continue
        if m and cur is not None:
            problems.append(u"第 %d 行：上一个围栏（第 %d 行起）还没关就起了新的" % (i, start))
            per_line[i] = cur
            continue
        if FENCE_END in ln:
            regions.append((start, i, cur))
            per_line[i] = cur
            cur = None
            continue
        per_line[i] = cur
    if cur is not None:
        problems.append(u"第 %d 行的围栏起了没关" % start)
    return per_line, regions, problems


# ============================================================
#  声明抽取（纯函数：不碰磁盘，反向验证复用它）
# ============================================================
def strip_css_comments(text):
    """注释换成等长空白（保留换行 → 行号不漂）。"""
    def blank(m):
        return "".join("\n" if c == "\n" else " " for c in m.group(0))
    return re.sub(r"/\*.*?\*/", blank, text, flags=re.S)


def strip_js_line_comments(text):
    """只剥行注释，且不碰 `://`（那可能在字符串里）。"""
    def blank(m):
        return " " * len(m.group(0))
    return re.sub(r"(?<![:\\])//[^\n]*", blank, text)


def strip_html_comments(text):
    def blank(m):
        return "".join("\n" if c == "\n" else " " for c in m.group(0))
    return re.sub(r"<!--.*?-->", blank, text, flags=re.S)


def ident_of_html(line):
    m = re.search(r'id="([^"]+)"', line)
    if m:
        return u"#" + m.group(1)
    m = re.search(r'class="([^"]+)"', line)
    if m:
        return u"." + m.group(1).split()[0]
    return u"<inline>"


def decls_from_text(rel, kind, raw):
    """从一个文件的内容里抽出全部底色声明：dict(rel, kind, line, ident, prop, value, fence)。"""
    out = []
    if kind == "css":
        txt = strip_css_comments(raw)
        for m in RE_RULE.finditer(txt):
            sel = u" ".join(m.group(1).split())
            line = txt.count("\n", 0, m.start()) + 1
            for d in RE_BG.finditer(m.group(2)):
                out.append(dict(rel=rel, kind=kind, line=line, ident=sel[:120],
                                prop=d.group(1), value=d.group(2).strip(), fence=None))
        return out
    # html / js：一行一条（行内 style 与 cssText 都是这个形状）
    txt = strip_html_comments(raw) if kind == "html" else strip_js_line_comments(raw)
    fence_lines, _regions, _probs = fences_of(raw)
    for i, line in enumerate(txt.split("\n"), 1):
        for d in RE_BG.finditer(u";" + line):
            out.append(dict(rel=rel, kind=kind, line=i,
                            ident=("<js>" if kind == "js" else ident_of_html(line)),
                            prop=d.group(1), value=d.group(2).strip(),
                            fence=fence_lines.get(i)))
    return out


def scan_decls(root):
    out = []
    for path, rel, kind in scan_files(root):
        out.extend(decls_from_text(rel, kind, read(path)))
    return out


# ============================================================
#  白名单（≤5 条；每条带 reason / why / 命中条数 n；只许缩短）
# ============================================================
MAX_WHITELIST = 5
WHITELIST = [
    dict(rel="web/styles/components.css", idents=(".modal",), n=1, reason="scrim",
         why=u"模态背后的幕布（55% 纯黑）：它盖的是任意内容，两套主题都必须压暗。"
             u"令牌表里现成的是 --scrim（#0a0c10cc＝80% 石板）与 --scrim-soft（60% 纯黑），"
             u"取值都与 .55 差一档，换上去会改暗色观感（本轮不许），故登记欠债。"),
    dict(rel="web/styles/panels.css", idents=(".onb-mask",), n=1, reason="scrim",
         why=u"首启引导的强遮罩（rgba(8,10,14,.72)）：同上，属于幕布不属于表面。"
             u"统一到 --scrim 会从 72% 变 80% 且带蓝调，改暗色观感。"),
    dict(rel="web/screens/codex.html", idents=("<inline>", "#codexTplPreview"), n=2,
         reason="canvas",
         why=u"代码试玩预览的纯黑底（外壳 div + 它的 iframe 各一条）：壳里预览的是 GALGAME"
             u" 播放器模板，必须一直是黑的。canvas 纯黑底：待补 design/tokens.json 的 canvas"
             u" 恒定角色（建议 #000000，暗/浅同值），补完后白名单应缩到 4 条。"),
    dict(rel="web/screens/codex.html", idents=("#codexPackInfo",), n=1, reason="tint",
         why=u"打包成功提示的浅绿底（rgba(46,160,67,.1)）：同色相「浅染」，文字是 --sub。"
             u"令牌里没有这个色相的角色，改成 --ok 会从灰绿变荧光绿（改暗色观感）；"
             u"造一个 tint 角色等于新增设计取值，超出本轮授权。"),
    dict(rel="web/screens/trpg.html", idents=("#trpgBar",), n=1, reason="tint",
         why=u"跑团状态条的深蓝染底（rgba(8,47,73,.45)）：同样是「浅染」，文字是 --text。"
             u"这是全站唯一一处**浅色主题下观感确实不够**的表面（深蓝条贴在浅底上），"
             u"但要修就得新造一个浅色取值（设计决定），本轮只登记、不动。"),
]
MAX_EXEMPT_DECLS = 6                     # 白名单总命中条数（只许缩短）
MAX_FENCE_REGIONS = 4                    # 围栏总片数（现 4：codex 播放器 / gal 徽标 / 2 个播放器脚本）


def whitelist_lookup(rel, ident):
    for idx, entry in enumerate(WHITELIST):
        if entry["rel"] == rel and ident in entry["idents"]:
            return idx
    return None


# ============================================================
#  令牌侧：每个表面角色暗/浅都要有值（缺一个就红）
# ============================================================
# 合法颜色值：#rrggbb、#rrggbbaa（带 alpha 的八角 hex，恒定角色 scrim/scrim_soft 就是这个写法）、rgb(a)()
RE_COLOR = re.compile(r"^(#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?"
                      r"|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}"
                      r"\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\))$")
# 网页 CSS 真在用、删了就会崩的角色（新增的恒定角色不列，避免与令牌表演进耦合）
REQUIRED_ROLES = ("bg", "surface", "surface_2", "border", "border_strong",
                  "text", "text_sub", "text_dim", "accent", "danger", "warn", "ok")
# 会写颜色角色的 5 个块（别名块只写 --panel/--bubble/--line… 这些指位，不算角色块）
THEME_BLOCKS = ("root", "media-light", "body.dark", "body.light", "body.oled")


def missing_roles(data, roles=None):
    """返回"暗/浅缺值或值不合法"的角色列表；判定器自检也用它（喂坏数据必须报出来）。"""
    colors = data.get("colors") or {}
    dark = colors.get("dark") or {}
    light = colors.get("light") or {}
    names = roles if roles is not None else sorted(set(dark) | set(light))
    return [r for r in names if not (isinstance(dark.get(r), str) and RE_COLOR.match(dark[r])
                                     and isinstance(light.get(r), str) and RE_COLOR.match(light[r]))]


def theme_blocks(text):
    """把 theme.css 切成 {块名: {变量名: 值}}。锚 ^ 很关键：别名规则那行是
    `:root, body, body.dark, body.light, body.oled{…}`，不加锚会把四个块全认成它。

    别名块（--panel/--bubble/--line/--sub/--user）单独收成 "aliases"：它们也是
    `background:var(--bubble)` 这类写法的真正出处，算"有定义"时不能漏。"""
    out = {}

    def grab(sel_pat, block_name):
        for m in re.finditer(sel_pat, text, re.M):
            out[block_name] = dict(re.findall(r"--([\w-]+)\s*:\s*([^;}\n]+);", m.group(1)))

    grab(r"^:root\s*\{([^{}]*)\}", "root")
    grab(r"@media\s*\(prefers-color-scheme:\s*light\)\s*\{\s*:root\s*\{([^{}]*)\}",
         "media-light")
    for name in ("dark", "light", "oled"):
        grab(r"^body\.%s\s*\{([^{}]*)\}" % name, "body." + name)
    grab(r"^:root\s*,\s*body[^{]*\{([^{}]*)\}", "aliases")
    return out


# ============================================================
#  main
# ============================================================
def main():
    print("=" * 66)
    print(u"容器底色令牌化守卫（表面底色只许来自令牌；两套主题都要有值）")
    print("=" * 66)

    files = scan_files(ROOT)
    decls = scan_decls(ROOT)
    rels = [r for _p, r, _k in files]

    # ------------------------------------------------------------------
    # ① 扫描范围先兜住（防"扫描被改空 → 全绿变假绿"）
    # ------------------------------------------------------------------
    print(u"\n== ① 扫描范围先兜住 ==")
    check(u"扫到 ≥40 个文件（现在 %d 个）" % len(files), len(files) >= 40, u"%s" % rels[:5])
    check(u"取到 ≥110 条底色声明（现在 %d 条）" % len(decls), len(decls) >= 110)
    check(u"覆盖 web/screens/*.html", any(r.startswith("web/screens/") for r in rels))
    check(u"覆盖 web/styles/**/*.css", any(r.startswith("web/styles/") for r in rels))
    check(u"覆盖 web/js/screens/*.js", any(r.startswith("web/js/screens/") for r in rels))
    check(u"生成物没被算进来（theme.css / icons.js / i18n.js）",
          not any(os.path.basename(r) in SKIP_BASENAMES for r in rels))
    check(u"三层都有声明（css / html / js）", len({d["kind"] for d in decls}) == 3,
          u"%s" % sorted({d["kind"] for d in decls}))

    # ------------------------------------------------------------------
    # ② 判定器自检：该红的必须红，该放的必须放
    # ------------------------------------------------------------------
    print(u"\n== ② 判定器自检（判定函数不许被改成永远 PASS）==")
    samples = [
        (u"var(--surface)", True, u"纯令牌"),
        (u"var(--bg)", True, u"纯令牌"),
        (u"transparent", True, u"关键字"),
        (u"color-mix(in srgb, var(--warn) 14%, var(--bubble))", True, u"令牌混色"),
        (u"radial-gradient(circle, var(--line) 1px, transparent 1px)", True, u"令牌画点阵"),
        (u"#fff", False, u"三字缩写 hex"),
        (u"#ffffff", False, u"六位 hex"),
        (u"rgba(0,0,0,.55)", False, u"遮罩 rgba"),
        (u"var(--bubble,#161b22)", False, u"令牌 + 暗色兜底（第 ② 类病灶）"),
        (u"linear-gradient(transparent,rgba(0,0,0,.92) 35%)", False, u"渐变里带 rgba"),
        (u"", False, u"空值不算合规"),
    ]
    for value, should_pass, why in samples:
        got = is_token_only(value)
        check(u"自检：%s → %s" % (why, u"合规" if should_pass else u"判红"), got == should_pass,
              u"「%s」" % value)

    # ------------------------------------------------------------------
    # ③ 全量：表面底色只许来自令牌
    # ------------------------------------------------------------------
    bad, whitelisted, fenced = [], [], []
    for d in decls:
        if is_token_only(d["value"]):
            continue
        if d["fence"]:
            fenced.append(d)
            continue
        idx = whitelist_lookup(d["rel"], d["ident"])
        if idx is not None:
            d["wl"] = idx
            whitelisted.append(d)
            continue
        bad.append(d)

    print(u"\n== ③ 表面底色只许出现 var(--…) ==")
    check(u"不合规（既没令牌、也没围栏/白名单）0 处", not bad,
          u"；".join(u"%s:%d [%s] %s = %s" % (x["rel"], x["line"], x["ident"], x["prop"], x["value"])
                    for x in bad[:8]))
    check(u"合规声明占绝大多数（≥85%）",
          sum(1 for d in decls if is_token_only(d["value"])) >= len(decls) * 0.85,
          u"%d/%d" % (sum(1 for d in decls if is_token_only(d["value"])), len(decls)))

    # ------------------------------------------------------------------
    # ④ 第 ② 类病灶（令牌 + 只有暗色一份的兜底）必须清零
    # ------------------------------------------------------------------
    print(u"\n== ④ 令牌兜底里不许再夹暗色 hex ==")
    with_fb = [x for x in decls if any(m.group(2) for m in RE_VAR.finditer(x["value"]))]
    check(u"background 的 var() 兜底值 0 处（现在 %d 处）" % len(with_fb), not with_fb,
          u"；".join(u"%s:%d %s" % (x["rel"], x["line"], x["value"]) for x in with_fb[:6]))

    # 删兜底之所以零观感变化：它引用的变量全都在 theme.css 里定义着
    blocks = theme_blocks(read(THEME_CSS))
    defined = set(blocks.get("root") or {}) | set(blocks.get("aliases") or {})
    used = set()
    for d in decls:
        used.update(var_names(d["value"]))
    undefined = sorted(n for n in used if n not in defined)
    check(u"background 引用的变量都在 :root 里有定义（删兜底不改渲染）", not undefined,
          u"未定义：%s" % undefined)
    check(u"被引用过的变量数 ≥10（现在 %d 个）" % len(used), len(used) >= 10, u"%s" % sorted(used))

    # ------------------------------------------------------------------
    # ⑤ 围栏：成对、理由合法、片数 ≤4
    # ------------------------------------------------------------------
    print(u"\n== ⑤ 自绘底色围栏（自带纯黑画布 / 同色相徽标）==")
    all_regions, fence_problems = [], []
    for path, rel, _kind in scan_files(ROOT):
        _per, regions, probs = fences_of(read(path))
        all_regions.extend([(rel, a, b, why) for a, b, why in regions])
        fence_problems.extend([u"%s %s" % (rel, p) for p in probs])
    check(u"围栏成对（起止各一行、不嵌套）", not fence_problems, u"；".join(fence_problems[:4]))
    check(u"围栏片数 ≤%d（现在 %d 片）" % (MAX_FENCE_REGIONS, len(all_regions)),
          len(all_regions) <= MAX_FENCE_REGIONS,
          u"、".join(u"%s:%d-%d(%s)" % tuple(r) for r in all_regions))
    check(u"围栏理由只有 fixed-dark / badge",
          all(r[3] in FENCE_REASONS for r in all_regions),
          u"、".join(sorted({r[3] for r in all_regions})))
    check(u"围栏里的底色声明 ≥1 条（围栏不是空摆设）", len(fenced) >= 1, u"%d 条" % len(fenced))
    for rel, a, b, why in all_regions:
        print(u"       · %s:%d-%d  %s" % (rel, a, b, why))

    # ------------------------------------------------------------------
    # ⑥ 白名单：≤5 条、每条有 reason/why、命中条数钉死（只许缩短）
    # ------------------------------------------------------------------
    print(u"\n== ⑥ 白名单（已知欠债；≤5 条，只许缩短）==")
    check(u"白名单 ≤%d 条（现在 %d 条）" % (MAX_WHITELIST, len(WHITELIST)),
          len(WHITELIST) <= MAX_WHITELIST)
    check(u"每条都写了 reason 与 why",
          all(e.get("reason") and str(e.get("why", "")).strip() for e in WHITELIST))
    check(u"reason 只有 scrim / canvas / tint",
          all(e["reason"] in ("scrim", "canvas", "tint") for e in WHITELIST),
          u"、".join(sorted({e["reason"] for e in WHITELIST})))
    total_wl = 0
    for idx, e in enumerate(WHITELIST):
        hit = [x for x in whitelisted if x.get("wl") == idx]
        total_wl += len(hit)
        check(u"%s %s 命中 %d 条（钉死，多/少都红）" % (e["rel"], u"|".join(e["idents"]), e["n"]),
              len(hit) == e["n"], u"实际 %d 条" % len(hit))
    check(u"白名单总命中 ≤%d 条（现在 %d 条）" % (MAX_EXEMPT_DECLS, total_wl),
          total_wl <= MAX_EXEMPT_DECLS)
    for e in WHITELIST:
        print(u"       · [%s] %s %s —— %s…" % (e["reason"], e["rel"], u"|".join(e["idents"]),
                                               e["why"][:56]))

    # ------------------------------------------------------------------
    # ⑦ 令牌：每个表面角色暗/浅都有值（缺一个就红）
    # ------------------------------------------------------------------
    print(u"\n== ⑦ design/tokens.json 每个表面角色暗/浅都要有值 ==")
    data = json.loads(read(TOKENS_JSON))
    colors = data.get("colors") or {}
    dark = colors.get("dark") or {}
    light = colors.get("light") or {}
    check(u"暗/浅两套键名完全一致", sorted(dark) == sorted(light),
          u"暗多：%s ／ 浅多：%s" % (sorted(set(dark) - set(light)),
                                  sorted(set(light) - set(dark))))
    miss = missing_roles(data)
    check(u"所有角色两套都有合法颜色值（缺一个就红）", not miss, u"缺：%s" % miss)
    check(u"网页真在用的表层角色一个都不缺",
          all(r in dark and r in light for r in REQUIRED_ROLES),
          u"缺：%s" % [r for r in REQUIRED_ROLES if r not in dark or r not in light])
    check(u"自检：挖掉浅色 surface → 必须判红",
          missing_roles({"colors": {"dark": dict(dark),
                                    "light": {k: v for k, v in light.items() if k != "surface"}}},
                        ["surface"]) == ["surface"])
    check(u"自检：浅色写成非法值 → 必须判红",
          missing_roles({"colors": {"dark": {"surface": "#14161c"},
                                    "light": {"surface": u"白"}}}, ["surface"]) == ["surface"])

    # ------------------------------------------------------------------
    # ⑧ theme.css 四块都写了每个角色（"只有暗色一份"在产物层也要断死）
    # ------------------------------------------------------------------
    print(u"\n== ⑧ web/theme.css 的每套主题都写了每个角色 ==")
    check(u"切出 5 个主题块（%s）" % u"、".join(THEME_BLOCKS),
          all(b in blocks for b in THEME_BLOCKS), u"实得：%s" % sorted(blocks))
    role_vars = [r.replace("_", "-") for r in sorted(dark)]
    for block in THEME_BLOCKS:
        got = blocks.get(block) or {}
        lac = [r for r in role_vars if r not in got]
        check(u"%s 里 %d 个角色全都有值" % (block, len(role_vars)), not lac, u"缺：%s" % lac)
    check(u"浅色块的取值与暗色块不同（真的换了一套，不是复制粘贴）",
          any((blocks.get("body.dark") or {}).get(v) != (blocks.get("body.light") or {}).get(v)
              for v in ("bg", "surface", "text", "accent")),
          u"检查了 bg/surface/text/accent")

    # ------------------------------------------------------------------
    # ⑨ 暗色零变化：本轮替换掉的每个字面量，令牌的暗色值必须与它一模一样
    # ------------------------------------------------------------------
    print(u"\n== ⑨ 暗色观感零变化（换令牌前 == 换令牌后：逐字节比色值）==")
    pinned = [
        (u"#f87171", "danger", u"#mechbar .mb-bar.fight i 的进度条红 / gal 体检结果左边线"),
        (u"#60a5fa", "accent", u"#mechbar .mb-bar.mp i / .we-dot.const 的蓝"),
        (u"#4ade80", "ok", u".wentry .we-dot.on 的绿"),
        (u"#f59e0b", "warn", u"GAL 场景行选中框 outline"),
        (u"#111111", "stage", u"#cropStage 的裁剪台（原写 #111）"),
        (u"#ffffff", "stage_line", u"裁剪框线（原写 #fff）"),
    ]
    for old_hex, role, why in pinned:
        got = (dark.get(role) or u"").lower()
        check(u"%s: %s 暗色 == %s（%s）" % (role, got or u"缺", old_hex, why),
              got == old_hex.lower(), u"令牌暗色 %s ≠ 原字面量 %s" % (got, old_hex))
    dark_pin = {"bg": "#0f1115", "surface": "#14161c", "surface_2": "#1a1e26",
                "border": "#5c6478", "border_strong": "#7b8598", "text": "#e5e7eb",
                "text_sub": "#94a3b8", "text_dim": "#7c8598"}
    drift = {k: (dark.get(k), v) for k, v in dark_pin.items() if (dark.get(k) or u"").lower() != v}
    check(u"8 个核心表层角色的暗色值未变", not drift, u"%s" % drift)
    # 这次改的 4 处 CSS 真的不再是字面量（注释里提到旧值不算，先剥注释）
    css_all = strip_css_comments(
        read(os.path.join(ROOT, "web", "styles", "screens.css")) +
        read(os.path.join(ROOT, "web", "styles", "screens", "wm.css")))
    for lit, role in ((u"#f87171", "danger"), (u"#60a5fa", "accent"), (u"#4ade80", "ok")):
        check(u"styles/** 里不再出现字面量 %s（已换成 var(--%s)）" % (lit, role),
              lit not in css_all, u"仍有 %s" % lit)

    # ------------------------------------------------------------------
    # ⑩ 反向验证：真往扫描范围里塞一条 background:#fff → 必须红
    # ------------------------------------------------------------------
    print(u"\n== ⑩ 反向验证（塞一条 background:#fff，必须判红） ==")
    plant = [
        ("web/screens/__plant__.html", "html",
         u'<div class="modal-box" style="background:#fff">x</div>\n'),
        ("web/styles/__plant__.css", "css", u'.modal-box{ background:#fff; }\n'),
        ("web/js/screens/__plant__.js", "js",
         u"var b = document.createElement('button');\n"
         u"b.style.cssText = 'padding:2px;background:#fff;border:1px solid #000';\n"),
    ]
    planted = []
    for rel, kind, body in plant:
        planted.extend(decls_from_text(rel, kind, body))
    planted_bad = [x for x in planted if not is_token_only(x["value"])]
    check(u"三层各塞一条 → 抽到 3 条底色声明", len(planted) == 3,
          u"实得 %d 条：%s" % (len(planted), [x["value"] for x in planted]))
    check(u"这 3 条全部判红（#fff 混不过去）", len(planted_bad) == 3,
          u"实得 %d 条判红" % len(planted_bad))
    check(u"报出来的值就是 #fff", sorted({x["value"] for x in planted_bad}) == ["#fff"],
          u"%s" % sorted({x["value"] for x in planted_bad}))
    check(u"红的是值不是文件：换成 var(--surface) 后 0 条判红",
          not [x for x in decls_from_text("web/screens/__plant__.html", "html",
                                          u'<div class="modal-box" style="background:var(--surface)">x</div>\n')
               if not is_token_only(x["value"])])
    # 塞进去的那条过不了闸门 —— 也就是说：仓库里"0 处"是真的 0 处，不是扫描漏了地方
    check(u"塞进白名单/围栏也骗不过闸门（它俩都不认 __plant__）",
          whitelist_lookup("web/screens/__plant__.html", ".modal-box") is None)
    print(u"       实证：在真实仓库里临时塞一条 → 见报告「反向验证」一节的原始输出")

    # ------------------------------------------------------------------
    # ⑪ 外壳边界：index.html 已经没有 <style>（容器样式全在 styles/**，被本测试覆盖）
    # ------------------------------------------------------------------
    print(u"\n== ⑪ 外壳边界（这条说明 index.html 为什么不在扫描范围里）==")
    shell = read(os.path.join(ROOT, "web", "index.html"))
    check(u"web/index.html 里没有 <style> 块", "<style" not in shell.lower())
    hrefs = re.findall(r'<link[^>]+href="([^"]+)"', shell)
    check(u"web/index.html 的 <link> 全指向 styles/** 或 theme.css",
          bool(hrefs) and all(("styles/" in h or h.endswith("theme.css")) for h in hrefs),
          u"%s" % hrefs)

    print("\n" + "=" * 66)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("WEB_SURFACES_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
