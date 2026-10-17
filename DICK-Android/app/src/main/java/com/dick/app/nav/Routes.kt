package com.dick.app

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/**
 * nav/Routes —— 屏的注册与跳转（安卓侧对应网页的 `web/js/router.js`）。
 *
 * 现状：这一版**没有引入导航库**，屏与屏之间的关系是"叠加式弹窗"，
 * 由 `ChatViewModel` 上的 `showXxx` 开关决定谁在屏幕上（开关就是路由状态）。
 * 所以这里不发明新的路由机制，只做三件事：
 *   ① 把"有哪些 overlay"和"谁先谁后"集中到一行一个（顺序 = 叠放顺序，改顺序就是改观感）；
 *   ② App.kt 从这里之后不再认识任何一个具体屏 —— 它只调 OverlayHost()；
 *   ③ 每条后面写清"这一屏搬出去了没有"，让下一批搬迁有个唯一的口径。
 *
 * 硬边界：
 *   · 这里**不写业务**，只做转调（参数从 App() 的 deps 里来，不再是各屏自己去抓）；
 *   · 屏内部之间不许互相调用；要跨屏就改 `vm` 上的开关或回调（见 ChatViewModel）。
 *   · 新增一屏 = 这里加一行 + `vm` 加一个开关；**别在 App.kt 里直接插一个 Dialog**。
 */
object Routes {
    /** 设置（API 配置 / 主题 / 语言 / 插件开关）—— 已搬到 ui/screens/settings/ */
    const val SETTINGS = "settings"

    /**  API 教程面板 —— 已搬到 ui/screens/api/（2026-11） */
    const val API_GUIDE = "apiGuide"

    /** 时间流速表盘（独立面板，不塞在设置里） */
    const val TIME_DIAL = "timeDial"

    /** 生活 / 空间 / 世界卡库 */
    const val LIFE_SPACE = "lifeSpace"

    /** 跑团（局域网房间） */
    const val TRPG = "trpg"

    /** 卡面查看 */
    const val CARD_FACE = "cardFace"

    /** 人物卡管理 */
    const val ROLES = "roles"

    /** 删除确认（角色/世界卡） */
    const val DELETE_CONFIRM = "deleteConfirm"

    /** 角色卡编辑 */
    const val CARD_EDIT = "cardEdit"

    /** 玩家角色卡 */
    const val PERSONA = "persona"

    /** 头像裁剪 */
    const val AVATAR_CROP = "avatarCrop"

    /** 世界卡管理 */
    const val WORLDS = "worlds"

    /** 世界卡编辑 */
    const val WORLD_EDIT = "worldEdit"

    /** 编辑消息 */
    const val EDIT_MSG = "editMsg"

    /** 创意工坊（本地 / 在线 / 插件）—— 已搬到 ui/screens/workshop/ */
    const val WORKSHOP = "workshop"

    /** 回档（分支树） */
    const val BRANCHES = "branches"
}

/**
 * 所有 overlay 的统一挂载点：一次性按固定顺序转调。
 *
 * 为什么集中：搬家前 App() 末尾是 14 行平铺的 `XxxDialog(vm, deps)`，
 * 谁都能在那儿顺手插一行 —— 于是"屏与屏互相点名"就一直长不回去。
 * 现在 App.kt 只认 OverlayHost 一个名字，具体有哪些屏、什么顺序，只在 Routes 这一处。
 */
@Composable
fun OverlayHost(
    vm: ChatViewModel,
    deps: DialogDeps,
    muted: Color,
    danger: Color,
    onDeleteRole: (String) -> Unit,
    onDeleteWorld: (String) -> Unit,
) {
    // 顺序 = 叠放顺序（后调的盖在前面的上面<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌）。与搬家前的调用顺序逐行对应，别重排。
    SettingsDialog(vm, deps)              // Routes.SETTINGS      → ui/screens/settings/
    ApiGuideDialog(vm)                    // Routes.API_GUIDE     → ui/screens/api/（只读，只吃 vm）
    TimeScalePanel(vm, deps)              // Routes.TIME_DIAL     · 自托管，读 vm.showTimeDial
    LifeSpaceSettingsPanel(vm, deps)      // Routes.LIFE_SPACE    · 自托管，读 vm.showLifeSpace
    TrpgDialog(vm, deps)                  // Routes.TRPG
    CardFaceDialog(vm, muted)             // Routes.CARD_FACE
    RolesDialog(vm, deps)                 // Routes.ROLES
    DeleteConfirmDialog(vm, muted, danger, onDeleteRole, onDeleteWorld)  // Routes.DELETE_CONFIRM
    RoleEditDialog(vm, deps)              // Routes.CARD_EDIT
    PersonaDialog(vm, deps)               // Routes.PERSONA
    AvatarCropDialog(vm, deps)            // Routes.AVATAR_CROP
    WorldsDialog(vm, deps)                // Routes.WORLDS
    WorldEditDialog(vm, deps)             // Routes.WORLD_EDIT
    EditMsgDialog(vm, deps)               // Routes.EDIT_MSG
    WorkshopDialog(vm, deps)              // Routes.WORKSHOP      → ui/screens/workshop/
    // 回档：分支树要用 tree/mech/accent + 三个回调，先直接从 deps 投影（下一步可以收成 BranchesActions）
    BranchesDialog(
        vm, deps.tree, deps.mech, deps.accent,
        { deps.saveTree() }, { deps.refreshChain() }, { deps.gal.restoreOptionsFromNode(it) },
    )
}
