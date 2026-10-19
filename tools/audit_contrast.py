# -*- coding: utf-8 -*-
"""audit_contrast.py —— 配色量化审计（本阶段的验收工具）。

两件事：
  1) **对比度矩阵**：读 `design/tokens.json`，对必需组合算 WCAG 2.1 对比度并判定。
     正文类 <4.5 判 FAIL；图标/大字/控件边界 <3.0 判 FAIL；装饰性（text_dim）只 WARN。
  2) **漂移扫描**：扫 `web/*.html`／`web/*.css`／`DICK-Android/.../app/*.kt` 里的硬编码颜色
     （`#rrggbb`、`rgba(`、`Color(0xFF…)`），列出"不在令牌文件里"的出现位置（文件:行号 + 颜色）。
     本轮不要求清零 —— 它是后续逐屏收敛的清单；但数量与位置要能看得到，不然"收敛"永远停在口头。

判定口径（Why 4.5 / 3.0）
------------------------
WCAG 2.1：正文（<18.66px 且非粗体）要 4.5:1；大字（≥18.66px 或 ≥14pt 粗体）与非文本的
控件/图形边界要 3:1。所以令牌里 `text_sub` 这种"次要但仍是正文"的角色按 4.5 卡，
`border` 按 3.0 卡，`text_dim` 明确定位成装饰性，只 WARN —— 但**不允许**拿它排正文。

用法：
    python tools/audit_contrast.py            # 矩阵 + 漂移清单
    python tools/audit_contrast.py --quiet    # 只打印结论与漂移数量
    python tools/audit_contrast.py --top 20   # 漂移清单显示前 N 条（默认 15）
退出码：必需组合缺失、或任一判定为 FAIL → 1；否则 0（WARN 不影响退出码）。
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "design", "tokens.json")

# 硬编码颜色扫描范围（相对仓库根<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌）：(目录, 后缀, 是否递归)
SCAN_GLOBS = [
    ("web", ".html", False),
    # .css 要递归：2026-11 阶段1 把 index.html 的 <style> 拆到了 web/styles/*.css，
    # 不递归的话那 400 多处硬编码颜色就从扫描范围里消失了（等于自己给自己放水）。
    ("web", ".css", True),
    (os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick"), ".kt", True),
]
# 生成物：它们本来就该满是令牌色，扫它们等于自己跟自己比
SKIP_BASENAMES = {"theme.css", "Tokens.kt", "IconNames.kt", "icons.js", "i18n.js"}

# ---------------------------------------------------------------- 自绘底色区域
# 有些界面的底色不是"主题底色"，而是**这一屏自己画的**：全屏 GALGAME 播放器压在纯黑幕 +
# 作者给的立绘上，状态徽标压在它自己的同色相浅底上。拿"主题最有利底"去套它们，得到的
# 数字（#eee vs 浅色 --surface = 1.16）并不代表玩家看到的对比度。
#
# 所以给它们一个**显式声明**：片段里起止各一行注释围栏，工具只认下面两个理由 ——
#   fixed-dark  自带纯黑画布：浅色主题那一遍跳过（暗色下仍然必须 ≥4.5，照查）
#   badge       瞬时状态徽标（文字与底色同色相）：不算正文，整条豁免
# 这是"记录已知欠债"，不是免检：条数上限（≤2 片）与理由白名单由 tests/test_no_dim_text.py 钉住，
# 区域内的文字色仍然要过用例 ⑥ 的暗色对比度。想加第三片，先改测试、再说明为什么值得。
SKIP_BEGIN = re.compile(r"<!--\s*contrast-skip:(fixed-dark|badge)\s*-->")
SKIP_END = "<!-- /contrast-skip -->"
SKIP_REASONS = ("fixed-dark", "badge")

HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")


# ============================================================
#  WCAG 2.1 相对亮度与对比度
# ============================================================
def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_rgb(h):
    h = h.strip().lstrip(u"#")
    if len(h) == 3:
        h = u"".join(ch * 2 for ch in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(h):
    r, g, b = hex_to_rgb(h)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg, bg):
    """WCAG 对比度（1..21）。两边顺序无关。"""
    a, b = luminance(fg), luminance(bg)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


# ============================================================
#  矩阵
# ============================================================
KIND_LABEL = {"body": u"正文", "ui": u"图标/边界", "decor": u"仅装饰"}


def print_matrix(pal, theme_name, data):
    """打印一套配色的对比度矩阵。返回 (fail, warn, missing) 三份清单。"""
    conf = data.get("contrast") or {}
    pairs = conf.get("pairs") or []
    mins = conf.get("min") or {}
    fail, warn, missing, rows = [], [], [], []
    for p in pairs:
        fg, bg = p.get("fg"), p.get("bg")
        kind = p.get("kind", "body")
        need = float(mins.get(kind, 4.5))
        if pal.get(fg) is None or pal.get(bg) is None:
            missing.append(u"%s/%s" % (fg, bg))
            rows.append((u"%s/%s" % (fg, bg), u"-", u"-", None, need, kind, u"MISSING"))
            continue
        r = contrast(pal[fg], pal[bg])
        required = bool(p.get("required", True))
        if not required:
            # 参考组合：只打印比值，不参与判定（例如 text 压在 accent 上 —— 本项目不允许这么用，
            # 压 accent 的文字一律走 accent_text）
            verdict = u"参考"
        elif kind == "decor":
            verdict = u"OK" if r >= need else u"WARN"
            if verdict == u"WARN":
                warn.append((u"%s/%s" % (fg, bg), r, need))
        else:
            verdict = u"OK" if r >= need else u"FAIL"
            if verdict == u"FAIL":
                fail.append((u"%s/%s" % (fg, bg), r, need))
        rows.append((u"%s/%s" % (fg, bg), pal[fg], pal[bg], r, need, kind, verdict))
    print(u"  %-22s %-9s %-9s %6s %6s %s" % (u"组合", u"前景", u"背景", u"比值", u"要求", u"判定"))
    for name, fg, bg, r, need, kind, verdict in rows:
        ratio = u"-" if r is None else u"%.2f" % r
        print(u"  %-22s %-9s %-9s %6s %6s %s %s" % (
            name, fg or u"-", bg or u"-", ratio, u"≥%g" % need,
            u"·" + KIND_LABEL.get(kind, kind), verdict))
    return fail, warn, missing


def load_tokens():
    with io.open(SRC, encoding="utf-8") as f:
        return json.load(f)


def min_text_ratio(data):
    """当前仓库里"文字色 / 其背景"的最低比值（给报告用：最差对比度提到多少）。"""
    worst = None
    n = 0
    for p in text_pairs(data):
        if p["ratio"] is None:
            continue
        n += 1
        if worst is None or p["ratio"] < worst[0]:
            worst = (p["ratio"], p["rel"], p["line"], p["theme"], p["value"])
    return worst, n


# ============================================================
#  漂移扫描
# ============================================================
RE_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RE_RGBA = re.compile(r"rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+")
RE_COMPOSE = re.compile(r"Color\(\s*0x([0-9a-fA-F]{6,8})\s*\)")


def _norm_hex(h):
    h = h.lstrip(u"#").lower()
    if len(h) == 3:
        h = u"".join(ch * 2 for ch in h)
    if len(h) == 8:          # #rrggbbaa → 丢掉 alpha（漂移清单只关心色相/明度）
        h = h[:6]
    return u"#" + h


def token_color_set(data):
    """令牌文件里出现过的全部颜色（暗/浅/OLED + 强调色的暗/浅版）。"""
    out = set()
    for pal in (data.get("colors") or {}).values():
        if isinstance(pal, dict):
            for v in pal.values():
                if isinstance(v, str) and HEX6.match(v):
                    out.add(_norm_hex(v))
    for acc in data.get("accents") or []:
        for k in ("dark", "light"):
            if isinstance(acc.get(k), str):
                out.add(_norm_hex(acc[k]))
    for v in (data.get("oled") or {}).values():
        if isinstance(v, str) and HEX6.match(v):
            out.add(_norm_hex(v))
    return out


def scan_files():
    out = []
    for sub, ext, recursive in SCAN_GLOBS:
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        if recursive:
            names = []
            for base, _dirs, files in os.walk(d):
                for fn in files:
                    names.append(os.path.join(base, fn))
        else:
            names = [os.path.join(d, fn) for fn in os.listdir(d)]
        for path in sorted(names):
            fn = os.path.basename(path)
            if not fn.endswith(ext) or fn in SKIP_BASENAMES:
                continue
            out.append(path)
    return out


def scan_drift(data):
    """返回 (total, 不在令牌里的命中列表[(相对路径, 行号, 颜色)])。"""
    known = token_color_set(data)
    total = 0
    hits = []
    for path in scan_files():
        rel = os.path.relpath(path, ROOT).replace(os.sep, u"/")
        try:
            with io.open(path, encoding="utf-8") as f:
                lines = f.read().split(u"\n")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines, 1):
            found = []
            for m in RE_HEX.finditer(line):
                found.append(_norm_hex(m.group(0)))
            for m in RE_RGBA.finditer(line):
                found.append(m.group(0).replace(u" ", u""))
            for m in RE_COMPOSE.finditer(line):
                found.append(_norm_hex(u"#" + m.group(1)))
            if not found:
                continue
            total += len(found)
            for col in found:
                if col not in known:
                    hits.append((rel, i, col))
    return total, hits


# ============================================================
#  ③ 文字色 vs 其背景（2026-11 去浅色字新增）
# ============================================================
# 为什么要有这一段
# ----------------
# 前两段查的是"令牌本身达不达标"和"哪些颜色没走令牌"。它们都看不见真正的病灶：
# 一屏里 `color:#8a93a3` 压在 `--panel` 上、`color:#fff` 压在 `--accent` 上 ——
# 令牌表全绿，用户还是说"颜色看起来费劲"。这一段直接拿**声明出来的文字色**与
# **它自己的背景**算比值，要求正文类一律 ≥4.5（WCAG 2.1 AA，本项目不给自己放水）。
#
# 判定口径（刻意保守，宁少误报也不放过真问题）：
#   1) 同一条规则/同一行内 style 里既有文字色又有背景 → 就按这一对判（最准）。
#   2) 只有文字色、背景无从得知 → 分别对 bg / surface / surface_2 三块底色算，
#      **取最有利的那个**：三块全不达标才算 FAIL。理由是"这块文字到底压在谁身上"
#      静态看不出来，取最有利值只会漏报、不会误报；而"三块全不行"一定是真的看不清。
#   3) 白名单（真正的功能态，不是正文）：`:disabled`/`disabled`（禁用态）、
#      `::placeholder`（占位符，WCAG 不把它算正文，但也要求 ≥3:1 → 单独按 3.0 判）、
#      以及非文字属性（border/box-shadow/outline/text-shadow 根本不在文字属性表里）。
#   4) 颜色取自 `design/tokens.json`（暗/浅两套），网页端 `var(--x)` 与安卓端
#      `theme.x` 都能解析；解析不出来的（`color-mix()`、渐变）跳过并计数，不猜。

TEXT_PROPS = ("color", "-webkit-text-fill-color")
# 网页上允许直接判定的"已知暗底次要灰"：这些值在暗底上次要文字勉强能看、在浅底上直接糊掉。
DIM_HEX = {
    "#555", "#666", "#777", "#888", "#999", "#aaa", "#bbb",
    "#8a93a3", "#7aa2b8", "#9aa1ab", "#7b828b", "#6b7078", "#a7adb6", "#8f93b0", "#9aa9aa",
}
DIM_ALPHA = 0.6            # 文字色 alpha 低于它就算"浅色字"（用户口径）
DIM_ALPHA_KT = 0.6         # 安卓口径按 "copy(alpha = 0.[0-6])" 抓，含 0.6 本身（≤0.6 都算）
PLACEHOLDER_MIN = 3.0      # 占位符放宽到 3:1，但不能再低
TEXT_MIN = 4.5             # 正文类硬门槛

_RE_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RE_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_RE_TEXT = re.compile(r"(?:^|[;{\s])(color|-webkit-text-fill-color)\s*:\s*([^;}\"']*)", re.I)
_RE_BG = re.compile(r"(?:^|[;{\s])(background(?:-color)?)\s*:\s*([^;}\"']*)", re.I)
_RE_RGBA = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)")
_RE_VAR = re.compile(r"var\(\s*--([\w-]+)\s*(?:,([^)]*))?\)")
_RE_MIX = re.compile(r"color-mix\(\s*in\s+srgb\s*,\s*([^,]+?)\s+([\d.]+)%\s*,\s*([^)]+?)\s*\)")
ALIAS = {"panel": "surface", "bubble": "surface_2", "sub": "text_sub",
         "line": "border", "user": "ok"}


def _blank(m):
    """把注释替换成等长空白（保留换行），这样行号不会漂。"""
    return re.sub(r"[^\n]", " ", m.group(0))


def strip_comments(text, js=False):
    text = _RE_COMMENT.sub(_blank, text)
    if js:
        text = re.sub(r"(?m)//[^\n]*", lambda m: " " * len(m.group(0)), text)
    return text


def role_value(role, pal):
    """--text-sub / text_sub / textSub → 调色板里的颜色。"""
    key = ALIAS.get(role, role).replace("-", "_")
    key = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
    return pal.get(key)


def parse_color(value, pal):
    """把一条 CSS 颜色值解析成 #rrggbb（可含 alpha 合成）。返回 (hex|None, alpha)。

    value 可以是 #hex / rgb() / rgba() / var(--role) / var(--role, #fallback) / color-mix()。
    """
    v = (value or "").strip()
    if not v:
        return None, 1.0
    m = _RE_MIX.search(v)
    if m:
        a, pct, b = m.group(1).strip(), float(m.group(2)) / 100.0, m.group(3).strip()
        ca, _ = parse_color(a, pal)
        cb, _ = parse_color(b, pal)
        if ca and cb:
            return blend_hex(ca, cb, pct), 1.0
        return None, 1.0
    m = _RE_VAR.search(v)
    if m:
        hit = role_value(m.group(1), pal)
        if hit:
            return hit, 1.0
        if m.group(2):
            return parse_color(m.group(2), pal)
        return None, 1.0
    m = _RE_RGBA.search(v)
    if m:
        a = float(m.group(4)) if m.group(4) else 1.0
        return "#%02x%02x%02x" % (int(m.group(1)), int(m.group(2)), int(m.group(3))), a
    m = HEX6.search(v) or re.search(r"#[0-9a-fA-F]{3}\b", v)
    if m:
        h = m.group(0)
        return ("#" + "".join(ch * 2 for ch in h[1:]) if len(h) == 4 else h), 1.0
    return None, 1.0


def blend_hex(fg, bg, alpha):
    r, g, b = hex_to_rgb(fg)
    br, bgc, bb = hex_to_rgb(bg)
    return "#%02x%02x%02x" % (round(r * alpha + br * (1 - alpha)),
                              round(g * alpha + bgc * (1 - alpha)),
                              round(b * alpha + bb * (1 - alpha)))


def _is_placeholder(sel):
    return "placeholder" in (sel or "").lower()


def _is_disabled(sel, line):
    s = ((sel or "") + " " + (line or "")).lower()
    return "disabled" in s


def text_scan_files():
    """网页端文字色扫描范围：web 下**全部** .css/.html/.js。

    注意不能复用 scan_files()：那份清单里 .html 是非递归的（只扫 web/*.html），
    而文字色主要长在 web/screens/*.html 和 web/js/**/*.js 里 —— 用它扫等于漏掉八成。
    """
    out = []
    web = os.path.join(ROOT, "web")
    for base, dirs, files in os.walk(web):
        dirs[:] = [d for d in dirs if d not in ("vendor", "live2d", "node_modules")]
        for fn in sorted(files):
            if not fn.endswith((".css", ".html", ".js")) or fn in SKIP_BASENAMES:
                continue
            out.append(os.path.join(base, fn))
    return sorted(out)


def web_text_units():
    """产出网页端每一条文字色声明：dict(rel, line, sel, prop, value, bg, whitelist)。"""
    out = []
    for path in text_scan_files():
        fn = os.path.basename(path)
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        try:
            raw = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        js = fn.endswith(".js")
        txt = strip_comments(raw, js=js)
        raw_lines = raw.split("\n")
        if fn.endswith(".css"):
            for m in _RE_RULE.finditer(txt):
                sel = m.group(1).strip().replace("\n", " ")
                body = m.group(2)
                line = txt.count("\n", 0, m.start()) + 1
                bgs = [b.group(2).strip() for b in _RE_BG.finditer(body)]
                for d in _RE_TEXT.finditer(body):
                    out.append(dict(rel=rel, line=line, sel=sel[:120], prop=d.group(1),
                                    value=d.group(2).strip(), bg=bgs[0] if bgs else None,
                                    skip=None,
                                    whitelist=("::placeholder" if _is_placeholder(sel) else
                                               "disabled" if _is_disabled(sel, "") else None)))
        else:
            # HTML 行内 style / JS 里的 cssText 字符串：一行一条，按行判最稳
            skip = None            # 自绘底色区域的状态（见 SKIP_BEGIN）
            for i, line in enumerate(txt.split("\n"), 1):
                m = SKIP_BEGIN.search(line)
                if m:
                    skip = m.group(1)
                    continue
                if SKIP_END in line:
                    skip = None
                    continue
                for d in _RE_TEXT.finditer(";" + line):
                    body = ";" + line
                    bgs = [b.group(2).strip() for b in _RE_BG.finditer(body)]
                    reason = None
                    if _is_placeholder(line):
                        reason = "::placeholder"
                    elif _is_disabled("", line):
                        reason = "disabled"
                    elif "console." in line:
                        reason = "console"
                    elif "aria-hidden" in line or any(
                            u"水印" in raw_lines[k] for k in range(max(0, i - 9), i)):
                        reason = "watermark"
                    out.append(dict(rel=rel, line=i, sel=("<inline>" if not js else "<js>"),
                                    prop=d.group(1), value=d.group(2).strip(),
                                    bg=bgs[0] if bgs else None, whitelist=reason, skip=skip))
    return out


_RE_KT_COPY = re.compile(r"copy\(\s*alpha\s*=\s*(0?\.\d+)f\s*\)")
_RE_KT_THEME = re.compile(r"\btheme\.([A-Za-z0-9_]+)")
_RE_KT_COLOR = re.compile(r"(?:color|tint)\s*=\s*(.+?)\s*(?:,|$)", re.I)
_RE_KT_LITERAL = re.compile(r"Color\(\s*0x([0-9a-fA-F]{8})\s*\)")
_RE_KT_RGB = re.compile(r"Color\.rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")


def android_text_units():
    """产出安卓端每一条文字色声明（严格只看 `color =` / `tint =` 语境）。

    刻意不收 `Color.rgb(…)`：那是 Canvas 上画生成头像的 TextPaint 颜色，
    背景是被画出来的渐变，静态推不出来 —— 收进来只会制造误报。
    """
    out = []
    d = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick")
    if not os.path.isdir(d):
        return out
    ctx = re.compile(r"(?:^|[^A-Za-z])(?:color|tint)\s*=", re.I)
    skip_files = {"Theme.kt", "Tokens.kt", "IconNames.kt"}
    for path in scan_files():
        if not path.endswith(".kt") or not path.startswith(d):
            continue
        if os.path.basename(path) in skip_files:
            continue
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        try:
            raw = io.open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        txt = strip_comments(raw, js=True)
        for i, line in enumerate(txt.split("\n"), 1):
            if not ctx.search(line):
                continue
            reason = "disabled" if "disabled" in line.lower() else None
            m = _RE_KT_COPY.search(line)
            if m:
                out.append(dict(rel=rel, line=i, sel="<kt>", prop="copy(alpha)",
                                value=float(m.group(1)), bg=None, whitelist=reason,
                                literal=None, alpha=float(m.group(1))))
                continue
            for lit in _RE_KT_LITERAL.finditer(line):
                argb = lit.group(1)
                out.append(dict(rel=rel, line=i, sel="<kt>", prop="Color(0x)",
                                value="#" + argb[2:].lower(), bg=None, whitelist=reason,
                                literal="#" + argb[2:].lower(), alpha=int(argb[:2], 16) / 255.0))
    return out


def _kt_role_expr(line, pal):
    """从一行 Kotlin 里认出 theme.textSub / DickTokens.dark.text 这类表达式 → 颜色。"""
    for m in _RE_KT_THEME.finditer(line):
        hit = role_value(m.group(1), pal)
        if hit:
            return hit
    return None


def dim_reason(value, pal=None):
    """一条 CSS 文字色值是不是"浅色字"？是则返回原因串，否则 None（纯函数，测试可自检）。

    判据（与用户口径一致）：
      · `rgba(…, a)` 且 a < 0.6        → 半透明浅色字
      · 已知暗底次要灰（DIM_HEX）       → 硬编码灰度，浅底上直接糊掉
      · 值里已经用了**存在的**颜色令牌  → 不算（令牌自己由矩阵那段按 4.5 卡）
    """
    v = value or ""
    m = _RE_VAR.search(v)
    if m and role_value(m.group(1), pal or _default_pal()):
        return None
    for mm in _RE_RGBA.finditer(v):
        if mm.group(4) and float(mm.group(4)) < DIM_ALPHA:
            return u"rgba alpha=%s < %s" % (mm.group(4), DIM_ALPHA)
    for h in re.findall(r"#[0-9a-fA-F]{3,8}\b", v):
        hh = ("#" + "".join(c * 2 for c in h[1:]) if len(h) == 4 else h.lower())
        if hh in DIM_HEX or h.lower() in DIM_HEX:
            return u"已知暗灰 %s" % h
    return None


def check_no_dim_text(data):
    """① 浅色字声明零容忍：alpha<0.6 的 rgba / 已知暗灰 hex / 安卓 copy(alpha=0.x)。

    返回 (violations, whitelist)。violations 里每条是 (rel, line, 说明)。
    """
    pals = palettes_of(data)
    viol, white = [], []
    for u in web_text_units():
        if u.get("skip"):
            continue           # 自绘底色区域（见 SKIP_BEGIN）：条数上限由测试钉住
        dim = dim_reason(u["value"], pals["dark"])
        if not dim:
            continue
        if u["whitelist"]:
            white.append((u["rel"], u["line"], dim, u["whitelist"]))
        else:
            viol.append((u["rel"], u["line"], u"color:%s（%s）" % (u["value"], dim)))
    # 网页端已改干净后，安卓端单独判：copy(alpha = 0.[0-6]) 出现在 color=/tint= 语境
    for u in android_text_units():
        if u["prop"] != "copy(alpha)":
            continue
        if u["alpha"] > DIM_ALPHA_KT + 1e-9:
            continue
        if u["whitelist"]:
            white.append((u["rel"], u["line"], u"alpha=%s" % u["alpha"], u["whitelist"]))
        else:
            viol.append((u["rel"], u["line"], u"copy(alpha = %sf)：文字色被压到 %d%%"
                         % (u["alpha"], round(u["alpha"] * 100))))
    return viol, white


def text_pairs(data):
    """把每条文字色与它自己的背景配对并算比值。

    产出 dict(ratio, need, rel, line, theme, value, bg_desc)。
    `check_text_contrast()` 与 `min_text_ratio()` 都走这里，避免两套算法给出两套结论。
    """
    pals = palettes_of(data)
    out = []
    canvas = ("bg", "surface", "surface_2")
    for theme in ("dark", "light"):
        pal = pals[theme]
        for u in web_text_units():
            need = TEXT_MIN
            if u["whitelist"] == "::placeholder":
                need = PLACEHOLDER_MIN
            elif u["whitelist"] in ("disabled", "console", "watermark"):
                continue
            skip = u.get("skip")
            if skip == "badge":
                continue                       # 状态徽标：不算正文（见 SKIP_BEGIN）
            if theme == "light" and (skip == "fixed-dark" or not _theme_aware(u["rel"])):
                continue                       # 自带纯黑画布 / 独立固定调色板页：只按暗色判
            fg, a = parse_color(u["value"], pal)
            if not fg:
                out.append(dict(ratio=None, need=need, rel=u["rel"], line=u["line"],
                                theme=theme, value=u["value"], bg_desc=u"解析不出颜色"))
                continue
            best = None
            if u["bg"]:
                bg, ba = parse_color(u["bg"], pal)
                if bg:
                    if ba >= 0.999:
                        best = (contrast(blend_hex(fg, bg, a), bg), bg)
                    else:
                        for role in canvas:
                            comp = blend_hex(bg, pal[role], ba)
                            r = contrast(blend_hex(fg, comp, a), comp)
                            if best is None or r > best[0]:
                                best = (r, u"把 %s 压在 --%s 上" % (u["bg"], role))
            if best is None:
                for role in canvas:
                    base = pal[role]
                    r = contrast(blend_hex(fg, base, a), base)
                    if best is None or r > best[0]:
                        best = (r, u"最有利底 --%s" % role)
            out.append(dict(ratio=best[0], need=need, rel=u["rel"], line=u["line"],
                            theme=theme, value=u["value"], bg_desc=best[1]))
        for u in android_text_units():
            if u["prop"] == "copy(alpha)" or u["whitelist"]:
                continue
            fg, a = u["literal"], u["alpha"]
            if not fg or a < 0.999:
                continue          # 带 alpha 的字面色交给 ① 判
            best = None
            for role in canvas:
                base = pal[role]
                r = contrast(fg, base)
                if best is None or r > best[0]:
                    best = (r, u"最有利底 --%s" % role)
            out.append(dict(ratio=best[0], need=TEXT_MIN, rel=u["rel"], line=u["line"],
                            theme=theme, value=u["value"], bg_desc=best[1]))
    return out


def check_text_contrast(data, top=12):
    """② 所有文字色 vs 其背景 ≥4.5（占位符 ≥3.0）。返回 (fails, checked, skipped)。"""
    fails, skipped = [], 0
    for p in text_pairs(data):
        if p["ratio"] is None:
            skipped += 1
            continue
        if p["ratio"] < p["need"]:
            fails.append((p["rel"], p["line"], p["theme"], p["value"],
                          p["bg_desc"], p["ratio"], p["need"]))
    return fails, len(text_pairs(data)) - skipped, skipped


_PAL_CACHE = {}
_PAL_DEFAULT = []
_AWARE = {}
# 认"这页会不会跟着主题换色"：只看它有没有引用**颜色角色**的变量。
# 别用宽泛的 `var(--` —— 动画时长也能写成 var(--d,4s)，那会让一整张固定调色板的
# 美术页（gothic_frame）被误判成会换主题，然后按浅色底给出一堆假 FAIL。
_RE_THEME_VAR = re.compile(
    r"var\(\s*--(bg|surface|surface-2|border|border-strong|text|text-sub|text-dim|accent|"
    r"accent-text|danger|warn|ok|focus-ring|panel|bubble|sub|line|user)\b")


def _theme_aware(rel):
    """整页没有一处颜色令牌变量的，是自带固定调色板的独立页 —— 只按暗色判。"""
    if rel not in _AWARE:
        try:
            raw = io.open(os.path.join(ROOT, rel.replace("/", os.sep)),
                          encoding="utf-8", errors="replace").read()
        except OSError:
            raw = ""
        _AWARE[rel] = bool(_RE_THEME_VAR.search(raw))
    return _AWARE[rel]


def _default_pal():
    """暗色调色板（`dim_reason` 的默认参照，只读一次令牌文件）。"""
    if not _PAL_DEFAULT:
        _PAL_DEFAULT.append(palettes_of(load_tokens())["dark"])
    return _PAL_DEFAULT[0]


def palettes_of(data):
    """暗/浅两套调色板（audit 与 test 共用；不 import gen_tokens，避免循环依赖）。"""
    key = id(data)
    if key not in _PAL_CACHE:
        _PAL_CACHE[key] = {"dark": dict(data["colors"]["dark"]),
                           "light": dict(data["colors"]["light"])}
    return _PAL_CACHE[key]


# ============================================================
#  main
# ============================================================
def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    quiet = "--quiet" in argv
    top = 15
    if "--top" in argv:
        try:
            top = int(argv[argv.index("--top") + 1])
        except (IndexError, ValueError):
            pass
    data = load_tokens()
    pals = {"dark": data["colors"]["dark"], "light": data["colors"]["light"]}

    n_fail = n_warn = n_missing = 0
    for name in ("dark", "light"):
        if not quiet:
            print(u"== 对比度矩阵 · %s ==" % name)
        fail, warn, missing = print_matrix(pals[name], name, data)
        n_fail += len(fail)
        n_warn += len(warn)
        n_missing += len(missing)
        if fail and quiet:
            for pair, r, need in fail:
                print(u"  [FAIL] %s %s = %.2f < %g" % (name, pair, r, need))
        if missing:
            for pair in missing:
                print(u"  [缺失] %s %s 组合引用了不存在的角色" % (name, pair))

    print(u"")
    print(u"== 汇总 ==")
    print(u"  判定：FAIL %d ／ WARN %d ／ 必需组合缺失 %d" % (n_fail, n_warn, n_missing))

    total, hits = scan_drift(data)
    by_file = {}
    for rel, line, col in hits:
        by_file.setdefault(rel, []).append((line, col))
    print(u"  漂移：硬编码颜色出现 %d 处，其中 **不在令牌里 %d 处**（分布在 %d 个文件）"
          % (total, len(hits), len(by_file)))
    if not quiet and hits:
        print(u"  -- 不在令牌里的出现位置（前 %d 条，后续逐屏收敛用）--" % top)
        shown = 0
        for rel in sorted(by_file, key=lambda k: -len(by_file[k])):
            for line, col in by_file[rel]:
                if shown >= top:
                    break
                print(u"    %s:%d  %s" % (rel, line, col))
                shown += 1
            if shown >= top:
                break
        print(u"  -- 按文件统计 --")
        for rel in sorted(by_file, key=lambda k: -len(by_file[k])):
            print(u"    %-58s %d" % (rel, len(by_file[rel])))

    bad = n_fail + n_missing

    # ---- ③ 文字色 vs 其背景 ----
    n_dim, white = check_no_dim_text(data)
    print(u"")
    print(u"== 文字色 vs 其背景（去浅色字） ==")
    print(u"  浅色字声明：FAIL %d ／ 白名单保留 %d" % (len(n_dim), len(white)))
    for rel, line, why in n_dim[:top]:
        print(u"    [FAIL] %s:%d  %s" % (rel, line, why))
    if len(n_dim) > top:
        print(u"    … 另有 %d 处" % (len(n_dim) - top))
    if white and not quiet:
        print(u"  -- 白名单（功能态，不算正文）--")
        for rel, line, why, reason in white:
            print(u"    %s:%d  %s  → %s" % (rel, line, why, reason))

    t_fails, t_checked, t_skipped = check_text_contrast(data)
    print(u"  文字色/背景配对：检查 %d 对（换两套主题各算一遍），不达标 %d 对，"
          u"解析不了跳过 %d" % (t_checked, len(t_fails), t_skipped))
    for rel, line, theme, val, bg, r, need in t_fails[:top]:
        print(u"    [FAIL] %s:%d [%s] %s 压 %s = %.2f < %g"
              % (rel, line, theme, val, bg, r, need))
    if len(t_fails) > top:
        print(u"    … 另有 %d 对" % (len(t_fails) - top))

    bad += len(n_dim) + len(t_fails)
    if bad:
        print(u"[FAIL] 配置不达标（%d 项）—— 调 design/tokens.json 后重跑，别改阈值。" % bad)
        return 1
    print(u"[ok] 必需组合全部达标（%d 项 FAIL ／ %d 项 WARN 仅装饰）；"
          u"无浅色字声明，文字色全部 ≥%g:1" % (n_fail, n_warn, TEXT_MIN))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
