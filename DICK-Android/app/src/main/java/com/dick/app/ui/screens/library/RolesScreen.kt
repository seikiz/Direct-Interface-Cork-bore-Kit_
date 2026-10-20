package com.dick.app

import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
 * 2026-12 用户反馈（截图）：行首那个勾选方框是早期留下的多余件 —— 整张卡片点一下就该选中/取消。
 * 改法（替换优先，整段重写，不就地贴补丁）：
 *   · 那 20 行状态重载逻辑从 `onCheckedChange` 里搬成局部函数 [toggleRole]（**行为逐字不变**：
 *     同样的调用顺序、同样的 `scope.launch(Dispatchers.Main)`、同样的异常吞法）；
 *   · 删掉 Material 的 `Checkbox`，整张卡片 `clickable { toggleRole(n) }`；
 *   · 选中态靠 `2.dp` + `palette.accent` 描边 + 行首 `check_circle` 图标（未选中 `1.dp` + `line`）。
 * [DickCheckRow]（ui/components/Cards.kt）保留 —— 设置页还有 6 处在用；只是这一屏彻底不再引用
 * `Checkbox(`（`tests/test_android_role_picker.py` 盯着这条）。
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

    /**
     * 选中 / 取消一个角色。
     *
     * 这 20 行原来直接写在 `Checkbox(onCheckedChange = { ck -> ... })` 里 —— "UI 事件里混业务"是
     * 典型的屎山形状（换一种选中方式就得把这段抄一遍）。现在只搬不改：调用顺序、所在线程、
     * 异常吞法（`TreeStore.load` 的 try/catch）与搬家前**逐字一致**，
     * `tests/test_android_role_picker.py` 把关键调用一个个钉住。
     */
    fun toggleRole(n: String) {
        saveTree()
        selectedRoles = if (n in selectedRoles) selectedRoles - n else selectedRoles + n
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
    }

    if (vm.showRoles.value) {
    DickDialog(
        onDismissRequest = { vm.showRoles.value = false },
        title = { Text(I18n.t("dlg_roles", "选择角色（多选=群聊）")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                for ((n, _) in roles) {
                    // 选中态只由这一处算：描边粗细 / 颜色 / 行首勾都跟着它（没有第二份布尔副本）
                    val on = n in selectedRoles
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .padding(vertical = 10.dp)
                            // 整张卡片可点：选中与取消都走同一个函数（方框已经删了）
                            .clickable { toggleRole(n) }
                            .border(
                                if (on) 2.dp else 1.dp,
                                if (on) theme.palette.accent else theme.line,
                                RoundedCornerShape(10.dp),
                            )
                            .padding(horizontal = 8.dp, vertical = 4.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            // 选中指示：只在选中时出现（未选中不占位，避免行首忽宽忽窄）
                            if (on) {
                                IconText("", fontSize = 14.sp, color = theme.palette.accent, icon = "check_circle")
                            }
                            Avatar(n, avatarCache)
                            Text(n, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.weight(1f))
                            if (roleUnlocked[n] == true) {
                                IconText("", fontSize = 13.sp, color = theme.danger, icon = "local_fire_department")
                            }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(start = 4.dp)) {
                            TextButton(onClick = { avatarTarget = n; avatarPicker.launch("image/*") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("头像", fontSize = 12.sp, icon = "image") }
                            TextButton(onClick = { toggleRoleUnlock(n) }, modifier = Modifier.heightIn(min = 44.dp)) {
                                IconText(if (roleUnlocked[n] == true) "破甲·开" else "破甲", fontSize = 12.sp, color = if (roleUnlocked[n] == true) theme.danger else Color.Unspecified, icon = "local_fire_department")
                            }
                            TextButton(onClick = { roleEditName = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("编辑", fontSize = 12.sp, icon = "edit") }
                            TextButton(onClick = { saveRole = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("档", fontSize = 12.sp, icon = "save") }
                            TextButton(onClick = { exportTarget = n to "json"; exportCardLauncher.launch("application/json") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("JSON", fontSize = 12.sp, icon = "download") }
                            TextButton(onClick = { exportTarget = n to "png"; exportCardLauncher.launch("image/png") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("PNG", fontSize = 12.sp, icon = "upload") }
                            TextButton(onClick = { pendingDelete = n to "role" }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("", color = theme.danger, fontSize = 14.sp, icon = "delete") }
                        }
                    }
                }
            }
        },
        confirmButton = {
            Row {
                TextButton(onClick = {
                    importCardLauncher.launch(arrayOf("image/png", "image/webp", "application/json"))
                }) { IconText(I18n.t("btn_import_card", "导入角色卡"), fontSize = 12.sp, icon = "inbox") }
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
