package com.dick.app

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 选世界（多选 = 平行世界）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `WorldsDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[WorldsDialog]（在 Dialogs.kt 末尾），转调 [WorldsScreen]。
 */
/** 选世界（多<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌选=平行世界） */
@Composable
fun WorldsScreen(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val accent = deps.accent
    val worlds = vm.worlds
    var selectedWorlds by vm.selectedWorlds
    var currentWorld by deps.currentWorld
    var showWorlds by vm.showWorlds
    var showWorldEdit by vm.showWorldEdit
    var pendingDelete by vm.pendingDelete
    if (showWorlds) {
        AlertDialog(
            onDismissRequest = { showWorlds = false },
            title = { Text(I18n.t("dlg_worlds", "选择世界（多选=平行世界）")) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    for ((n, _) in worlds) {
                        Row {
                            Checkbox(checked = n in selectedWorlds, onCheckedChange = { ck ->
                                selectedWorlds = if (ck) selectedWorlds + n else selectedWorlds - n
                                if (currentWorld !in selectedWorlds) currentWorld = selectedWorlds.firstOrNull() ?: ""
                            })
                            Text(n, Modifier.padding(top = 14.dp))
                            if (n == currentWorld) Text("★", Modifier.padding(top = 14.dp), color = accent, fontSize = 12.sp)
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = { currentWorld = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("🚀", fontSize = 14.sp) }
                            TextButton(onClick = { showWorldEdit = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText(I18n.t("btn_edit", "✏️"), fontSize = 14.sp) }
                            TextButton(onClick = { pendingDelete = n to "world" }, modifier = Modifier.heightIn(min = 44.dp)) { Text(I18n.t("btn_delete", "删除"), color = theme.danger, fontSize = 12.sp) }
                        }
                    }
                }
            },
            confirmButton = {
                Row {
                    TextButton(onClick = { showWorldEdit = "" }) { IconText(I18n.t("btn_new_world", "新建世界"), fontSize = 12.sp, iconSize = 13.dp) }
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { showWorlds = false }) { Text("完成") }
                }
            },
        )
    }
}
