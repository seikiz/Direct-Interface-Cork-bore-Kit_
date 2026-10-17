package com.dick.app

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 空状态 / 加载态（同一类"这里暂时没内容 / 正在等"的提示）。
 *
 * 为什么值得单独两个函数：这两种提示在三个屏里出现过（工坊、文件夹菜单、世界卡列表），
 * 每次都是"一行灰色小字 + 行首图标"。散着写的结果就是字号 11/12/13 各来一遍、
 * 颜色在 muted/dim 之间随机 —— 于是同一个 App 里"没内容"长三种样子。
 *
 * 契约：只吃参数（文案 + 尺寸），不读 vm、不发请求。文案由调用点走 I18n.t。
 * 两者观感刻意做得**一样**（都是 muted 一行）：区别只在语义，
 * 加载态以后要加转圈/骨架屏时，改这里一个地方就全站生效。
 */

/** 空状态：例如"插件市场暂<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌无内容（工坊服务器未启动）"。 */
@Composable
fun DickEmptyState(
    text: String,
    modifier: Modifier = Modifier,
    fontSize: TextUnit = 12.sp,
    iconSize: Dp = 13.dp,
) {
    IconText(text, modifier = modifier, fontSize = fontSize, color = DickTone.Muted.color(), iconSize = iconSize)
}

/** 加载态：例如"自动连接中…"。现在与空状态同形，语义不同（以后加动画只动这里）。 */
@Composable
fun DickLoading(
    text: String,
    modifier: Modifier = Modifier,
    fontSize: TextUnit = 12.sp,
    iconSize: Dp = 13.dp,
) {
    IconText(text, modifier = modifier, fontSize = fontSize, color = DickTone.Muted.color(), iconSize = iconSize)
}
