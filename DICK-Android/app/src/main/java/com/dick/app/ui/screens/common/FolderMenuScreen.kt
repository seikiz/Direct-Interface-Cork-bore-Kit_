package com.dick.app

import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.ChatTree
import com.dick.core.TreeStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * 顶栏  文件夹下拉菜单：人物卡 + 世界卡 直接勾选。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `FolderMenu` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[FolderMenu]（在 Dialogs.kt 末尾），转调 [FolderMenuScreen]。
 */
/** 顶栏  文件夹 = 下拉菜单：人物卡 + 世界卡 都在这里直接勾选（编辑/导入/导出/删除留在抽屉） */
@Composable
fun FolderMenuScreen(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val accent = deps.accent
    val scope = deps.scope
    val tree = deps.tree
    val mech = deps.mech
    val gal = deps.gal
    val saveTree = deps.saveTree
    val saveConfig = deps.saveConfig
    val refreshChain = deps.refreshChain
    val treeFileFor = deps.treeFileFor
    val stateFileFor = deps.stateFileFor
    val mechConfig = deps.mechConfig
    val mechBattleConfig = deps.mechBattleConfig
    val playerBattleConfig = deps.playerBattleConfig
    val roles = vm.roles
    val worlds = vm.worlds
    var selectedRoles by vm.selectedRoles
    var selectedWorlds by vm.selectedWorlds
    var currentWorld by deps.currentWorld
    var expanded by remember { mutableStateOf(false) }

    fun toggleRole(n: String) {
        val ck = n !in selectedRoles
        saveTree()
        selectedRoles = if (ck) selectedRoles + n else selectedRoles - n
        saveConfig()
        gal.clearChoices()  // 切换角色 = 新会话，旧选项作废
        // 切换到新角<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌色的聊天树
        scope.launch(Dispatchers.Main) {
            val tf = treeFileFor()
            tree.loadData(if (tf.exists()) {
                try { TreeStore.load(tf).historyTree } catch (_: Exception) { ChatTree().toData() }
            } else ChatTree().toData())
            tree.fixLeaf()
            mech.stateFile = stateFileFor()  // 换角色 → 换第三个文件夹状态文件
            mech.resetConfigTracking()  // 换卡 = 新配置源：不触发字段级对齐（保留新角色累加）
            mech.reload(mechConfig(), tree, reset = true)
            mech.battleCfg = mechBattleConfig()
            mech.playerCfg = playerBattleConfig()
            mech.initBattle()
            refreshChain()
        }
        expanded = false
    }

    fun toggleWorld(n: String) {
        val ck = n !in selectedWorlds
        selectedWorlds = if (ck) selectedWorlds + n else selectedWorlds - n
        if (currentWorld !in selectedWorlds) currentWorld = selectedWorlds.firstOrNull() ?: ""
        expanded = false
    }

    Box {
        TextButton(onClick = { expanded = true }) { IconText("", fontSize = 16.sp, icon = "folder") }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier.width(240.dp),
        ) {
            // 内容直接放 DropdownMenu 的 ColumnScope 里（它内部自带滚动），
            // 不要在外层再套 verticalScroll / 宽度高度——会触发测量递归 StackOverflow。
            IconText("人物卡（" + selectedRoles.size + "）", fontSize = 12.sp, color = theme.muted, iconSize = 13.dp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp), icon = "group")
            if (roles.isEmpty()) {
                DickEmptyState("（暂无 · 抽屉 → 角色 新建/导入）", fontSize = 11.sp,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 2.dp))
            }
            roles.forEach { (n, _) ->
                DropdownMenuItem(
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = n in selectedRoles, onCheckedChange = null)
                            Text(n, fontSize = 13.sp)
                        }
                    },
                    onClick = { toggleRole(n) },
                )
            }
            IconText("世界卡（" + selectedWorlds.size + "）", fontSize = 12.sp, color = theme.muted, iconSize = 13.dp, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp), icon = "public")
            if (worlds.isEmpty()) {
                DickEmptyState("（暂无 · 抽屉 → 世界 新建）", fontSize = 11.sp,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 2.dp))
            }
            worlds.forEach { (n, _) ->
                DropdownMenuItem(
                    text = {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = n in selectedWorlds, onCheckedChange = null)
                            Text(n, fontSize = 13.sp)
                            if (n == currentWorld) {
                                Spacer(Modifier.width(4.dp))
                                Text("★ 当前", fontSize = 11.sp, color = accent)
                            }
                        }
                    },
                    onClick = { toggleWorld(n) },
                )
            }
            Text("管理", fontSize = 11.sp, color = theme.muted, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
            DropdownMenuItem(
                text = { IconText("人物卡管理（编辑/导入/导出/删除）", fontSize = 12.sp, icon = "settings") },
                onClick = { expanded = false; vm.showRoles.value = true },
            )
            DropdownMenuItem(
                text = { IconText("世界卡管理（编辑/新建/删除）", fontSize = 12.sp, icon = "settings") },
                onClick = { expanded = false; vm.showWorlds.value = true },
            )
        }
    }
}
