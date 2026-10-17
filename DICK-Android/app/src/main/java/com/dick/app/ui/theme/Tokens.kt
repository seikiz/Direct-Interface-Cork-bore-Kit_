// 生成物：由 tools/gen_tokens.py 从 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌design/tokens.json 生成，别手改。
//   改配色：改 design/tokens.json，再跑 python tools/gen_tokens.py。
//   验收：python tools/audit_contrast.py。

package com.dick.app

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 一套配色。字段名与 design/tokens.json 的颜色角色一一对应（暗/浅键名一致）。 */
data class DickPalette(
    val bg: Color,
    val surface: Color,
    val surface2: Color,
    val border: Color,
    val borderStrong: Color,
    val text: Color,
    val textSub: Color,
    val textDim: Color,
    val accent: Color,
    val accentText: Color,
    val danger: Color,
    val warn: Color,
    val ok: Color,
    val focusRing: Color
)

/** 一枚可选强调色：暗色 / 浅色各一个（浅色底上原亮色当文字色不达标，另给深色版）。 */
data class DickAccent(val key: String, val name: String, val dark: Color, val light: Color)

/** 主题模式：跟随系统（默认）/ 深色 / 浅色 / OLED。 */
enum class DickThemeMode { System, Dark, Light, Oled }

/** 当前生效的配色（由 DickTheme 提供）：不想层层传参的组件用 LocalDickPalette.current。 */
val LocalDickPalette = staticCompositionLocalOf { DickTokens.dark }

/**
 * 设计令牌（唯一真相 design/tokens.json 的生成物）。
 * 颜色：dark / light / oled；尺寸：radius* / space* / font* / lh* / icon*。
 */
object DickTokens {
    /** 暗色（默认） */
    val dark = DickPalette(
        bg = Color(0xFF0F1115),
        surface = Color(0xFF14161C),
        surface2 = Color(0xFF1A1E26),
        border = Color(0xFF5C6478),
        borderStrong = Color(0xFF7B8598),
        text = Color(0xFFE5E7EB),
        textSub = Color(0xFF94A3B8),
        textDim = Color(0xFF7C8598),
        accent = Color(0xFF60A5FA),
        accentText = Color(0xFF0B1220),
        danger = Color(0xFFF87171),
        warn = Color(0xFFF59E0B),
        ok = Color(0xFF4ADE80),
        focusRing = Color(0xFF93C5FD),
    )
    /** 浅色（跟随系统时用） */
    val light = DickPalette(
        bg = Color(0xFFF5F6F8),
        surface = Color(0xFFFFFFFF),
        surface2 = Color(0xFFFFFFFF),
        border = Color(0xFF8A9199),
        borderStrong = Color(0xFF6B7280),
        text = Color(0xFF1F2937),
        textSub = Color(0xFF656C79),
        textDim = Color(0xFF7F8792),
        accent = Color(0xFF2563EB),
        accentText = Color(0xFFFFFFFF),
        danger = Color(0xFFCF2222),
        warn = Color(0xFFB45309),
        ok = Color(0xFF15803D),
        focusRing = Color(0xFF1D4ED8),
    )
    /** OLED：暗色压黑 */
    val oled = DickPalette(
        bg = Color(0xFF000000),
        surface = Color(0xFF0A0A0C),
        surface2 = Color(0xFF101014),
        border = Color(0xFF5C6478),
        borderStrong = Color(0xFF7B8598),
        text = Color(0xFFE5E7EB),
        textSub = Color(0xFF94A3B8),
        textDim = Color(0xFF7C8598),
        accent = Color(0xFF60A5FA),
        accentText = Color(0xFF0B1220),
        danger = Color(0xFFF87171),
        warn = Color(0xFFF59E0B),
        ok = Color(0xFF4ADE80),
        focusRing = Color(0xFF93C5FD),
    )

    /** 可选强调色（与网页端 ACCENTS 同一份） */
    val accents: List<DickAccent> = listOf(
        DickAccent("blue", "蓝", Color(0xFF60A5FA), Color(0xFF2563EB)),
        DickAccent("green", "绿", Color(0xFF4ADE80), Color(0xFF15803D)),
        DickAccent("purple", "紫", Color(0xFFA78BFA), Color(0xFF6D28D9)),
        DickAccent("pink", "粉", Color(0xFFF472B6), Color(0xFFBE185D)),
    )

    val radiusSm: Dp = 6.dp
    val radiusMd: Dp = 12.dp
    val radiusLg: Dp = 14.dp
    val radiusPill: Dp = 999.dp
    val iconSm: Dp = 12.dp
    val iconMd: Dp = 16.dp
    val iconLg: Dp = 20.dp
    val iconXl: Dp = 24.dp
    val space1: Dp = 2.dp
    val space2: Dp = 4.dp
    val space3: Dp = 6.dp
    val space4: Dp = 8.dp
    val space5: Dp = 12.dp
    val space6: Dp = 16.dp
    val space7: Dp = 20.dp
    val space8: Dp = 24.dp
    val fontXs: TextUnit = 11.sp
    val fontSm: TextUnit = 12.sp
    val fontMd: TextUnit = 13.sp
    val fontLg: TextUnit = 15.sp
    val fontXl: TextUnit = 18.sp
    val lhTight: Float = 1.3f
    val lhNormal: Float = 1.55f
    val lhLoose: Float = 1.8f
}

/** 主题模式 + 系统当前是否深色 → 落到哪套配色。 */
fun dickPalette(mode: DickThemeMode, systemDark: Boolean): DickPalette = when (mode) {
    DickThemeMode.Dark -> DickTokens.dark
    DickThemeMode.Light -> DickTokens.light
    DickThemeMode.Oled -> DickTokens.oled
    DickThemeMode.System -> if (systemDark) DickTokens.dark else DickTokens.light
}

/** 主题模式 + 系统是否深色 → 是不是浅色（决定用哪一版强调色/哪套 Material 语义色）。 */
fun dickIsLight(mode: DickThemeMode, systemDark: Boolean): Boolean = when (mode) {
    DickThemeMode.Light -> true
    DickThemeMode.Dark, DickThemeMode.Oled -> false
    DickThemeMode.System -> !systemDark
}

/** 取第 idx 枚强调色（浅色主题用深色版，保证压在浅底上的文字/图标达标）。 */
fun accentFor(idx: Int, light: Boolean): Color {
    val a = DickTokens.accents[idx.coerceIn(0, DickTokens.accents.size - 1)]
    return if (light) a.light else a.dark
}

/**
 * 两端统一的主题入口：套一层 MaterialTheme，**只映射需要的槽位**
 * （primary/背景/表面/错误/描边），不整套替换 Material 3 语义色 ——
 * 换掉整套会把没显式传色的控件（Button/TextField/Switch）也一起改样。
 */
@Composable
fun DickTheme(
    mode: DickThemeMode = DickThemeMode.System,
    accentIdx: Int = 0,
    content: @Composable () -> Unit,
) {
    // 跟随系统：isSystemInDarkTheme() 决定落暗还是浅；显式选深/浅/OLED 时以用户选择为准。
    val systemDark = isSystemInDarkTheme()
    val pal = dickPalette(mode, systemDark)
    val light = dickIsLight(mode, systemDark)
    val acc = accentFor(accentIdx, light)
    val scheme = if (light) lightColorScheme(
        primary = acc, onPrimary = pal.accentText,
        background = pal.bg, onBackground = pal.text,
        surface = pal.surface, onSurface = pal.text,
        surfaceVariant = pal.surface2, onSurfaceVariant = pal.textSub,
        outline = pal.border, outlineVariant = pal.borderStrong,
        error = pal.danger, onError = pal.accentText,
    ) else darkColorScheme(
        primary = acc, onPrimary = pal.accentText,
        background = pal.bg, onBackground = pal.text,
        surface = pal.surface, onSurface = pal.text,
        surfaceVariant = pal.surface2, onSurfaceVariant = pal.textSub,
        outline = pal.border, outlineVariant = pal.borderStrong,
        error = pal.danger, onError = pal.accentText,
    )
    CompositionLocalProvider(LocalDickPalette provides pal) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}
