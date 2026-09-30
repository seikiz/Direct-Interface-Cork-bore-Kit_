package com.dick.app

import androidx.compose.ui.graphics.Color

/**
 * Theme.kt —— 主题/颜色系统（从 App.kt 抽出，重构收拢）
 * 集中定义主题配色与强调色，避免散落在各组件里的硬编码 hex。
 */
data class ThemeSpec(
    val name: String,
    val bg: Color,
    val bubble: Color,
    val text: Color,
    val muted: Color,
    val danger: Color,
    val line: Color,
)

val THEMES = listOf(
    ThemeSpec("深色", Color(0xFF0F1115), Color(0xFF1A1E26), Color(0xFFE5E7EB),
        muted = Color(0xFF94A3B8), danger = Color(0xFFF87171), line = Color(0xFF262B34)),
    ThemeSpec("浅色", Color(0xFFF5F6F8), Color(0xFFFFFFFF), Color(0xFF1F2937),
        muted = Color(0xFF6B7280), danger = Color(0xFFDC2626), line = Color(0xFFE5E7EB)),
    ThemeSpec("OLED", Color(0xFF000000), Color(0xFF101014), Color(0xFFE5E7EB),
        muted = Color(0xFF71717A), danger = Color(0xFFF87171), line = Color(0xFF1C1C22)),
)

val ACCENTS = listOf(
    "蓝" to Color(0xFF60A5FA),
    "绿" to Color(0xFF4ADE80),
    "紫" to Color(0xFFA78BFA),
    "粉" to Color(0xFFF472B6),
)

// 头像配色盘（按<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌名字散列取色）
val AVATAR_PALETTE = listOf(
    Color(0xFF60A5FA), Color(0xFF34D399), Color(0xFFFBBF24), Color(0xFFA78BFA),
    Color(0xFFF472B6), Color(0xFF22D3EE), Color(0xFFFB923C), Color(0xFFF87171),
)

fun speakerColor(name: String): Color {
    if (name == "你") return Color(0xFF4ADE80)
    if (name == "AI" || name.isBlank()) return Color(0xFF94A3B8)
    var h = 0
    for (c in name) h += c.code
    return AVATAR_PALETTE[h % AVATAR_PALETTE.size]
}
