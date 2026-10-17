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
 *   · 只转发五个槽位（dismiss / title / text / confirm / dismiss button），
 *     其余参数一律用 Material3 默认 —— 所以换壳这一步**观感零变化**；
 *   · 不持有状态：开关由屏自己（vm.showXxx）决定，壳不 remember 任何东西。
 */
@Composable
fun DickDialog(
    onDismissRequest: () -> Unit,
    title: @Composable () -> Unit,
    text: @Composable () -> Unit,
    confirmButton: @Composable () -> Unit,
    dismissButton: @Composable (() -> Unit)? = null,
) {
    AlertDialog(
        onDismissRequest = onDismissRequest,
        title = title,
        text = text,
        confirmButton = confirmButton,
        dismissButton = dismissButton,
    )
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌