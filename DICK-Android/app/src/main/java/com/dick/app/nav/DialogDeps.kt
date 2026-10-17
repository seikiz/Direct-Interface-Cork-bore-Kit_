package com.dick.app

import android.content.Context
import android.net.Uri
import androidx.activity.compose.ManagedActivityResultLauncher
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import com.dick.core.ChatEngine
import com.dick.core.ChatTree
import com.dick.core.J
import com.dick.core.MechanicsEngine
import com.dick.plugins.DicePlugin
import com.dick.plugins.FinancialPlugin
import com.dick.plugins.GalgamePlugin
import com.dick.plugins.JpPlugin
import com.dick.plugins.MemoryPlugin
import com.dick.plugins.PluginRegistry
import com.dick.plugins.SearchPlugin
import com.dick.plugins.SwipePlugin
import com.dick.plugins.UiPlugin
import java.io.File
import kotlinx.coroutines.CoroutineScope

/**
 * DialogDeps —— App() 与各屏之间的**接线契约**（启动器 / 回调 / 只读对象）。
 *
 * 从 Dialogs.kt 搬到 nav 层：它是「路由 + 依赖注入」，不是某一屏的东西。
 * 下一步：各屏已经陆续有自己的 `<Feature>Actions`（settings/workshop 已完成），
 * 这里每少一个字段，App() 与屏之间的接触面就小一格。
 */
/**
 * DialogDeps —— 从 App() 闭包里抽出来、对话框需要的"环境依赖"。
 * 对话框只认 vm（状态协议）+ deps（对象/回调/颜色/偏好），不再散落 App 闭包。
 * 新对话框 = 在 Dialogs.kt 新写 @Composable fun XxxDialog(vm, deps, ...)。
 */
class DialogDeps(
    val context: Context,
    val scope: CoroutineScope,
    val engine: ChatEngine,
    val registry: PluginRegistry,
    val tree: ChatTree,
    val dice: DicePlugin,
    val memory: MemoryPlugin,
    val swipe: SwipePlugin,
    val gal: GalgamePlugin,
    val mech: MechanicsEngine,
    val search: SearchPlugin,
    val financial: FinancialPlugin,
    val jp: JpPlugin,
    val uiPlugin: UiPlugin,
    val theme: ThemeSpec,
    val accent: Color,
    // rememberSaveable <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌应用级偏好（转屏/进程重建保留）
    val themeIdx: MutableState<Int>,
    val accentIdx: MutableState<Int>,
    val presetIdx: MutableState<Int>,
    val currentWorld: MutableState<String>,
    val devMode: MutableState<Boolean>,
    val humanize: MutableState<Boolean>,
    val styleGuard: MutableState<Boolean>,
    val styleGuardLong: MutableState<Boolean>,
    val autoTurn: MutableState<Boolean>,
    val language: MutableState<String>,
    // 启动器（在 App() 创建，回调闭包 App 状态，故不走 VM）
    val importCardLauncher: ManagedActivityResultLauncher<Array<String>, Uri?>,
    val avatarPicker: ManagedActivityResultLauncher<String, Uri?>,
    val appIconPicker: ManagedActivityResultLauncher<String, Uri?>,
    val wallpaperPicker: ManagedActivityResultLauncher<String, Uri?>,
    val clearWallpaper: () -> Unit,
    val exportCardLauncher: ManagedActivityResultLauncher<String, Uri?>,
    val wsExportLauncher: ManagedActivityResultLauncher<String, Uri?>,
    // App 闭包里的回调函数
    val saveConfig: () -> Unit,
    val saveTree: () -> Unit,
    val refreshChain: () -> Unit,
    val saveGlobalRegex: (String) -> Unit,
    val reloadMech: () -> Unit,
    val reloadRolesFromDisk: () -> Unit,
    val reloadWorldsFromDisk: () -> Unit,
    val personaFields: () -> Map<String, String>,
    val personaDisplayName: () -> String,
    val userDisplayName: () -> String,
    // 生活层/空间层要读"当前角色卡 / 当前世界卡"（年代、地图、口味、忌口都在卡里）
    val roleJsonFor: (String?) -> String?,
    val worldJsonFor: () -> String?,
    val treeFileFor: () -> File,
    val stateFileFor: () -> File,
    val listRoleSaves: (String) -> List<J.Obj>,
    val createRoleSave: (String, String) -> Unit,
    val saveToRoleSlot: (String, String) -> Unit,
    val loadRoleSlot: (String, String) -> Unit,
    val deleteRoleSlot: (String, String) -> Unit,
    val renameRoleSlot: (String, String, String) -> Unit,
    val mechConfig: () -> J.Obj?,
    val mechBattleConfig: () -> J.Obj?,
    val playerBattleConfig: () -> J.Obj?,
    val activeCardFace: () -> String,
    val editMessage: (ChatMsg, String) -> Unit,
    val toggleRoleUnlock: (String) -> Unit,
    val wsRefreshLocal: () -> Unit,
    val wsLoadOnline: () -> Unit,
    val wsSearchOnline: () -> Unit,
    val wsLoadPlugins: () -> Unit,
    val wsInstallPlugin: (String) -> Unit,
    val wsDownloadSelected: () -> Unit,
    val wsLikeSelected: () -> Unit,
    val wsDeleteSelected: () -> Unit,
    val wsUploadLocal: () -> Unit,
)
