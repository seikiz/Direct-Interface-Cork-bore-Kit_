package com.dick.narrative.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/* 哥特暗色：墨底、暗金、细线。刻<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌意不跟随系统亮色，避免黑白混用。 */

val Ink = Color(0xFF0B0B0D)
val Panel = Color(0xFF14141A)
val PanelHi = Color(0xFF1D1D25)
val LineCol = Color(0xFF2E2E3A)
val TextMain = Color(0xFFE8E6E3)
val TextSub = Color(0xFF9A97A0)
val Accent = Color(0xFFB9A16B)
val AccentDim = Color(0xFF6B5F44)

private val Scheme = darkColorScheme(
    primary = Accent,
    onPrimary = Ink,
    secondary = AccentDim,
    onSecondary = TextMain,
    background = Ink,
    onBackground = TextMain,
    surface = Panel,
    onSurface = TextMain,
    surfaceVariant = PanelHi,
    onSurfaceVariant = TextSub,
    outline = LineCol,
)

@Composable
fun NarrTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Scheme, content = content)
}
