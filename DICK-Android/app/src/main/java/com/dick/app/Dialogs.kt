package com.dick.app

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import com.dick.core.ChatTree
import com.dick.core.MechanicsEngine

/**
 * Dialogs.kt —— 历史门面 + 还没搬走的屏（自 App.kt 迁出，全体认 ChatViewModel 协议）。
 *
 * 2026-11 UI 解耦之后，这个文件有**两种东西**，看函数就能分清：
 *   · 还写着完整实现的屏 —— 就是下一批要搬的（跑团 / 角色卡编辑 / 备份 / 世界卡…）；
 *   · 文件末尾「历史门面」区里那些只有一行转调的函数 —— 实现在 ui/screens/<feature>/。
 *
 * 规矩：
 *   · 新加一屏**不要**再往这里写，去 ui/screens/<feature>/ 建 {Screen,State,Actions}.kt，
 *     然后在 nav/Routes.kt 注册一行；
 *   · 门面里不许加逻辑（它只负责"老名字还能调通"）。
 */

/* =====================================================================================
 * 历史门面（兼容层）——这些名字还有人调，但里面已经没有人了。
 *
 * 2026-11 UI 解耦：每一屏的实现都在 ui/screens/<feature>/，App.kt 通过 nav/OverlayHost 调。
 * 这里保留同名函数只为两件事：
 *   ① 外部（老的调用点 / 第三方改过的分支）引用不会断；
 *   ② 让"哪些屏还在这个文件里"一眼可见 —— 没了，全都搬完了，只剩这一片门面。
 * 规矩：**不许在门面里加逻辑**。要改行为去 ui/screens/ 里改。
 *
 * | 门面 | 实现 |
 * | --- | --- |
 * | DeleteConfirmDialog | ui/screens/common/DeleteConfirmScreen.kt |
 * | CardFaceDialog | ui/screens/common/CardFaceScreen.kt |
 * | AvatarCropDialog | ui/screens/common/AvatarCropScreen.kt |
 * | EditMsgDialog | ui/screens/common/EditMsgScreen.kt |
 * | FolderMenu | ui/screens/common/FolderMenuScreen.kt |
 * | BranchesDialog | ui/screens/backup/BranchesScreen.kt |
 * | SaveSlotsDialog | ui/screens/backup/SaveSlotsScreen.kt |
 * | TrpgDialog | ui/screens/trpg/TrpgScreen.kt |
 * | RolesDialog / WorldsDialog / WorldEditDialog | ui/screens/library/ |
 * | RoleEditDialog / PersonaDialog | ui/screens/cardEdit/ |
 * | SettingsDialog / TimeScalePanel | ui/screens/settings/ |
 * | WorkshopDialog | ui/screens/workshop/ |
 * | LifeSpaceSettingsPanel | ui/screens/lifeSpace/ |
 * ===================================================================================== */

@Composable
fun DeleteConfirmDialog(vm: ChatViewModel, muted: Color, danger: Color,
                        onDeleteRole: (String) -> Unit, onDeleteWorld: (String) -> Unit) {
    DeleteConfirmScreen(vm, muted, danger, onDeleteRole, onDeleteWorld)
}

@Composable
fun CardFaceDialog(vm: ChatViewModel, muted: Color) {
    CardFaceScreen(vm, muted)
}

/** 分支树要 tree/mech/accent + 三个回调（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌先照原样传，收窄成 BranchesActions 是下一步）。 */
@Composable
fun BranchesDialog(
    vm: ChatViewModel,
    tree: ChatTree,
    mech: MechanicsEngine,
    accent: Color,
    saveTree: () -> Unit,
    refreshChain: () -> Unit,
    restoreOptions: (String?) -> Unit,
) {
    BranchesScreen(vm, tree, mech, accent, saveTree, refreshChain, restoreOptions)
}

@Composable
fun TimeScalePanel(vm: ChatViewModel, deps: DialogDeps) {
    TimeDialScreen(vm, deps)
}

@Composable
fun TrpgDialog(vm: ChatViewModel, deps: DialogDeps) {
    TrpgScreen(vm, deps)
}

@Composable
fun SaveSlotsDialog(vm: ChatViewModel, deps: DialogDeps, role: String, onClose: () -> Unit) {
    SaveSlotsScreen(vm, deps, role, onClose)
}

@Composable
fun RolesDialog(vm: ChatViewModel, deps: DialogDeps) {
    RolesScreen(vm, deps)
}

@Composable
fun RoleEditDialog(vm: ChatViewModel, deps: DialogDeps) {
    CardEditScreen(vm, deps)
}

@Composable
fun PersonaDialog(vm: ChatViewModel, deps: DialogDeps) {
    PersonaScreen(vm, deps)
}

@Composable
fun AvatarCropDialog(vm: ChatViewModel, deps: DialogDeps) {
    AvatarCropScreen(vm, deps)
}

@Composable
fun WorldsDialog(vm: ChatViewModel, deps: DialogDeps) {
    WorldsScreen(vm, deps)
}

@Composable
fun WorldEditDialog(vm: ChatViewModel, deps: DialogDeps) {
    WorldEditScreen(vm, deps)
}

@Composable
fun EditMsgDialog(vm: ChatViewModel, deps: DialogDeps) {
    EditMsgScreen(vm, deps)
}

@Composable
fun FolderMenu(vm: ChatViewModel, deps: DialogDeps) {
    FolderMenuScreen(vm, deps)
}

@Composable
fun SettingsDialog(vm: ChatViewModel, deps: DialogDeps) {
    SettingsScreen(vm, deps.settingsActions())
}

@Composable
fun WorkshopDialog(vm: ChatViewModel, deps: DialogDeps) {
    WorkshopScreen(vm, deps.workshopActions())
}

@Composable
fun LifeSpaceSettingsPanel(vm: ChatViewModel, deps: DialogDeps) {
    LifeSpaceScreen(vm, deps)
}
