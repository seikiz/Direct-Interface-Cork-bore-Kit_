package com.dick.app

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp

/**
 * 卡片 / 标签 / 勾选行（DICK 的"容器与语义色"三件套）。
 *
 * 语义色走**色调枚举**（DickTone / DickSurfaceTone），不传裸 Color：
 * 屏里以前写 `color = theme.muted`，现在写 `DickTone.Muted` ——
 * 换主题时颜色只可能来自 LocalDickPalette 一处，屏里再也拼不出一个野生 hex。
 *
 * 契约：只吃参数 + 主题令牌（CompositionLocal）。不读 vm、不认屏、不发请求。
 */

/** 语义色调 → 当前主题的实际颜色。改配色只改这里<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（色值本身在 ui/theme/Tokens.kt）。 */
enum class DickTone { Text, Muted, Dim, Accent, Danger, Ok, Warn }

@Composable
fun DickTone.color(): Color {
    val p = LocalDickPalette.current
    return when (this) {
        DickTone.Text -> p.text
        DickTone.Muted -> p.textSub
        DickTone.Dim -> p.textDim
        DickTone.Accent -> p.accent
        DickTone.Danger -> p.danger
        DickTone.Ok -> p.ok
        DickTone.Warn -> p.warn
    }
}

/** 容器色调 → 当前主题的底色（Surface = 卡片底，Surface2 = 选中/浮起，Bubble = 气泡底）。 */
enum class DickSurfaceTone { Surface, Surface2, Bubble }

@Composable
fun DickSurfaceTone.color(): Color {
    val p = LocalDickPalette.current
    return when (this) {
        DickSurfaceTone.Surface -> p.surface
        DickSurfaceTone.Surface2 -> p.surface2
        DickSurfaceTone.Bubble -> p.surface2
    }
}

/**
 * 卡片：一个带圆角与底色的 Surface。
 * `radius` 是**圆角像素值**（8/10/12.dp 是这里真实在用的三档），不是语义档位 ——
 * 保持调用点能逐字复刻搬家前的数值。
 */
@Composable
fun DickCard(
    modifier: Modifier = Modifier,
    radius: Dp = 12.dp,
    tone: DickSurfaceTone = DickSurfaceTone.Surface,
    content: @Composable () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(radius),
        color = tone.color(),
        modifier = modifier,
        content = content,
    )
}

/**
 * 标签 / 徽章 / 状态串：一行带语义色的短文本（可含行首 emoji，自动换图标）。
 * 默认 `DickTone.Muted`（次要信息），`fontSize`/`iconSize` 不给就是 IconText 的默认值 ——
 * 这样"原调用点没写字号"的地方搬过来仍然没写字号。
 */
@Composable
fun DickTag(
    text: String,
    modifier: Modifier = Modifier,
    tone: DickTone = DickTone.Muted,
    fontSize: TextUnit = TextUnit.Unspecified,
    iconSize: Dp = 16.dp,
    maxLines: Int = Int.MAX_VALUE,
) {
    IconText(
        text,
        modifier = modifier,
        fontSize = fontSize,
        color = tone.color(),
        iconSize = iconSize,
        maxLines = maxLines,
    )
}

/**
 * 勾选行：Checkbox + 说明文字。
 * `topPadding` 是那行文字的**上边距像素值**（搬家前的 14/8/4.dp 三档），
 * 因为 Checkbox 比文字高，文字要往下压一点才和方框对齐 —— 这是原样保留的视觉细节。
 */
@Composable
fun DickCheckRow(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    topPadding: Dp = 14.dp,
    iconSize: Dp = 14.dp,
) {
    Row(modifier) {
        Checkbox(checked = checked, onCheckedChange = onCheckedChange)
        IconText(label, Modifier.padding(top = topPadding), iconSize = iconSize)
    }
}
