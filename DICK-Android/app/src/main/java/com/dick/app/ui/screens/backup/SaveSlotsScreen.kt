package com.dick.app

import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 角色卡·多存档（新存档 / 覆盖 / 读档 / 重命名 / 删除）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `SaveSlotsDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[SaveSlotsDialog]（在 Dialogs.kt 末尾），转调 [SaveSlotsScreen]。
 */
/** 角色卡·多存档：存档点管理（新存档 / <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌覆盖保存 / 读档 / 重命名 / 删除） */
@Composable
fun SaveSlotsScreen(vm: ChatViewModel, deps: DialogDeps, role: String, onClose: () -> Unit) {
    val theme = deps.theme
    var tick by remember { mutableStateOf(0) }
    var newLabel by remember { mutableStateOf("") }
    var renameSlot by remember { mutableStateOf<String?>(null) }
    var renameText by remember { mutableStateOf("") }
    val saves = remember(role, tick) { deps.listRoleSaves(role) }
    DickDialog(
        onDismissRequest = onClose,
        title = { IconText("存档 · " + role, icon = "save") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (renameSlot != null) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        OutlinedTextField(value = renameText, onValueChange = { renameText = it },
                            singleLine = true, modifier = Modifier.weight(1f).padding(end = 8.dp))
                        TextButton(onClick = {
                            val rs = renameSlot; if (rs != null) deps.renameRoleSlot(role, rs, renameText)
                            renameSlot = null; renameText = ""; tick++
                        }) { IconText("重命名", fontSize = 13.sp) }
                    }
                    Spacer(Modifier.height(6.dp))
                }
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                    OutlinedTextField(value = newLabel, onValueChange = { newLabel = it },
                        placeholder = { Text("存档名（可留空，自动编号）", fontSize = 12.sp) },
                        singleLine = true, modifier = Modifier.weight(1f).padding(end = 8.dp))
                    TextButton(onClick = { deps.createRoleSave(role, newLabel); newLabel = ""; tick++ }) { IconText("新存档", fontSize = 13.sp, icon = "note") }
                }
                Spacer(Modifier.height(8.dp))
                if (saves.isEmpty()) {
                    Text("还没有存档点。继续聊天后点「新存档」即把当前进度固化成一个存档点。", color = theme.muted, fontSize = 13.sp)
                } else {
                    saves.forEach { s ->
                        val id = s.fields["id"]?.str() ?: return@forEach
                        val label = s.fields["label"]?.str() ?: "未命名存档"
                        val prog = s.fields["progress"]?.int() ?: 0
                        val ts = s.fields["updated_ts"]?.str() ?: ""
                        Column(
                            Modifier.fillMaxWidth().padding(vertical = 6.dp)
                                .border(1.dp, theme.line, RoundedCornerShape(10.dp))
                                .padding(horizontal = 10.dp, vertical = 6.dp)
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(label, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                Row(horizontalArrangement = Arrangement.spacedBy(2.dp),
                                    modifier = Modifier.horizontalScroll(rememberScrollState())) {
                                    TextButton(onClick = { deps.loadRoleSlot(role, id); onClose() }, modifier = Modifier.heightIn(min = 40.dp)) { IconText("读档", fontSize = 12.sp, icon = "folder") }
                                    TextButton(onClick = { deps.saveToRoleSlot(role, id); tick++ }, modifier = Modifier.heightIn(min = 40.dp)) { IconText("覆盖", fontSize = 12.sp, icon = "save") }
                                    TextButton(onClick = { renameSlot = id; renameText = label; tick++ }, modifier = Modifier.heightIn(min = 40.dp)) { IconText("", fontSize = 12.sp, icon = "edit") }
                                    TextButton(onClick = { deps.deleteRoleSlot(role, id); tick++ }, modifier = Modifier.heightIn(min = 40.dp)) { IconText("", fontSize = 13.sp, color = theme.danger, icon = "delete") }
                                }
                            }
                            Text("$prog 条对话 · $ts", color = theme.muted, fontSize = 11.sp)
                        }
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = onClose) { Text(I18n.t("btn_done", "关闭")) } },
    )
}
