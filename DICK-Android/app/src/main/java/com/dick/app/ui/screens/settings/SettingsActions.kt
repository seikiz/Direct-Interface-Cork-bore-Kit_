package com.dick.app

import android.content.Context
import android.net.Uri
import androidx.activity.compose.ManagedActivityResultLauncher
import androidx.compose.ui.graphics.Color
import com.dick.core.ChatEngine
import com.dick.plugins.GalgamePlugin
import com.dick.plugins.PluginRegistry
import com.dick.plugins.UiPlugin

/**
 * SettingsActions —— 设置屏的**对外依赖**（一组回调 + 只读对象）。
 *
 * 为什么不再直接吃 DialogDeps：DialogDeps 是"整个 App 的抽屉"（60 多个字段），
 * 任何一屏拿到它就能摸到别的屏要用的东西 —— 那等于没解耦。
 * 屏只声明自己真正需要的，App 那边多一个字段也不会悄悄流进来。
 *
 * 契约：
 *   · 只读对象（engine/registry/gal/uiPlugin/theme/accent）+ 动作回调（saveConfig…）；
 *   · 屏**不改**这些对象的状态以外的东西，回调把"要落盘/要开系统相册"这类事推给上层；
 *   · 这个类自己不含状态，构造一次即可（无需 remember）。
 */
class SettingsActions(
    val context: Context,
    val theme: ThemeSpec,
    val accent: Color,
    val engine: ChatEngine,
    val registry: PluginRegistry,
    val gal: GalgamePlugin,
    val uiPlugin: UiPlugin,
    val appIconPicker: ManagedActivityResultLauncher<String, Uri?>,
    val wallpaperPicker: ManagedActivityResultLauncher<String, Uri?>,
    val clearWallpaper: () -> Unit,
    val personaDisplayName: () -> String,
    val saveConfig: () -> Unit,
    val saveGlobalRegex: (String) -> Unit,
)

/** 兼容层用：把老的 DialogDep<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌s 投影成"设置屏真正需要的这一小份"。 */
fun DialogDeps.settingsActions(): SettingsActions = SettingsActions(
    context = context,
    theme = theme,
    accent = accent,
    engine = engine,
    registry = registry,
    gal = gal,
    uiPlugin = uiPlugin,
    appIconPicker = appIconPicker,
    wallpaperPicker = wallpaperPicker,
    clearWallpaper = clearWallpaper,
    personaDisplayName = personaDisplayName,
    saveConfig = saveConfig,
    saveGlobalRegex = saveGlobalRegex,
)
