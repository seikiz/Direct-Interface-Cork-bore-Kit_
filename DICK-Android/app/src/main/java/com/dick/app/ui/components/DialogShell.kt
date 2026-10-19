package com.dick.app

import androidx.compose.material3.AlertDialog
import androidx.compose.runtime.Composable

/**
 * 弹窗壳（DICK 的唯一弹窗外框）。
 *
 * 为什么要有壳：安卓端的"屏"现在全是弹窗（设置/工坊/跑团/备份…），
 * 如果每屏各写一遍 `AlertDialog(onDismissRequest, title, text, confirmButton, dismissButton)`，
 * 那"统一改弹窗圆角/背景/最大宽度"就成了 14 处改动。
 *
 * 契约：
 *   · 只转发五个槽位（dismiss / title / text / confirm / dismiss button）；
 *   · **颜色全部显式取自令牌**（2026-12 改）：绝对不能"其余参数用 Material3 默认"——
 *     AlertDialog 的底色取的是 `surfaceContainerHigh`，一旦这段组合落在 `DickTheme { }` 之外，
 *     那个槽位就没被映射，于是回落到 M3 默认的淡紫（深色主题下整片白，用户截图那次）；
 *     文字色同理，会落到 `LocalContentColor` 的**纯黑**默认值 → 深色底压黑字。
 *     现在四个颜色槽位都指到 LocalDickPalette：改配色只需改 design/tokens.json。
 *   · 不持有状态：开关由屏自己（vm.showXxx）决定，壳不 remember 任何东西。
 */
@Composable
fun DickDialog(
    onDismissRequest: () -> Unit,
    title: (@Composable () -> Unit)? = null,
    text: @Composable () -> Unit,
    confirmButton: @Composable () -> Unit,
    dismissButton: @Composable (() -> Unit)? = null,
) {
    val p = LocalDickPalette.current
    AlertDialog(
        onDismissRequest = onDismissRequest,
        title = title,
        text = text,
        confirmButton = confirmButton,
        dismissButton = dismissButton,
        // 容器用 surface_2（比页面底高一档，弹窗才"浮"得起来）；字一律用正文令牌。
        containerColor = p.surface2,
        titleContentColor = p.text,
        textContentColor = p.text,
        iconContentColor = p.textSub,
    )
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌