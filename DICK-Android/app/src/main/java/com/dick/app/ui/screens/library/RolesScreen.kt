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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.ChatTree
import com.dick.core.TreeStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * 人物卡管理（列表 · 选中 · 编辑/导入/导出/删除入口）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `RolesDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[RolesDialog]（在 Dialogs.kt 末尾），转调 [RolesScreen]。
 */
@Composable
fun RolesScreen(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val scope = deps.scope
    val tree = deps.tree
    val mech = deps.mech
    val gal = deps.gal
    val roles = vm.roles
    val saveTree = deps.saveTree
    val saveConfig = deps.saveConfig
    val refreshChain = deps.refreshChain
    val treeFileFor = deps.treeFileFor
    val stateFileFor = deps.stateFileFor
    val mechConfig = deps.mechConfig
    val mechBattleConfig = deps.mechBattleConfig
    val playerBattleConfig = deps.playerBattleConfig
    val toggleRoleUnlock = deps.toggleRoleUnlock
    val avatarPicker = deps.avatarPicker
    val importCardLauncher = deps.importCardLauncher
    val exportCardLauncher = deps.exportCardLauncher
    val avatarCache = vm.avatarCache
    val roleUnlocked = vm.roleUnlocked
    var selectedRoles by vm.selectedRoles
    var avatarTarget by vm.avatarTarget
    var exportTarget by vm.exportTarget
    var roleEditName by vm.roleEditName
    var pendingDelete by vm.pendingDelete
    var saveRole by remember { mutableStateOf<String?>(null) }
    if (vm.showRoles.value) {
    AlertDialog(
        onDismissRequest = { vm.showRoles.value = false },
        title = { Text(I18n.t("dlg_roles", "选择角色（多选=群聊）")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                for ((n, _) in roles) {
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .padding(vertical = 10.dp)
                            .border(1.dp, theme.line, RoundedCornerShape(10.dp))
                            .padding(horizontal = 8.dp, vertical = 4.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = n in selectedRoles, onCheckedChange = { ck ->
                                saveTree()
                                selectedRoles = if (ck) selectedRoles + n else selectedRoles - n
                                saveConfig()
                                gal.clearChoices()
                                scope.launch(Dispatchers.Main) {
                                    val tf = treeFileFor()
                                    tree.loadData(if (tf.exists()) {
                                        try { TreeStore.load(tf).historyTree } catch (_: Exception) { ChatTree().toData() }
                                    } else ChatTree().toData())
                                    tree.fixLeaf()
                                    mech.stateFile = stateFileFor()
                                    mech.resetConfigTracking()
                                    mech.reload(mechConfig(), tree, reset = true)
                                    mech.battleCfg = mechBattleConfig()
                                    mech.playerCfg = playerBattleConfig()
                                    mech.initBattle()
                                    refreshChain()
                                }
                            })
                            Avatar(n, avatarCache)
                            Text(n, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.weight(1f))
                            if (roleUnlocked[n] == true) {
                                IconText("🔥", fontSize = 13.sp, color = theme.danger)
                            }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(start = 4.dp)) {
                            TextButton(onClick = { avatarTarget = n; avatarPicker.launch("image/*") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("🖼️ 头像", fontSize = 12.sp) }
                            TextButton(onClick = { toggleRoleUnlock(n) }, modifier = Modifier.heightIn(min = 44.dp)) {
                                IconText(if (roleUnlocked[n] == true) "🔥 破甲·开" else "🔥 破甲", fontSize = 12.sp, color = if (roleUnlocked[n] == true) theme.danger else Color.Unspecified)
                            }
                            TextButton(onClick = { roleEditName = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("✏️ 编辑", fontSize = 12.sp) }
                            TextButton(onClick = { saveRole = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("💾 档", fontSize = 12.sp) }
                            TextButton(onClick = { exportTarget = n to "json"; exportCardLauncher.launch("application/json") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("⬇️ JSON", fontSize = 12.sp) }
                            TextButton(onClick = { exportTarget = n to "png"; exportCardLauncher.launch("image/png") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("📤 PNG", fontSize = 12.sp) }
                            TextButton(onClick = { pendingDelete = n to "role" }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("🗑️", color = theme.danger, fontSize = 14.sp) }
                        }
                    }
                }
            }
        },
        confirmButton = {
            Row {
                TextButton(onClick = {
                    importCardLauncher.launch(arrayOf("image/png", "image/webp", "application/json"))
                }) { IconText(I18n.t("btn_import_card", "📥 导入角色卡"), fontSize = 12.sp) }
                Spacer(Modifier.weight(1f))
                TextButton(onClick = { roleEditName = "" }) { IconText(I18n.t("btn_new_role", "新建角色"), iconSize = 15.dp) }
            }
        },
        dismissButton = { TextButton(onClick = { vm.showRoles.value = false }) { Text(I18n.t("btn_done", "完成")) } },
    )
    saveRole?.let { sr ->
        SaveSlotsDialog(vm, deps, sr, onClose = { saveRole = null })
    }
    }
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌