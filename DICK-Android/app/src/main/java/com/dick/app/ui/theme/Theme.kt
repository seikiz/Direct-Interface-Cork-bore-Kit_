package com.dick.app

import androidx.compose.ui.graphics.Color

/**
 * Theme.kt —— 主题/配色系统（颜色值的唯一真相已经搬到 design/tokens.json → Tokens.kt）
 *
 * 这里只留三件业务上的东西：
 *   · THEMES：应用内可选主题（深色/浅色/OLED/跟随系统），色值全部来自 DickTokens，不再手写 hex；
 *   · resolveTheme：把「跟随系统」按系统深浅落到具体一套；
 *   · 说话人身份色（头像底色/名字色）—— 这是「谁的发言」的身份配色，不是主题色，所以留在令牌之外。
 *
 * 为什么 ThemeSpec 改成「持有 DickPalette + 一组 getter」：这两个文件里已经有一百多处
 * `theme.bg / theme.text / theme.muted / theme.line / theme.danger / theme.bubble` 的调用，
 * 改成 getter 就不必动那些调用点（本阶段只统一配色语义，不重排 UI）。
 */
data class ThemeSpec(
    val name: String,
    val mode: DickThemeMode,
    val palette: DickPalette,
) {
    val bg: Color get() = palette.bg
    val bubble: Color get() = palette.surface2
    val text: Color get() = palette.text
    val muted: Color get() = palette.textSub
    val danger: Color get() = palette.danger
    val line: Color get() = palette.border
}

/** 应用内可选主题。前三项是显式选择，最后一项「跟随系统」按 isSystemInDarkTheme() 落暗/浅（网页端 THEMES 同一顺序）。 */
val THEMES = listOf(
    ThemeSpec("深色", DickThemeMode.Dark, DickTokens.dark),
    ThemeSpec("浅色", DickThemeMode.Light, DickTokens.light),
    ThemeSpec("OLED", DickThemeMode.Oled, DickTokens.oled),
    ThemeSpec("跟随系统", DickThemeMode.System, DickTokens.dark),
)

/** 主题序号 + 系统当前是否深色 → 实际生效的主题（「跟随系统」在这里被解析成暗色或浅色）。 */
fun resolveTheme(idx: Int, systemDark: Boolean): ThemeSpec {
    val t = THEMES[idx.coerceIn(0, THEMES.size - 1)]
    return if (t.mode == DickThemeMode.System) {
        if (systemDark) THEMES[0] else THEMES[1]
    } else {
        t
    }
}

/**
 * 强调色：名字给设置界面/循环按钮用（`.first`），`.second` 是暗色版。
 * 真正取色请用 Tokens.kt 的 accentFor(idx, light) —— 浅色主题要用同一色相的深色版，
 * 否则 #60a5fa 这类亮蓝压在浅底上当文字色只有 2.5:1。
 */
val ACCENTS: List<Pair<String, Color>> = DickTokens.accents.map { it.name to it.dark }

// 头像配色盘（按名字散列取色）。身份色，不属于<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌主题令牌：它要保证「同一个人永远同一种颜色」。
// 浅色主题下这些亮色当**文字**会不够（例如 #fbbf24 压白 1.9:1），所以只当头像**底**用，
// 名字色单独走 speakerNameColor()。
val AVATAR_PALETTE = listOf(
    Color(0xFF60A5FA), Color(0xFF34D399), Color(0xFFFBBF24), Color(0xFFA78BFA),
    Color(0xFFF472B6), Color(0xFF22D3EE), Color(0xFFFB923C), Color(0xFFF87171),
)

/** 按名字散列取头像底色（身份色，暗/浅主题都用同一套，保证「同一个人同一个颜色」）。 */
fun speakerColor(name: String): Color {
    if (name == "你") return DickTokens.dark.ok
    if (name == "AI" || name.isBlank()) return DickTokens.dark.textSub
    var h = 0
    for (c in name) h += c.code
    return AVATAR_PALETTE[h % AVATAR_PALETTE.size]
}

/** 名字文字色：压在气泡同级的背景上，所以跟主题走（暗色绿/次要灰，浅色用深绿/深灰）。 */
fun speakerNameColor(name: String, isUser: Boolean, aiColor: Color, pal: DickPalette): Color {
    if (isUser) return pal.ok
    if (name == "AI" || name.isBlank()) return pal.textSub
    return aiColor
}

/* ---------- 显示名（三语）----------
 * THEMES / ACCENTS 的 name 是**给中文界面用的默认名**（也是落盘值的来源），
 * 显示时统一走下面两个函数：索引 → key → 当前语言。缺翻译会回退到 name，不会出现键名。
 */
fun themeLabel(idx: Int): String {
    val t = THEMES[idx.coerceIn(0, THEMES.size - 1)]
    val key = when (t.mode) {
        DickThemeMode.Dark -> "theme_dark"
        DickThemeMode.Light -> "theme_light"
        DickThemeMode.Oled -> "theme_oled"
        DickThemeMode.System -> "theme_system"
    }
    return I18n.t(key, t.name)
}

/** 强调色名（三语）。ACCENTS 与 DickTokens.accents 同序同长（见上面的构造）。 */
fun accentLabel(idx: Int): String {
    val i = idx.coerceIn(0, DickTokens.accents.size - 1)
    return I18n.t("accent_" + DickTokens.accents[i].key, ACCENTS[i].first)
}
