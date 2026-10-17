package com.dick.app

import android.net.Uri
import androidx.activity.compose.ManagedActivityResultLauncher
import kotlinx.coroutines.CoroutineScope

/**
 * WorkshopActions —— 工坊屏的**对外依赖**（一组回调 + 只读对象）。
 *
 * 与 SettingsActions 同一个理由：屏不再拿整个 DialogDeps（那是 App 的抽屉），
 * 只声明自己真正要调的那几个动作。工坊的活儿全是"重活"（扫目录 / 连服务器 / 下载 / 装插件），
 * 所以回调实现在 App() 那边，仍旧走 Lanes 与 io 线（本文件不碰线程）。
 */
class WorkshopActions(
    val theme: ThemeSpec,
    val scope: CoroutineScope,
    val importCardLauncher: ManagedActivityResultLauncher<Array<String>, Uri?>,
    val wsExportLauncher: ManagedActivityResultLauncher<String, Uri?>,
    val refreshLocal: () -> Unit,
    val loadOnline: () -> Unit,
    val searchOnline: () -> Unit,
    val loadPlugins: () -> Unit,
    val installPlugin: (String) -> Unit,
    val downloadSelected: () -> Unit,
    val likeSelected: () -> Unit,
    val deleteSelected: () -> Unit,
    val uploadLocal: () -> Unit,
    val reloadRolesFromDisk: () -> Unit,
    val reloadWorldsFromDisk: () -> Unit,
)

/** 兼容层用：把老的 DialogDep<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌s 投影成"工坊屏真正需要的这一小份"。 */
fun DialogDeps.workshopActions(): WorkshopActions = WorkshopActions(
    theme = theme,
    scope = scope,
    importCardLauncher = importCardLauncher,
    wsExportLauncher = wsExportLauncher,
    refreshLocal = wsRefreshLocal,
    loadOnline = wsLoadOnline,
    searchOnline = wsSearchOnline,
    loadPlugins = wsLoadPlugins,
    installPlugin = wsInstallPlugin,
    downloadSelected = wsDownloadSelected,
    likeSelected = wsLikeSelected,
    deleteSelected = wsDeleteSelected,
    uploadLocal = wsUploadLocal,
    reloadRolesFromDisk = reloadRolesFromDisk,
    reloadWorldsFromDisk = reloadWorldsFromDisk,
)
