# -*- coding: utf-8 -*-
"""gen_tokens.py —— 设计令牌唯一真相 `design/tokens.json` → 两端产物。

为什么要有它
------------
配色原来散在三个地方各写一套：`web/index.html` 的行内 `:root`/`body.light`/`body.oled`、
`DICK-Android/.../Theme.kt` 的 `THEMES`/`ACCENTS`、以及组件里几百处 `Color(0xFF…)` 与
`#rrggbb`。三处对不上就是"两端漂"：网页改了安卓没改，或者浅色主题下某块面板还是深色。

现在**唯一真相是 `design/tokens.json`**（14 个颜色角色 × 暗/浅 + 圆角/间距/字号阶梯），
两端产物由本脚本生成：

  · `web/theme.css`      `:root{…}`（暗色默认）+ `@media (prefers-color-scheme:light)`（浅色覆写）
                         + `body.dark/.light/.oled`（应用内显式选择时覆写系统）
  · `DICK-Android/.../app/Tokens.kt`
                         `object DickTokens{ dark / light / oled / accents / 尺寸 }`
                         + `@Composable DickTheme(…)`（`isSystemInDarkTheme()` 切换，
                         只把需要的几个槽位映射进 MaterialTheme，不整套替换）

变量命名口径（不发明新体系）：颜色角色名直接就是 CSS 变量名（`--bg`/`--surface`/…），
网页里原来那套短名（`--panel`/`--bubble`/`--sub`/`--line`/`--user`）作为**一次性别名**
输出在同一份 CSS 里，指向对应语义令牌（映射表见 tokens.json 的 `web_aliases`，报告里也列了）。
别名规则用 `:root, body, body.dark, body.light, body.oled` 一条多选择器规则写，这样
`body.light` 覆写 `--surface` 时，继承下来的 `--panel` 会跟着重新取值（自定义属性的计算值
会就地替换 var()，写在 `:root` 一处会导致浅色主题下别名仍是暗色值）。

用法：
    python tools/gen_tokens.py            # 重新生成两份产物
    python tools/gen_tokens.py --check    # 校验 json + 产物是否最新（CI / 测试用）
    python tools/gen_tokens.py --report   # 令牌表 + 对比度矩阵
退出码：0 正常；1 json 有问题或 --check 发现产物过期。
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 让 `import seiki_mark` / `import audit_<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌contrast` 找得到（同 tools/gen_icons.py 的坑）
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SRC = os.path.join(ROOT, "design", "tokens.json")
CSS_OUT = os.path.join(ROOT, "web", "theme.css")
# 2026-11 UI 解耦：Tokens.kt 跟 Theme.kt 一起搬进 ui/theme/（目录=分区，包名仍是 com.dick.app）
KT_OUT = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick",
                      "app", "ui", "theme", "Tokens.kt")

# 颜色角色：暗/浅必须同名同数（顺序即 CSS / Kotlin 字段顺序）
ROLES = ["bg", "surface", "surface_2", "border", "border_strong", "text", "text_sub",
         "text_dim", "accent", "accent_text", "danger", "warn", "ok", "focus_ring"]
# 非颜色令牌：名字 → 生成时的后缀单位
SIZES = {
    "radius": ["sm", "md", "lg", "pill"],
    "space": ["1", "2", "3", "4", "5", "6", "7", "8"],
    "font_size": ["xs", "sm", "md", "lg", "xl"],
    "line_height": ["tight", "normal", "loose"],
    "icon_size": ["sm", "md", "lg", "xl"],
}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
ZW = re.compile(u"[\u200b-\u200f\u2060\ufeff\u00ad]+")

HEADER_CSS = (u"/* 生成物：由 tools/gen_tokens.py 从 design/tokens.json 生成，别手改。\n"
              u"   改配色：改 design/tokens.json，再跑 python tools/gen_tokens.py。\n"
              u"   验收：python tools/audit_contrast.py（对比度矩阵 + 漂移扫描）。\n"
              u"   默认暗色，跟随系统；body.dark/.light/.oled 是应用内显式选择时的覆写。 */\n")
HEADER_KT = (u"// 生成物：由 tools/gen_tokens.py 从 design/tokens.json 生成，别手改。\n"
             u"//   改配色：改 design/tokens.json，再跑 python tools/gen_tokens.py。\n"
             u"//   验收：python tools/audit_contrast.py。\n")


# ---------------- 水印（与 tools/gen_icons.py 同一套做法） ----------------
def _clean(text):
    """剥掉水印（可见的 `<seiki>` 前缀 + 零宽负载）后再比内容。"""
    return ZW.sub(u"", text.replace(u"<seiki>", u""))


def _mark(path, text):
    try:
        import seiki_mark as SM
        styles = SM.COMMENT.get(os.path.splitext(path)[1].lower())
        if styles:
            text, _st, _why = SM.embed(text, None, styles, fmt="native")
    except Exception:
        pass
    return text


def _read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


# ---------------- 载入与校验 ----------------
def load():
    """返回 (data, problems)。problems 非空表示令牌本身不合法，产物不能生成。"""
    problems = []
    if not os.path.isfile(SRC):
        return None, [u"找不到唯一真相 design/tokens.json"]
    try:
        with io.open(SRC, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        return None, [u"design/tokens.json 不是合法 JSON：%s" % e]

    colors = data.get("colors") or {}
    for theme in ("dark", "light"):
        pal = colors.get(theme)
        if not isinstance(pal, dict):
            problems.append(u"colors.%s 缺失" % theme)
            continue
        for role in ROLES:
            v = pal.get(role)
            if v is None:
                problems.append(u"colors.%s.%s 缺失（每个角色暗/浅都必须有）" % (theme, role))
            elif not (isinstance(v, str) and HEX.match(v)):
                problems.append(u"colors.%s.%s = %r 不是 #rrggbb" % (theme, role, v))
        extra = [k for k in pal if not k.startswith("_") and k not in ROLES]
        if extra:
            problems.append(u"colors.%s 有多余角色 %s（角色表是两端共用的，别单边加）"
                            % (theme, u"、".join(extra)))
    # OLED 只是覆写，键必须在 ROLES 里
    for k in (data.get("oled") or {}):
        if k not in ROLES:
            problems.append(u"oled.%s 不是合法角色名" % k)

    for acc in data.get("accents") or []:
        for k in ("key", "name", "dark", "light"):
            if not acc.get(k):
                problems.append(u"accents 条目缺 %s：%r" % (k, acc))
        for k in ("dark", "light"):
            if acc.get(k) and not HEX.match(acc.get(k) or ""):
                problems.append(u"accents[%s].%s 不是 #rrggbb" % (acc.get("key"), k))

    for group, keys in SIZES.items():
        node = data.get(group)
        if not isinstance(node, dict):
            problems.append(u"%s 缺失（非颜色令牌）" % group)
            continue
        for k in keys:
            v = node.get(k)
            if not isinstance(v, (int, float)):
                problems.append(u"%s.%s 必须是数字，当前 %r" % (group, k, v))

    # 别名只能指向真实角色
    for alias, target in (data.get("web_aliases") or {}).items():
        if alias.startswith("_"):
            continue
        if target not in ROLES:
            problems.append(u"web_aliases.%s → %s 不是合法角色名" % (alias, target))
    return (None if problems else data), problems


def palettes(data):
    """返回 {主题名: {角色: '#rrggbb'}}。oled 由 dark 覆写而来（唯一真相里只存三个覆写）。"""
    out = {"dark": dict(data["colors"]["dark"]), "light": dict(data["colors"]["light"])}
    oled = dict(out["dark"])
    oled.update({k: v for k, v in (data.get("oled") or {}).items() if not k.startswith("_")})
    out["oled"] = oled
    return out


def aliases(data):
    return {k: v for k, v in (data.get("web_aliases") or {}).items() if not k.startswith("_")}


# ---------------- web/theme.css ----------------
def _css_palette(pal, indent=u"  "):
    o = []
    for role in ROLES:
        o.append(u"%s--%s:%s;" % (indent, role.replace(u"_", u"-"), pal[role]))
    return o


def gen_css(data):
    pals = palettes(data)
    o = [HEADER_CSS]
    # 1) 暗色默认（:root）
    o.append(u":root{")
    o.append(u"  color-scheme:dark;")
    o.append(u"  /* 颜色角色 · 暗色（默认） */")
    o.extend(_css_palette(pals["dark"]))
    o.extend(_css_sizes(data))
    o.append(u"}")
    # 2) 跟随系统：浅色覆写
    o.append(u"/* 跟随系统：系统是浅色就整片换浅色（正文/次要文字/边框都已按 AA 调过） */")
    o.append(u"@media (prefers-color-scheme: light){")
    o.append(u"  :root{")
    o.append(u"    color-scheme:light;")
    o.extend(_css_palette(pals["light"], u"    "))
    o.append(u"  }")
    o.append(u"}")
    # 3) 应用内显式选择（网页「主题」循环：深色/浅色/OLED/跟随系统）
    for name, why in ((u"dark", u"显式选深色：系统即使是浅色也压回暗色"),
                      (u"light", u"显式选浅色"),
                      (u"oled", u"OLED：暗色压黑（只有 bg/surface/surface_2 换，其它角色共用暗色）")):
        o.append(u"/* body.%s —— %s */" % (name, why))
        o.append(u"body.%s{" % name)
        o.append(u"  color-scheme:%s;" % (u"light" if name == u"light" else u"dark"))
        o.extend(_css_palette(pals[name]))
        o.append(u"}")
    # 4) 旧变量名 → 语义令牌（一次性映射）
    al = aliases(data)
    o.append(u"/* 旧变量名 → 语义令牌（一次性映射，见 tokens.json 的 web_aliases）：")
    o.append(u"   网页现有 CSS 与 JS 还在用 --panel/--bubble/--sub/--line/--user，这里让它们指向新角色。")
    o.append(u"   选择器写成一条多元素规则：body.light 覆写 --surface 时，继承来的 --panel 会重新取值。 */")
    o.append(u":root, body, body.dark, body.light, body.oled{")
    for alias in sorted(al):
        o.append(u"  --%s:var(--%s);" % (alias, al[alias].replace(u"_", u"-")))
    o.append(u"  --radius:var(--radius-md);   /* 气泡圆角（原 --radius:12px） */")
    o.append(u"}")
    # 5) 焦点环：原来只有 :focus 改边框色，键盘用户看不出焦点
    o.append(u"/* 焦点环：键盘 Tab 走一遍就看得出在哪（原来只有 :focus 改边框色，等于没有） */")
    o.append(u":focus-visible{ outline:2px solid var(--focus-ring); outline-offset:2px; }")
    return u"\n".join(o) + u"\n"


def _css_sizes(data):
    """非颜色令牌 → CSS 变量。圆角/间距/字号阶梯都是 px，行高是倍数。"""
    o = [u"  /* 尺寸令牌（px；行高是倍数） */"]
    for k in SIZES["radius"]:
        o.append(u"  --radius-%s:%spx;" % (k, _num(data["radius"][k])))
    for k in SIZES["space"]:
        o.append(u"  --space-%s:%spx;" % (k, _num(data["space"][k])))
    for k in SIZES["font_size"]:
        o.append(u"  --font-%s:%spx;" % (k, _num(data["font_size"][k])))
    for k in SIZES["line_height"]:
        o.append(u"  --lh-%s:%s;" % (k, _num(data["line_height"][k])))
    for k in SIZES["icon_size"]:
        o.append(u"  --icon-%s:%spx;" % (k, _num(data["icon_size"][k])))
    return o


def _num(v):
    """6 → '6'；1.55 → '1.55'；6.0 → '6'（json 里写整数就别输出 6.0）。"""
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return (u"%d" % v) if isinstance(v, int) else (u"%s" % (u"%.4f" % v).rstrip(u"0").rstrip(u"."))


# ---------------- Android Tokens.kt ----------------
def c(hexv):
    """'#0f1115' → 'Color(0xFF0F1115)'（Compose 要求 AARRGGBB）。"""
    return u"Color(0xFF%s)" % hexv.lstrip(u"#").upper()


def _kt_palette(pal, indent=u"        "):
    o = []
    for role in ROLES:
        field = u"".join(w.capitalize() if i else w
                         for i, w in enumerate(role.split(u"_")))
        o.append(u"%s%s = %s," % (indent, field, c(pal[role])))
    return o


def gen_kt(data):
    pals = palettes(data)
    o = [HEADER_KT, u"package com.dick.app", u""]
    o.append(u"import androidx.compose.foundation.isSystemInDarkTheme")
    o.append(u"import androidx.compose.material3.MaterialTheme")
    o.append(u"import androidx.compose.material3.darkColorScheme")
    o.append(u"import androidx.compose.material3.lightColorScheme")
    o.append(u"import androidx.compose.runtime.Composable")
    o.append(u"import androidx.compose.runtime.CompositionLocalProvider")
    o.append(u"import androidx.compose.runtime.staticCompositionLocalOf")
    o.append(u"import androidx.compose.ui.graphics.Color")
    o.append(u"import androidx.compose.ui.unit.Dp")
    o.append(u"import androidx.compose.ui.unit.TextUnit")
    o.append(u"import androidx.compose.ui.unit.dp")
    o.append(u"import androidx.compose.ui.unit.sp")
    o.append(u"")
    o.append(u"/** 一套配色。字段名与 design/tokens.json 的颜色角色一一对应（暗/浅键名一致）。 */")
    o.append(u"data class DickPalette(")
    o.append(u",\n".join(u"    val %s: Color" % r for r in ROLES_KT))
    o.append(u")")
    o.append(u"")
    o.append(u"/** 一枚可选强调色：暗色 / 浅色各一个（浅色底上原亮色当文字色不达标，另给深色版）。 */")
    o.append(u"data class DickAccent(val key: String, val name: String, val dark: Color, val light: Color)")
    o.append(u"")
    o.append(u"/** 主题模式：跟随系统（默认）/ 深色 / 浅色 / OLED。 */")
    o.append(u"enum class DickThemeMode { System, Dark, Light, Oled }")
    o.append(u"")
    o.append(u"/** 当前生效的配色（由 DickTheme 提供）：不想层层传参的组件用 LocalDickPalette.current。 */")
    o.append(u"val LocalDickPalette = staticCompositionLocalOf { DickTokens.dark }")
    o.append(u"")
    o.append(u"/**")
    o.append(u" * 设计令牌（唯一真相 design/tokens.json 的生成物）。")
    o.append(u" * 颜色：dark / light / oled；尺寸：radius* / space* / font* / lh* / icon*。")
    o.append(u" */")
    o.append(u"object DickTokens {")
    for name, key, note in ((u"dark", u"dark", u"暗色（默认）"),
                            (u"light", u"light", u"浅色（跟随系统时用）"),
                            (u"oled", u"oled", u"OLED：暗色压黑")):
        o.append(u"    /** %s */" % note)
        o.append(u"    val %s = DickPalette(" % name)
        o.extend(_kt_palette(pals[key]))
        o.append(u"    )")
    o.append(u"")
    o.append(u"    /** 可选强调色（与网页端 ACCENTS 同一份） */")
    o.append(u"    val accents: List<DickAccent> = listOf(")
    for acc in data["accents"]:
        o.append(u"        DickAccent(%s, %s, %s, %s)," % (
            _s(acc["key"]), _s(acc["name"]), c(acc["dark"]), c(acc["light"])))
    o.append(u"    )")
    o.append(u"")
    for group, unit, dt in ((u"radius", u"dp", u"Dp"), (u"icon", u"dp", u"Dp")):
        src = u"radius" if group == u"radius" else u"icon_size"
        for k in SIZES[src]:
            o.append(u"    val %s%s: %s = %s.%s" % (group, k.capitalize(), dt,
                                                    _num(data[src][k]), unit))
    for k in SIZES["space"]:
        o.append(u"    val space%s: Dp = %s.dp" % (k, _num(data["space"][k])))
    for k in SIZES["font_size"]:
        o.append(u"    val font%s: TextUnit = %s.sp" % (k.capitalize(), _num(data["font_size"][k])))
    for k in SIZES["line_height"]:
        o.append(u"    val lh%s: Float = %sf" % (k.capitalize(), _num(data["line_height"][k])))
    o.append(u"}")
    o.append(u"")
    o.append(u"/** 主题模式 + 系统当前是否深色 → 落到哪套配色。 */")
    o.append(u"fun dickPalette(mode: DickThemeMode, systemDark: Boolean): DickPalette = when (mode) {")
    o.append(u"    DickThemeMode.Dark -> DickTokens.dark")
    o.append(u"    DickThemeMode.Light -> DickTokens.light")
    o.append(u"    DickThemeMode.Oled -> DickTokens.oled")
    o.append(u"    DickThemeMode.System -> if (systemDark) DickTokens.dark else DickTokens.light")
    o.append(u"}")
    o.append(u"")
    o.append(u"/** 主题模式 + 系统是否深色 → 是不是浅色（决定用哪一版强调色/哪套 Material 语义色）。 */")
    o.append(u"fun dickIsLight(mode: DickThemeMode, systemDark: Boolean): Boolean = when (mode) {")
    o.append(u"    DickThemeMode.Light -> true")
    o.append(u"    DickThemeMode.Dark, DickThemeMode.Oled -> false")
    o.append(u"    DickThemeMode.System -> !systemDark")
    o.append(u"}")
    o.append(u"")
    o.append(u"/** 取第 idx 枚强调色（浅色主题用深色版，保证压在浅底上的文字/图标达标）。 */")
    o.append(u"fun accentFor(idx: Int, light: Boolean): Color {")
    o.append(u"    val a = DickTokens.accents[idx.coerceIn(0, DickTokens.accents.size - 1)]")
    o.append(u"    return if (light) a.light else a.dark")
    o.append(u"}")
    o.append(u"")
    o.append(u"/**")
    o.append(u" * 两端统一的主题入口：套一层 MaterialTheme，**只映射需要的槽位**")
    o.append(u" * （primary/背景/表面/错误/描边），不整套替换 Material 3 语义色 ——")
    o.append(u" * 换掉整套会把没显式传色的控件（Button/TextField/Switch）也一起改样。")
    o.append(u" */")
    o.append(u"@Composable")
    o.append(u"fun DickTheme(")
    o.append(u"    mode: DickThemeMode = DickThemeMode.System,")
    o.append(u"    accentIdx: Int = 0,")
    o.append(u"    content: @Composable () -> Unit,")
    o.append(u") {")
    o.append(u"    // 跟随系统：isSystemInDarkTheme() 决定落暗还是浅；显式选深/浅/OLED 时以用户选择为准。")
    o.append(u"    val systemDark = isSystemInDarkTheme()")
    o.append(u"    val pal = dickPalette(mode, systemDark)")
    o.append(u"    val light = dickIsLight(mode, systemDark)")
    o.append(u"    val acc = accentFor(accentIdx, light)")
    o.append(u"    val scheme = if (light) lightColorScheme(")
    o.extend(_scheme_args())
    o.append(u"    ) else darkColorScheme(")
    o.extend(_scheme_args())
    o.append(u"    )")
    o.append(u"    CompositionLocalProvider(LocalDickPalette provides pal) {")
    o.append(u"        MaterialTheme(colorScheme = scheme, content = content)")
    o.append(u"    }")
    o.append(u"}")
    return u"\n".join(o) + u"\n"


ROLES_KT = []
for _r in ROLES:
    ROLES_KT.append(u"".join(w.capitalize() if i else w for i, w in enumerate(_r.split(u"_"))))


def _scheme_args():
    return [
        u"        primary = acc, onPrimary = pal.accentText,",
        u"        background = pal.bg, onBackground = pal.text,",
        u"        surface = pal.surface, onSurface = pal.text,",
        u"        surfaceVariant = pal.surface2, onSurfaceVariant = pal.textSub,",
        u"        outline = pal.border, outlineVariant = pal.borderStrong,",
        u"        error = pal.danger, onError = pal.accentText,",
    ]


def _s(v):
    """Kotlin 字符串字面量（转义反斜杠与引号）。"""
    return u'"%s"' % str(v).replace(u"\\", u"\\\\").replace(u'"', u'\\"')


# ---------------- 写 / 校验 ----------------
def write_or_check(path, text, check):
    old = _read(path) if os.path.isfile(path) else None
    if old is not None and _clean(old) == _clean(text):
        print(u"[ok] %s 已是最新" % os.path.relpath(path, ROOT))
        return True
    if check:
        print(u"[过期] %s 与 design/tokens.json 不一致 —— 跑 python tools/gen_tokens.py 重新生成"
              % os.path.relpath(path, ROOT))
        return False
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_mark(path, text))
    print(u"[写] %s（%d 字符）" % (os.path.relpath(path, ROOT), len(text)))
    return True


def cmd_report(data):
    """令牌表 + 对比度矩阵（矩阵本身由 tools/audit_contrast.py 算，避免两套公式）。"""
    import audit_contrast as AC
    pals = palettes(data)
    print(u"== design/tokens.json ==")
    print(u"  角色 %d 个 × 主题 %d 套（暗/浅/OLED）" % (len(ROLES), len(pals)))
    head = u"  %-14s %-9s %-9s %-9s" % (u"角色", u"暗色", u"浅色", u"OLED")
    print(head)
    for role in ROLES:
        print(u"  %-14s %-9s %-9s %-9s" % (role, pals["dark"][role], pals["light"][role],
                                           pals["oled"][role]))
    print(u"  强调色：%s" % u"、".join(
        u"%s(暗 %s / 浅 %s)" % (a["name"], a["dark"], a["light"]) for a in data["accents"]))
    print(u"  圆角 %s ／ 间距 %s ／ 字号 %s ／ 行高 %s ／ 图标 %s" % (
        u"/".join(u"%s=%s" % (k, _num(data["radius"][k])) for k in SIZES["radius"]),
        u"/".join(_num(data["space"][k]) for k in SIZES["space"]),
        u"/".join(_num(data["font_size"][k]) for k in SIZES["font_size"]),
        u"/".join(_num(data["line_height"][k]) for k in SIZES["line_height"]),
        u"/".join(_num(data["icon_size"][k]) for k in SIZES["icon_size"])))
    for name in ("dark", "light"):
        print(u"  -- %s 对比度 --" % name)
        AC.print_matrix(pals[name], name, data)


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    check = "--check" in argv
    data, problems = load()
    if data is None:
        for p in problems:
            print(u"[问题] " + p)
        return 1
    ok1 = write_or_check(CSS_OUT, gen_css(data), check)
    ok2 = write_or_check(KT_OUT, gen_kt(data), check)
    if "--report" in argv:
        cmd_report(data)
    if check:
        if ok1 and ok2:
            print(u"[ok] 令牌一致：%d 角色 × 暗/浅，%d 枚强调色，尺寸 %d 项"
                  % (len(ROLES), len(data["accents"]),
                     sum(len(v) for v in SIZES.values())))
        else:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
