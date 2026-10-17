package com.dick.app

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.unit.sp

/**
 * 编辑消息（改一句话就重发）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `EditMsgDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[EditMsgDialog]（在 Dialogs.kt 末尾），转调 [EditMsgScreen]。
 */
/** 编<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌辑消息 */
@Composable
fun EditMsgScreen(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val editMessage = deps.editMessage
    var editMsgTarget by vm.editMsgTarget
    var editMsgText by vm.editMsgText
    if (editMsgTarget != null) {
        val target = editMsgTarget!!
        AlertDialog(
            onDismissRequest = { editMsgTarget = null },
            title = { Text(I18n.t("edit_title", "编辑消息")) },
            text = {
                Column {
                    Text(
                        if (target.role == "你") I18n.t("edit_user_hint", "编辑后重新生成回复（保留旧分支）")
                        else I18n.t("edit_ai_hint", "原地修改这条 AI 回复"),
                        fontSize = 11.sp,
                        color = theme.muted,
                    )
                    OutlinedTextField(value = editMsgText, onValueChange = { editMsgText = it }, minLines = 3)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val t = target
                    editMsgTarget = null
                    editMessage(t, editMsgText.trim())
                }) { Text(I18n.t("btn_save", "保存")) }
            },
            dismissButton = { TextButton(onClick = { editMsgTarget = null }) { Text(I18n.t("btn_cancel", "取消")) } },
        )
    }
}
