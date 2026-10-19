package com.dick.app

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 删除确认（角色卡 / 世界卡）—— 二次确认弹窗。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `DeleteConfirmDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[DeleteConfirmDialog]（在 Dialogs.kt 末尾），转调 [DeleteConfirmScreen]。
 */
/** 删除确认<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（角色/世界） */
@Composable
fun DeleteConfirmScreen(
    vm: ChatViewModel,
    muted: Color,
    danger: Color,
    onDeleteRole: (String) -> Unit,
    onDeleteWorld: (String) -> Unit,
) {
    val pd = vm.pendingDelete.value ?: return
    val (name, kind) = pd
    val label = if (kind == "role") "角色卡「$name」" else "世界卡「$name」"
    DickDialog(
        onDismissRequest = { vm.pendingDelete.value = null },
        title = { IconText("确认删除", icon = "warning") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("确定删除$label 吗？")
                Spacer(Modifier.height(6.dp))
                Text(
                    if (kind == "role") "(会一并删除它的聊天记录，不可恢复。)" else "(会一并删除它的世界书内容，不可恢复。)",
                    fontSize = 12.sp, color = muted,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = {
                if (kind == "role") onDeleteRole(name) else onDeleteWorld(name)
                vm.pendingDelete.value = null
            }) { IconText("删除", color = danger, iconSize = 15.dp, icon = "delete") }
        },
        dismissButton = { TextButton(onClick = { vm.pendingDelete.value = null }) { Text("取消") } },
    )
}
