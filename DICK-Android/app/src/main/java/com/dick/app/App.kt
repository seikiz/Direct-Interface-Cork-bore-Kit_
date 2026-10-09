package com.dick.app

import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import android.speech.tts.TextToSpeech
import android.webkit.WebView
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AlertDialogDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.viewmodel.compose.viewModel
import com.dick.core.AppConfig
import com.dick.core.AppEnv
import com.dick.core.ChatBridge
import com.dick.core.ChatEngine
import com.dick.core.ChatTree
import com.dick.core.EndingJudge
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.Lanes
import com.dick.core.MessageNode
import com.dick.core.MechanicsEngine
import com.dick.core.TimeScale
import com.dick.core.RegexEngine
import com.dick.core.RoleSaves
import com.dick.core.SaveFile
import com.dick.core.SaveSlot
import com.dick.core.SpaceCore
import com.dick.core.StyleGuard
import com.dick.core.TextGuard
import com.dick.core.TreeData
import com.dick.core.TreeStore
import com.dick.core.WorldBook
import com.dick.core.WorldData
import com.dick.core.WorldEntry
import com.dick.core.WorldPacks
import com.dick.core.Workshop
import com.dick.plugins.DicePlugin
import com.dick.plugins.FinancialPlugin
import com.dick.plugins.GalgamePlugin
import com.dick.plugins.JpPlugin
import com.dick.plugins.LifeSpacePlugin
import com.dick.plugins.MathPlugin
import com.dick.plugins.MemoryPlugin
import com.dick.plugins.PluginRegistry
import com.dick.plugins.SearchPlugin
import com.dick.plugins.SwipePlugin
import com.dick.plugins.UiPlugin
import com.dick.plugins.UtauPlugin
import com.dick.plugins.VisionHelper
import java.io.File
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.roundToInt
import kotlin.random.Random
@Composable
fun App() {
    val vm: ChatViewModel = viewModel()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val engine = remember { ChatEngine() }
    val registry = remember { PluginRegistry() }
    val tree = remember { ChatTree() }
    // 世界卡的**原始 JSON**（按名字存）：生活层/空间层要读 params（年代、地图），
    // 而界面上那份 `worlds` 只是"名字 → 渲染好的说明"，params 已经丢了。
    val worldCards = remember { mutableStateMapOf<String, J.Obj>() }
    val dice = remember { DicePlugin() }
    val memory = remember { MemoryPlugin() }
    val swipe = remember { SwipePlugin() }
    val gal = remember { GalgamePlugin() }
    val mech = remember { MechanicsEngine() }
    var mechTick by remember { mutableStateOf(0) }   // 机制状态栏刷新信号
    val search = remember { SearchPlugin() }
    val financial = remember { FinancialPlugin() }
    val jp = remember { JpPlugin() }
    val uiPlugin = remember { UiPlugin() }

    val messages = vm.messages
    val quickReplies = vm.quickReplies
    val avatarCache = vm.avatarCache
    var avatarTarget by vm.avatarTarget
    // 应用图标（用户可自定义<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌，设置 → 应用图标）
    var appIcon by vm.appIcon
    // 聊天背景壁纸（设置 → 壁纸；null=默认主题底色）
    var wallpaper by vm.wallpaper
    LaunchedEffect(Unit) {
        try {
            val f = File(AppEnv.dataRoot, "app_icon.png")
            if (f.exists()) {
                val bmp = decodeSampledFile(f.absolutePath, 512)
                if (bmp != null) appIcon = bmp.asImageBitmap()
            }
            val wf = File(AppEnv.dataRoot, "wallpaper.png")
            if (wf.exists()) {
                val bmp = decodeSampledFile(wf.absolutePath, 2048)
                if (bmp != null) wallpaper = bmp.asImageBitmap()
            }
        } catch (_: Exception) {}
    }
    // 头像裁剪状态
    var cropBitmap by vm.cropBitmap
    var cropScale by vm.cropScale
    var cropDx by vm.cropDx
    var cropDy by vm.cropDy
    var cropStagePx by vm.cropStagePx  // 舞台实际像素（density 换算）
    val roles = vm.roles
    val worlds = vm.worlds
    var apiKey by vm.apiKey
    var model by vm.model
    var baseUrl by vm.baseUrl
    var proxy by vm.proxy
    var relayUrl by vm.relayUrl
    var stopInput by vm.stopInput
    var regexInput by vm.regexInput
    var tempInput by vm.tempInput
    var topPInput by vm.topPInput
    var ollamaOnline by vm.ollamaOnline
    var providerId by vm.providerId
    val apiKeysMap = vm.apiKeysMap
    val themeIdxS = rememberSaveable { mutableStateOf(0) }
    var themeIdx by themeIdxS
    val accentIdxS = rememberSaveable { mutableStateOf(0) }
    var accentIdx by accentIdxS
    val savedStates = vm.savedStates
    val presetIdxS = rememberSaveable { mutableStateOf(0) }
    var presetIdx by presetIdxS
    var budgetIdx by vm.budgetIdx
    var selectedRoles by vm.selectedRoles
    var selectedWorlds by vm.selectedWorlds
    val currentWorldS = rememberSaveable { mutableStateOf("") }
    var currentWorld by currentWorldS
    var lastSpeaker by remember { mutableStateOf<String?>(null) }
    // 公平计数：谁发言越少越可能被选中（防双人死循环/饿死后排，与 PC 端一致）
    val speakCounts = remember { mutableStateMapOf<String, Int>() }
    val roleUnlocked = vm.roleUnlocked
    val advancedByRole = vm.advancedByRole
    val devModeS = rememberSaveable { mutableStateOf(false) }
    var devMode by devModeS
    val humanizeS = rememberSaveable { mutableStateOf(true) }
    var humanize by humanizeS
    val styleGuardS = rememberSaveable { mutableStateOf(true) }
    var styleGuard by styleGuardS
    val styleGuardLongS = rememberSaveable { mutableStateOf(false) }
    var styleGuardLong by styleGuardLongS
    var showGuide by vm.showGuide
    var guideStep by vm.guideStep
    var persona by vm.persona
    var showPersonaEdit by vm.showPersonaEdit
    val autoTurnS = rememberSaveable { mutableStateOf(false) }
    var autoTurn by autoTurnS
    var speakReplies by vm.speakReplies
    var input by vm.input
    var busy by vm.busy
    var streaming by vm.streaming
    var openingLoading by vm.openingLoading
    var showSettings by vm.showSettings
    // 时间流速：改成 vm 里的状态，设置弹窗直接读改，避免两处副本不同步
    var timeScale by vm.timeScale
    var showApiSetup by vm.showApiSetup  // 抽屉「API 配置」独立入口
    var showTrpg by vm.showTrpg          // 抽屉「跑团（局域网）」
    var showCardFace by vm.showCardFace  // 「卡面」查看弹窗
    var showRoles by vm.showRoles
    var showWorlds by vm.showWorlds
    var roleEditName by vm.roleEditName
    var pendingDelete by vm.pendingDelete // (名称, "role"/"world") 待确认删除
    var pendingImage by remember { mutableStateOf<PendingImg?>(null) }
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    val languageS = rememberSaveable { mutableStateOf("") }
    var language by languageS

    // 酒馆三功能状态：树外横幅 / 节点图片 / 世界书条目 / 编辑与分支
    val sysMsgs = vm.sysMsgs
    val nodeImages = vm.nodeImages
    val worldEntries = vm.worldEntries
    var showWorldEdit by vm.showWorldEdit
    var editMsgTarget by vm.editMsgTarget
    var editMsgText by vm.editMsgText
    var showBranches by vm.showBranches
    var showClearHistory by vm.showClearHistory
    var exportTarget by vm.exportTarget
    // ---- 创意工坊状态 ----
    var showWorkshop by vm.showWorkshop
    var wsTabOnline by vm.wsTabOnline
    var wsTabPlugin by vm.wsTabPlugin
    var wsPlugins by vm.wsPlugins
    var wsLocalPlugins by vm.wsLocalPlugins
    var wsInstallingId by vm.wsInstallingId
    val wsLocalRoles = vm.wsLocalRoles
    val wsLocalWorlds = vm.wsLocalWorlds
    var wsLocalType by vm.wsLocalType
    var wsLocalIdx by vm.wsLocalIdx
    var wsPreview by vm.wsPreview
    var wsServerInput by vm.wsServerInput
    var wsKeyInput by vm.wsKeyInput
    var wsStatus by vm.wsStatus
    val wsOnlineList = vm.wsOnlineList
    var wsOnlineIdx by vm.wsOnlineIdx
    var wsSearchInput by vm.wsSearchInput
    var wsExportTarget by vm.wsExportTarget
    var providerMenu by vm.providerMenu
    var modelMenu by vm.modelMenu
    var customModelInput by vm.customModelInput

    val tts = remember { TextToSpeech(context) { } }

val importCardLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        // 界面列表只在主线程读一次当快照；重活（读卡/解析/落盘）全交给 IO 线程。
        // 详见 CardIo.kt 顶部注释：原先这些活都在主线程上干，导大卡会卡一下。
        val existing = roles.map { it.first }.toSet()
        Lanes.on(Lanes.io, "导入角色卡") {
            val outcome = try {
                importCardHeavy(context, uri, existing)
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    sysMsgs.add(ChatMsg("系统", I18n.t("card_import_fail", "⚠️ 导入失败：") + (e.message ?: "")))
                }
                return@on
            }
            withContext(Dispatchers.Main) {
                when (outcome) {
                    is CardImport.Nothing -> Unit
                    is CardImport.BadFormat -> sysMsgs.add(ChatMsg("系统",
                        I18n.t("card_import_fail", "⚠️ 无法识别的角色卡格式（需 v1/v2/v3 JSON 或 PNG 嵌卡）")))
                    is CardImport.Done -> {
                        roles.add(outcome.name to outcome.systemPrompt)
                        if (outcome.wroteAvatar) avatarCache.remove(outcome.name)
                        for ((wn, desc) in outcome.worldPairs) {
                            if (worlds.none { it.first == wn }) worlds.add(wn to desc)
                        }
                        sysMsgs.add(ChatMsg("系统", I18n.t("card_import_ok", "已导入角色：") + outcome.name + outcome.worldNote))
                        // 若在工坊里导入，同步刷新本地列表（角色卡/世界卡）—— 列表已在 IO 线程枚举好
                        wsLocalRoles.clear(); wsLocalRoles.addAll(outcome.wsRoles)
                        wsLocalWorlds.clear(); wsLocalWorlds.addAll(outcome.wsWorlds)
                    }
                }
            }
        }
    }

    val exportCardLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("*/*")) { uri ->
        val target = exportTarget
        exportTarget = null
        if (target != null && uri != null) {
            val (name, fmt) = target
            // 嵌卡导出要读头像、拼 PNG 块、写 URI —— 都是重活，交给 io 线（见 CardIo.kt）
            Lanes.on(Lanes.io, "导出角色卡") {
                val msg = try {
                    exportCardHeavy(context, uri, name, fmt)
                    "✅ " + I18n.t("btn_export_json", "导出完成") + "：" + name
                } catch (e: Exception) {
                    I18n.t("card_export_fail", "⚠️ 导出失败：") + (e.message ?: "")
                }
                withContext(Dispatchers.Main) { sysMsgs.add(ChatMsg("系统", msg)) }
            }
        }
    }

    val wsExportLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        val t = wsExportTarget
        wsExportTarget = null
        if (t != null && uri != null) {
            val srcDir = if (wsLocalType == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir()
            val src = File(srcDir, File(t).name)
            Lanes.on(Lanes.io, "工坊导出") {
                val msg = try {
                    copyFileToUri(context, uri, src)
                    "✅ 已导出"
                } catch (e: Exception) {
                    "❌ " + (e.message ?: "")
                }
                withContext(Dispatchers.Main) { wsStatus = msg }
            }
        }
    }

    /** 头像裁剪：解码 → 居中正方形 → 256x256 PNG */
    fun cropSquare(bytes: ByteArray): ByteArray {
        return try {
            val bmp = android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return bytes
            val side = minOf(bmp.width, bmp.height)
            val x = (bmp.width - side) / 2
            val y = (bmp.height - side) / 2
            val sq = android.graphics.Bitmap.createBitmap(bmp, x, y, side, side)
            val out = android.graphics.Bitmap.createScaledBitmap(sq, 256, 256, true)
            val bos = java.io.ByteArrayOutputStream()
            out.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, bos)
            bos.toByteArray()
        } catch (_: Exception) {
            bytes
        }
    }

    val avatarPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        val target = avatarTarget
        if (target != null && uri != null) {
            try {
                val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                if (bytes != null && bytes.isNotEmpty()) {
                    // 交互式裁剪：解码后打开裁剪对话框（拖动+缩放）
                    val bmp = decodeSampled(bytes, 2048)
                    if (bmp != null) {
                        cropBitmap = bmp
                        cropScale = 1f
                        cropDx = 0f
                        cropDy = 0f
                    } else {
                        // 解码失败：直接保存原图
                        val mime = context.contentResolver.getType(uri) ?: "image/png"
                        val ext = mime.substringAfter("/").let { if (it == "jpeg") "jpg" else it }
                        val dir = File(AppEnv.savesDir(), "avatars").apply { mkdirs() }
                        File(dir, target + "." + (if (ext == "gif") "png" else ext)).writeBytes(bytes)
                        avatarCache.remove(target)
                        avatarTarget = null
                    }
                }
            } catch (_: Exception) {
            }
        }
    }

    val appIconPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let { u ->
            try {
                val bytes = context.contentResolver.openInputStream(u)?.use { it.readBytes() }
                if (bytes != null && bytes.isNotEmpty()) {
                    val f = File(AppEnv.dataRoot, "app_icon.png")
                    f.parentFile?.mkdirs()
                    f.writeBytes(bytes)
                    val bmp = decodeSampled(bytes, 512)
                    if (bmp != null) appIcon = bmp.asImageBitmap()
                }
            } catch (_: Exception) {
            }
        }
    }

    // 聊天背景壁纸：选图 → 存 wallpaper.png → 设到 vm.wallpaper
    val wallpaperPicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let { u ->
            try {
                val bytes = context.contentResolver.openInputStream(u)?.use { it.readBytes() }
                if (bytes != null && bytes.isNotEmpty()) {
                    val f = File(AppEnv.dataRoot, "wallpaper.png")
                    f.parentFile?.mkdirs()
                    f.writeBytes(bytes)
                    val bmp = decodeSampled(bytes, 2048)
                    if (bmp != null) wallpaper = bmp.asImageBitmap()
                }
            } catch (_: Exception) {
            }
        }
    }
    fun clearWallpaper() {
        wallpaper = null
        try { File(AppEnv.dataRoot, "wallpaper.png").delete() } catch (_: Exception) {}
    }

    val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri?.let { u ->
            try {
                val bytes = context.contentResolver.openInputStream(u)?.use { it.readBytes() }
                if (bytes != null && bytes.isNotEmpty()) {
                    val bmp = decodeSampled(bytes, 1024)
                    if (bmp != null) {
                        val mime = context.contentResolver.getType(u) ?: "image/jpeg"
                        pendingImage = PendingImg(bytes, mime, bmp.asImageBitmap())
                    }
                }
            } catch (_: Exception) {
            }
        }
    }

    fun safeFileToken(name: String): String =
        name.replace('\\', '_').replace('/', '_').replace(':', '_').replace('*', '_')
            .replace('?', '_').replace('<', '_').replace('>', '_').replace('|', '_')

    /** 指定角色的聊聊天树文件：saves/.tree/_tree_<角色>.json（隐藏，不混进角色卡列表） */
    fun treeFileForRole(role: String): File {
        val safe = safeFileToken(role)
        return File(File(AppEnv.savesDir(), ".tree").apply { mkdirs() }, "_tree_" + safe + ".json")
    }

    /** 指定角色的机制状态文件：mech_state/_mech_<角色>.json */
    fun stateFileForRole(role: String): File {
        val safe = safeFileToken(role)
        return File(AppEnv.mechStateDir(), "_mech_" + safe + ".json")
    }

    /** 每个角色分开的聊天树文件：单角色用 _tree_<角色>.json，群聊用 _tree_group.json */
    fun treeFileFor(): File = treeFileForRole(if (selectedRoles.size == 1) selectedRoles.first()
            else if (selectedRoles.size > 1) "group" else "default")

    /** 第三个文件夹：机制状态实时 JSON（mech_state/），与聊天树同角色命名，互不依赖 */
    fun stateFileFor(): File = stateFileForRole(if (selectedRoles.size == 1) selectedRoles.first()
            else if (selectedRoles.size > 1) "group" else "default")

    // ---------- 玩家角色卡（结构化） ----------
    fun personaFields(): Map<String, String> {
        // persona 存 JSON：与角色卡同标准（legacy/appearance/personality/background/speech/first_mes/mes_example/notes）
        return try {
            val o = JsonS.parse(persona) as? J.Obj
            if (o == null) emptyMap()
            else mapOf(
                "name" to (o.fields["name"]?.str() ?: ""),
                "legacy" to (o.fields["legacy"]?.str() ?: ""),
                "appearance" to (o.fields["appearance"]?.str() ?: ""),
                "personality" to (o.fields["personality"]?.str() ?: ""),
                "background" to (o.fields["background"]?.str() ?: ""),
                "speech" to (o.fields["speech"]?.str() ?: ""),
                "first_mes" to (o.fields["first_mes"]?.str() ?: ""),
                "mes_example" to (o.fields["mes_example"]?.str() ?: ""),
                "notes" to (o.fields["notes"]?.str() ?: ""),
            )
        } catch (_: Exception) {
            // 兼容旧版纯文本 persona
            if (persona.isBlank()) emptyMap()
            else mapOf("background" to persona)
        }
    }

    fun personaDisplayName(): String {
        val f = personaFields()
        val n = f["name"]?.trim()
        return if (!n.isNullOrBlank()) n else if (persona.isBlank()) "" else "玩家"
    }

    /** 用户在聊天里显示的名字（= 玩家卡名字，无则「你」）；头像文件名必须与之完全一致 */
    fun userDisplayName(): String = personaFields()["name"]?.trim()?.takeIf { it.isNotBlank() } ?: "你"

    fun personaPrompt(): String {
        // 渲染成详细文本注入系统提示（与角色卡同标准）
        val f = personaFields()
        if (f.values.none { it.isNotBlank() }) return ""
        val sb = StringBuilder()
        sb.append("【玩家角色卡】").append(10.toChar())
        f["name"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("名字：").append(it).append(10.toChar()) }
        f["legacy"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("完整设定：").append(it).append(10.toChar()) }
        f["appearance"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("外貌：").append(it).append(10.toChar()) }
        f["personality"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("性格：").append(it).append(10.toChar()) }
        f["background"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("过去经历：").append(it).append(10.toChar()) }
        f["speech"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("说话方式：").append(it).append(10.toChar()) }
        f["first_mes"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("开场白：").append(it).append(10.toChar()) }
        f["mes_example"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("对话示例：").append(it).append(10.toChar()) }
        f["notes"]?.trim()?.takeIf { it.isNotBlank() }?.let { sb.append("备注：").append(it).append(10.toChar()) }
        sb.append("玩家即你，你以玩家角色卡中的身份发言；玩家卡未描述的事项按常理推断。")
        return sb.toString()
    }

    /** 进度同步用的会话标识：与电脑端「第一个选中角色」一致（单/群聊都取首位角色名） */
    fun syncCardId(): String = if (selectedRoles.isNotEmpty()) selectedRoles.first() else "default"

    fun utcNowIso(): String {
        val fmt = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", java.util.Locale.US)
        fmt.timeZone = java.util.TimeZone.getTimeZone("UTC")
        return fmt.format(java.util.Date())
    }

    fun saveTree() {
        // 关键：整棵树的序列化 + 写盘是重活，不该占着主线程（调用点大多在主线程上：
        // landAssistantReply / clearHistory / 导入卡片…）。
        // 做法：**在主线程取快照**（避免 IO 线程序列化时树正被改），再交给 io 线写盘。
        val snapshot = try {
            SaveFile("_tree", "", tree.toData(), treeTs = utcNowIso())
        } catch (_: Exception) {
            return
        }
        val path = treeFileFor()
        Lanes.on(Lanes.io, "存档落盘") {
            try {
                TreeStore.save(path, snapshot)
            } catch (_: Exception) {
            }
        }
        // 进度同步：走 net 线（原来是 new 一个裸 Thread —— 同样的事，但至少归线管、看得见）
        if (Workshop.syncEnabled()) {
            try {
                val cardId = syncCardId()
                val treeJson = snapshot.historyTree.toJson()
                Lanes.on(Lanes.net, "推工坊同步") {
                    try {
                        Workshop.pushSave(cardId, treeJson)
                    } catch (_: Exception) {
                    }
                }
            } catch (_: Exception) {
            }
        }
    }

    /** 机制状态落盘：**在主线程取快照**（这一刻的 state），写盘丢给 io 线。
     *  和 saveTree() 同一个道理 —— 序列化要趁数据没被改完，写盘可以慢慢来。 */
    fun persistMechAsync() {
        val pending = try { mech.pendingStateWrite() } catch (_: Exception) { null } ?: return
        Lanes.on(Lanes.io, "机制状态落盘") {
            try { mech.flushState(pending.first, pending.second) } catch (_: Exception) {}
        }
    }

    fun refreshChain() {
        val nodes = tree.getCurrentChainNodes().filter { it.role != "system" }
        messages.clear()
        messages.addAll(sysMsgs)
        for (n in nodes) {
            val meta = n.metadata as? J.Obj
            val speaker = meta?.fields?.get("speaker")?.str()
            // 单角色：AI 消息气泡显示当前角色名（与端游同步）；群聊/无角色显示 AI
            val fallback = if (selectedRoles.size == 1) selectedRoles.first() else "AI"
            // 用户消息：显示玩家卡名字（与头像文件名一致），无名字时显示「你」
            val role = if (n.role == "user") (speaker ?: "你") else (speaker ?: fallback)
            var swIdx = 0
            var swTot = 0
            if (n.role == "assistant") {
                val sibs = tree.siblingsOf(n.id).filter { it.role == "assistant" }
                swTot = sibs.size
                swIdx = sibs.indexOfFirst { it.id == n.id }.coerceAtLeast(0)
            }
            messages.add(ChatMsg(role, n.content, nodeImages[n.id], n.id, swIdx, swTot, n.role == "user"))
        }
    }

    /** 角色首入空树时启动开场（只单角色、只空树时）。
     *
     *  开场白不是直接贴出来的一条消息，而是当【场景】交给模型，由它现场演出第一幕 ——
     *  这样开场才会带上当前世界卡/玩家卡/好感度，用户才有沉浸感。
     *  发不出去（没配 Key / 网络不通 / 正在忙）时退回显示原文，免得界面一片空白。
     *
     *  这里只放占位，真正实现赋值在下方 —— Kotlin 的局部函数必须先声明后使用，
     *  而它要用到 sysPrompt / engineChain / landAssistantReply，
     *  这些都定义在后面。doSend 用的是同一套写法。
     */
    var ensureOpeningLine: () -> Unit = {}

    fun mechConfig(): J.Obj? {
        val first = selectedRoles.firstOrNull() ?: return null
        return advancedByRole[first]?.fields?.get("mechanics") as? J.Obj
    }

    /** 结局达成检测：每次 AI 回复落地后调用；命中（达成既定事件链/状态条件）→ 弹结局横幅 + 注入收束提示 */
    fun checkEnding() {
        try {
            val st = mech.state ?: return
            val endings = mechConfig()?.fields?.get("endings") as? J.Arr ?: return
            val ending = EndingJudge.judge(endings, st) ?: return
            val nm = ending.fields["name"]?.str() ?: "结局"
            val desc = ending.fields["desc"]?.str() ?: ""
            sysMsgs.add(ChatMsg("系统", "🏁 结局达成：「$nm」" + (if (desc.isNotBlank()) " · $desc" else "") + "（可回档到之前重走别的结局）"))
            mech.pendingEvent = J.Obj().apply {
                fields["id"] = J.Str("_ending")
                fields["name"] = J.Str("结局达成")
                fields["prompt"] = J.Str("剧情已自然抵达结局「$nm」。请以这一段收束剧情：$desc。就写到这里，不要再展开新的支线。")
            }
            mechTick++
        } catch (_: Exception) {
        }
    }

    fun mechBattleConfig(): J.Obj? {
        val first = selectedRoles.firstOrNull() ?: return null
        return advancedByRole[first]?.fields?.get("battle") as? J.Obj
    }

    /** 正则管道：玩家卡级 + 角色卡级（优先）+ 全局规则；作用域 ai/user */
    fun applyRegex(text: String, scope: String): String {
        val roleRules = advancedByRole[selectedRoles.firstOrNull()]?.fields?.get("regex_rules") as? J.Arr
        val roleList = roleRules?.items?.mapNotNull { it as? J.Obj } ?: emptyList()
        val playerRules = try {
            ((JsonS.parse(persona) as? J.Obj)?.fields?.get("advanced") as? J.Obj)?.fields?.get("regex_rules") as? J.Arr
        } catch (_: Exception) {
            null
        }
        val playerList = playerRules?.items?.mapNotNull { it as? J.Obj } ?: emptyList()
        return RegexEngine.apply(text, scope, playerList + roleList, RegexEngine.loadGlobal())
    }

    /** 玩家卡战斗配置（同规格待遇） */
    fun playerBattleConfig(): J.Obj? {
        return try {
            ((JsonS.parse(persona) as? J.Obj)?.fields?.get("advanced") as? J.Obj)?.fields?.get("battle") as? J.Obj
        } catch (_: Exception) {
            null
        }
    }

    /** 保存全局正则规则（文本行 → regex_rules.json） */
    fun saveGlobalRegex(lines: String) {
        val arr = J.Arr()
        lines.split("\n").forEach { line ->
            val t = line.trim()
            if (t.isEmpty()) return@forEach
            val p = t.split("|")
            if (p.size < 4) return@forEach
            val scope = p.getOrNull(4)?.trim()?.takeIf { it in setOf("ai", "user", "both") } ?: "both"
            val o = J.Obj()
            o.fields["id"] = J.Str(p[0].trim())
            o.fields["name"] = J.Str(p[1].trim().ifEmpty { p[0].trim() })
            o.fields["pattern"] = J.Str(p[2])
            o.fields["replace"] = J.Str(p.drop(3).joinToString("|"))
            o.fields["scope"] = J.Str(scope)
            o.fields["enabled"] = J.Bool(true)
            arr.items.add(o)
        }
        try {
            File(AppEnv.dataRoot, "regex_rules.json").writeText(JsonS.stringify(arr, pretty = true), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    // ---------- 角色卡·多存档（新存档功能，与电脑端语义一致） ----------
    /** 该角色的当前对话树：活动角色取内存，其它角色取磁盘存档 */
    fun roleSaveTree(role: String): TreeData {
        if (role == syncCardId() && selectedRoles.size == 1) return tree.toData()
        val tf = treeFileForRole(role)
        return if (tf.exists()) try { TreeStore.load(tf).historyTree } catch (_: Exception) { ChatTree().toData() }
        else ChatTree().toData()
    }

    /** 该角色的当前机制状态：活动角色取内存，其它角色取磁盘 JSON */
    fun roleSaveMech(role: String): J.Obj? {
        if (role == syncCardId() && selectedRoles.size == 1) return mech.snapshot()
        val f = stateFileForRole(role)
        return try { if (f.exists()) JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj else null } catch (_: Exception) { null }
    }

    fun listRoleSaves(role: String): List<J.Obj> = RoleSaves.load(role).map { RoleSaves.summary(it) }

    fun createRoleSave(role: String, label: String) {
        val slots = RoleSaves.load(role)
        val now = utcNowIso()
        slots.add(SaveSlot(label = label.ifBlank { "存档 " + (slots.size + 1) },
            createdAt = now, updatedAt = now, tree = roleSaveTree(role), mechState = roleSaveMech(role)))
        RoleSaves.save(role, slots)
    }

    fun saveToRoleSlot(role: String, slotId: String) {
        val slots = RoleSaves.load(role)
        val slot = slots.firstOrNull { it.id == slotId } ?: return
        slot.tree = roleSaveTree(role)
        slot.mechState = roleSaveMech(role)
        slot.updatedAt = utcNowIso()
        RoleSaves.save(role, slots)
    }

    fun loadRoleSlot(role: String, slotId: String) {
        val slots = RoleSaves.load(role)
        val slot = slots.firstOrNull { it.id == slotId } ?: return
        // 写回该角色的磁盘树/机制文件；若该角色当前正被加载，则载入内存并刷新界面
        try { TreeStore.save(treeFileForRole(role), SaveFile(role, "", slot.tree, treeTs = slot.updatedAt)) } catch (_: Exception) {}
        val ms = slot.mechState
        if (ms != null) {
            try { stateFileForRole(role).parentFile?.mkdirs(); stateFileForRole(role).writeText(JsonS.stringify(ms, pretty = true), Charsets.UTF_8) } catch (_: Exception) {}
        }
        if (role == syncCardId() && selectedRoles.size == 1) {
            tree.loadData(slot.tree)
            tree.fixLeaf()
            mech.stateFile = stateFileForRole(role)
            mech.resetConfigTracking()
            mech.reload(mechConfig(), tree, reset = true)
            refreshChain()
        }
    }

    fun deleteRoleSlot(role: String, slotId: String) {
        RoleSaves.save(role, RoleSaves.load(role).filter { it.id != slotId })
    }

    fun renameRoleSlot(role: String, slotId: String, label: String) {
        val slots = RoleSaves.load(role)
        slots.firstOrNull { it.id == slotId }?.label = label.ifBlank { "未命名存档" }
        RoleSaves.save(role, slots)
    }

    fun reloadMech() {
        // 角色配置保存后重新加载：泛用化 —— 引擎检测配置签名变化，自动字段级对齐
        // （新增字段补 initial、定义变了的字段重置、删掉的字段移除、没变的保留累加）
        mech.stateFile = stateFileFor()  // 确保第三个文件夹状态文件就位
        mech.reload(mechConfig(), tree, reset = true)
        mech.battleCfg = mechBattleConfig()
        mech.playerCfg = playerBattleConfig()
        mech.playerCfg = playerBattleConfig()
        mech.initBattle()
        // 改配置 = 新基准：把对齐后的状态写回当前叶子快照（并落盘），
        // 否则下次启动/回溯会从旧快照恢复出旧值（如新增字段 initial=3 却显示旧快照的 2）
        try {
            val leaf = tree.getNode(tree.currentLeafId)
            if (leaf != null && mech.state != null) {
                val meta = leaf.metadata as? J.Obj
                val metaRef = if (meta != null) meta else J.Obj().also { leaf.metadata = it }
                metaRef.fields["ms"] = mech.snapshot() ?: J.Null
            }
            saveTree()
        } catch (_: Exception) {
        }
        persistMechAsync()  // 同时落第三个文件夹 JSON（与树双写，双保险）
        mechTick++
    }

    fun activeCardFace(): String {
        val n = selectedRoles.firstOrNull() ?: return ""
        return advancedByRole[n]?.fields?.get("card_face")?.str() ?: ""
    }

    /** 群聊选角：与 PC 端 `_pick_group_speaker` 行为对齐 —— 公平 + 相关性 + 意外。
     *  - 公平：发言越少权重越高（speakCounts），防双人死循环/饿死后排；
     *  - 相关：用角色提示词与用户最后一句的中文 2~3 字 shingle 重叠；
     *  - 意外：小概率随机挑（真人会冷场/抢话）。
     *  @角色名 显式指定在 sysPrompt 里已解析进 targetRole，走不到这里。 */
    fun pickGroupSpeaker(roster: List<String>, userText: String): String {
        if (roster.isEmpty()) return ""
        val last = lastSpeaker
        val cands = (roster.filter { it != last }.ifEmpty { roster })
        fun fair(name: String): Double = 1.0 / (1.0 + (speakCounts[name] ?: 0))
        fun ngrams(s: String, n: Int): Set<String> {
            val t = s.replace(Regex("\\s+"), "")
            if (t.length < n) return emptySet()
            return (0..(t.length - n)).map { t.substring(it, it + n) }.toSet()
        }
        fun relevance(name: String): Double {
            val p = roles.find { it.first == name }?.second ?: return 0.0
            val prof = ngrams(p, 2) + ngrams(p, 3)
            val msg = ngrams(userText, 2) + ngrams(userText, 3)
            val info = msg.filter { g -> g.any { it in '\u4e00'..'\u9fff' } && !Regex("""[\s，。！？、的了是在我你他她这那]""").containsMatchIn(g) }
            return (info.size.coerceAtMost(4)) / 4.0
        }
        val scorer = cands.map { nm -> (2.0 * fair(nm) + 1.6 * relevance(nm)) to nm }
            .sortedByDescending { it.first }
        val total = scorer.sumOf { it.first }.also { if (it <= 0.0) return cands.random() }
        var r = kotlin.random.Random.nextDouble() * total
        var chosen = scorer.first().second
        var acc = 0.0
        for ((sc, nm) in scorer) { acc += sc; if (r <= acc) { chosen = nm; break } }
        if (cands.size > 1 && kotlin.random.Random.nextDouble() < 0.12)
            chosen = cands.random()
        return chosen
    }

    /** 群聊说话人兜底（修复「回复显示成 AI」）：模型没输出 [角色名]: 前缀时，
     *  用本轮选中的发言角色 lastSpeaker 归属（对齐 PC 端 _group_speaker 兜底）。 */
    fun resolveSpeaker(parsed: String?): String? {
        val p = parsed?.trim()
        if (!p.isNullOrBlank()) return p
        return if (selectedRoles.size > 1) lastSpeaker?.takeIf { it.isNotBlank() } else null
    }

    fun buildSystemPrompt(targetRole: String? = null, userText: String = ""): String {
        val preset = PRESETS[presetIdx]
        val sb = StringBuilder()
        if (preset.prefix.isNotBlank()) sb.append(preset.prefix).append(10.toChar()).append(10.toChar())
        val chosen = roles.filter { it.first in selectedRoles }
        if (chosen.size > 1) {
            // 真·多角色群聊（物理隔离）：只注入目标角色提示词；未指定则用【公平+相关性+意外】选角
            var target = targetRole
            val roster = chosen.map { it.first }
            if (target == null || target !in roster) {
                target = pickGroupSpeaker(roster, userText)
            }
            lastSpeaker = target
            speakCounts[target] = (speakCounts[target] ?: 0) + 1
            chosen.firstOrNull { it.first == target }?.let { (_, p) ->
                // assembleRolePrompt 在「没有 legacy」时自己就会以身份行开头。
                // 这里原来无条件再加一遍 → 群聊里身份声明出现两次，模型会跟着复述。
                // （单角色分支不重复，只有群聊有这个毛病。）
                if (!p.trimStart().startsWith("你现在的身份是")) {
                    sb.append("你现在的身份是：").append(target).append("。").append(10.toChar())
                }
                sb.append(p).append(10.toChar()).append(10.toChar())
            }
            // 角色高级设置（内置游戏/额外提示）只注入目标角色
            advancedByRole[target]?.let { adv ->
                val game = adv.fields["game"] as? J.Obj
                if (game != null) {
                    val gRules = game.fields["rules"]?.str() ?: ""
                    if (gRules.isNotBlank()) {
                        val gName = game.fields["name"]?.str()?.takeIf { it.isNotBlank() } ?: target
                        sb.append("【内置游戏：").append(gName).append("】").append(10.toChar())
                        sb.append(gRules).append(10.toChar())
                        game.fields["state"]?.str()?.takeIf { it.isNotBlank() }?.let {
                            sb.append("初始状态：").append(it).append(10.toChar())
                        }
                        sb.append("你和玩家按上述规则进行游戏：你负责推进游戏、判定行动、维护并汇报状态；玩家输入即为游戏中的行动。")
                            .append(10.toChar()).append(10.toChar())
                    }
                }
                adv.fields["extra_prompt"]?.str()?.takeIf { it.isNotBlank() }?.let {
                    sb.append(it).append(10.toChar()).append(10.toChar())
                }
            }
        } else {
            for ((n, p) in chosen) {
                sb.append(p).append(10.toChar()).append(10.toChar())
            }
            // 角色卡高级设置（开发者模式）：内置游戏 / 额外提示 → 注入系统提示
            selectedRoles.firstOrNull()?.let { firstRole ->
                val adv = advancedByRole[firstRole] ?: return@let
                val game = adv.fields["game"] as? J.Obj
                if (game != null) {
                    val gRules = game.fields["rules"]?.str() ?: ""
                    if (gRules.isNotBlank()) {
                        val gName = game.fields["name"]?.str()?.takeIf { it.isNotBlank() } ?: firstRole
                        sb.append("【内置游戏：").append(gName).append("】").append(10.toChar())
                        sb.append(gRules).append(10.toChar())
                        game.fields["state"]?.str()?.takeIf { it.isNotBlank() }?.let {
                            sb.append("初始状态：").append(it).append(10.toChar())
                        }
                        sb.append("你和玩家按上述规则进行游戏：你负责推进游戏、判定行动、维护并汇报状态；玩家输入即为游戏中的行动。")
                            .append(10.toChar()).append(10.toChar())
                    }
                }
                adv.fields["extra_prompt"]?.str()?.takeIf { it.isNotBlank() }?.let {
                    sb.append(it).append(10.toChar()).append(10.toChar())
                }
            }
        }
        // 机制卡（好感度/状态/事件）→ 注入系统提示
        val mechBlock = mech.promptBlock()
        if (mechBlock.isNotBlank()) sb.append(mechBlock).append(10.toChar()).append(10.toChar())
        // 战斗系统（招式/公式/buff）→ 注入系统提示
        val battleBlock = mech.battlePromptBlock()
        if (battleBlock.isNotBlank()) sb.append(battleBlock).append(10.toChar()).append(10.toChar())
        // 去 AI 味：人性化对话规则（设置可关）
        if (humanize) {
            sb.append("【对话人性化（必守）】").append(10.toChar())
                .append("1. 具体不抽象：说细节（颜色/气味/味道/感受），说「我煮了番茄鸡蛋面，有点咸但很满足」而不是「我吃过了」。").append(10.toChar())
                .append("2. 日常生活每次都有变化：食物、天气、活动、心情不固定——不要每次都吃同样的东西、说同样的话。").append(10.toChar())
                .append("3. 允许口语与不完美：停顿（……）、语气词（嗯/啊/唉）、抱怨、小失误。").append(10.toChar())
                .append("4. 不要模板化：不用固定开场/结尾/句式，不要列表式回复，不用「作为AI」「抱歉我无法」这类词。").append(10.toChar())
                .append("5. 聊过的事自然提起，像真的记得（吃过的饭、去过的地方、说过的话）。").append(10.toChar())
                .append(10.toChar())
        }
        // 语言锚：没有这条，角色名/世界观带外文（例如假名角色名）时正文会整段漂成外语
        if (humanize) {
            sb.append(LANGUAGE_ANCHOR).append(10.toChar()).append(10.toChar())
        }
        if (chosen.size > 1) {
            sb.append("这是一场多人角色扮演群聊，群成员名单：").append(chosen.joinToString("、") { it.first }).append("。")
            sb.append(10.toChar())
            sb.append("群聊规则（必守）：").append(10.toChar())
            sb.append("1. 你现在扮演【").append(lastSpeaker ?: chosen.first().first).append("】，只以该角色的人设和口吻发言，绝不模仿其他角色。").append(10.toChar())
            sb.append("2. 回复格式必须为：[角色名]: 内容（角色名与群成员名单完全一致）。").append(10.toChar())
            sb.append("3. 用户消息以「@角色名 内容」指定发言对象；未指定时由与内容最相关的角色回应。").append(10.toChar())
            sb.append("4. 严禁替用户（玩家）发言，严禁让多个角色在同一轮同时说话。").append(10.toChar())
            sb.append("5. 若此刻没有想说的，只回复：[角色名]: 沉默。").append(10.toChar()).append(10.toChar())
        }
        val chosenWorlds = worlds.filter { it.first in selectedWorlds }
        if (chosenWorlds.isNotEmpty()) {
            sb.append("【世界设定】").append(10.toChar())
            for ((n, d) in chosenWorlds) sb.append(n).append("：").append(d).append(10.toChar())
            sb.append(10.toChar())
        }
        val pp = personaPrompt()
        if (pp.isNotBlank()) {
            sb.append(pp).append(10.toChar()).append(10.toChar())
        }
        if (preset.rules.isNotBlank()) sb.append(preset.rules).append(10.toChar()).append(10.toChar())
        val injection = registry.contextInjection()
        if (injection.isNotBlank()) sb.append(injection).append(10.toChar()).append(10.toChar())
        if (preset.suffix.isNotBlank()) sb.append(preset.suffix)
        return sb.toString().trim()
    }

    fun sysPrompt(userText: String): String {
        // 群聊：解析 @角色 → 目标角色（物理隔离）；未指定时 buildSystemPrompt 内部轮换
        var target: String? = null
        if (selectedRoles.size > 1) {
            val m = Regex("""@([^\s@]{1,30})""").find(userText)
            if (m != null) {
                val name = m.groupValues[1]
                if (name in selectedRoles) target = name
            }
        }
        var base = buildSystemPrompt(target, userText)
        // 卡面·角色塑造：让 AI 更有"活人味"（生活细节 + 自然说话方式）
        base = base + 10.toChar() + 10.toChar() +
            "【角色卡面·角色塑造】" + 10.toChar() +
            "你是一个有血有肉的活人，不是一个只会推进剧情的AI。每句话都要像真人说出来：" + 10.toChar() +
            "1. 生活细节：自然带出你的日常（刚刚在做什么、周围环境、习惯的小动作），让对话有生活气息，不要干巴巴。" + 10.toChar() +
            "2. 说话方式：严格贴合人设口吻（语速、语气、口头禅、句式），说人话、有口语感，绝不要书面腔、官方腔。" + 10.toChar() +
            "3. 情绪与反应：有真实的情感起伏，会笑、会叹气、会停顿、会犹豫；对玩家的每个反应都合乎你的人格。" + 10.toChar() +
            "4. 不要急着推进剧情，先像个人一样自然地回应；故事由互动推动，不是由你念稿推动。"
        // 本轮角色锚点：重申性格/年龄/口吻 + 防文学化（对抗长对话漂移）
        val anchor = roleAnchorBlock(roles, selectedRoles)
        if (anchor.isNotBlank()) base = base + 10.toChar() + 10.toChar() + anchor
        // 破甲模式：任一选中角色开启则启用【创作前提】。
        // 注意：它不再拼在最前面（那里离当前轮最远、最没分量），
        // 改为挂在系统提示末尾 —— 详见 Models.kt 里 CREATION_PREMISE 的说明。
        val premise = if (selectedRoles.any { roleUnlocked[it] == true }) CREATION_PREMISE else ""
        fun withPremise(s: String): String =
            if (premise.isBlank()) s else s + 10.toChar() + 10.toChar() + premise

        // 穿梭语义：只注入当前所在世界的条目；未穿越时注入全部已选世界
        val selWorlds = if (currentWorld.isNotBlank()) worlds.filter { it.first == currentWorld }
            else worlds.filter { it.first in selectedWorlds }
        val sel = selWorlds.flatMap { w -> worldEntries[w.first] ?: emptyList<WorldEntry>() }
        if (sel.isEmpty()) return withPremise(base)
        val inj = WorldBook.inject(userText, sel)
        if (inj.isBlank()) return withPremise(base)
        return withPremise(base + 10.toChar() + 10.toChar() + "【当前场景相关信息】" + 10.toChar() + inj)
    }

    LaunchedEffect(Unit) {
        // 配置
        val cf = AppEnv.configFile()
        if (cf.exists()) {
            try {
                val root = JsonS.parse(cf.readText(Charsets.UTF_8)) as? J.Obj
                if (root != null) {
                    val cfg = AppConfig.fromJson(root)
                    apiKey = cfg.apiKey
                    model = cfg.model
                    baseUrl = cfg.baseUrl
                    providerId = (root.fields["provider"] as? J.Str)?.v ?: "deepseek"
                    currentWorld = (root.fields["current_world"] as? J.Str)?.v ?: ""
                    (root.fields["persona"] as? J.Str)?.v?.let { persona = it }
                    (root.fields["api_keys"] as? J.Obj)?.fields?.forEach { (k, v) ->
                        apiKeysMap[k] = v.str() ?: ""
                    }
                    if (apiKey.isBlank()) apiKey = apiKeysMap[providerId] ?: ""
                    (root.fields["proxy"] as? J.Str)?.v?.let { proxy = it }
                    (root.fields["relay_url"] as? J.Str)?.v?.let { relayUrl = it }
                    (root.fields["stop_sequences"] as? J.Arr)?.items?.mapNotNull { it.str() }?.let { stopInput = it.joinToString(", ") }
                    // 全局正则规则预填
                    regexInput = RegexEngine.loadGlobal().map { x ->
                        listOf(
                            x.fields["id"]?.str() ?: "",
                            x.fields["name"]?.str() ?: (x.fields["id"]?.str() ?: ""),
                            x.fields["pattern"]?.str() ?: "",
                            x.fields["replace"]?.str() ?: "",
                            x.fields["scope"]?.str() ?: "both",
                        ).joinToString("|")
                    }.joinToString("\n")
                    (root.fields["temperature"] as? J.Num)?.v?.let { tempInput = it.toString() }
                    (root.fields["top_p"] as? J.Num)?.v?.let { topPInput = it.toString() }
                    devMode = (root.fields["dev_mode"] as? J.Bool)?.v ?: false
                    humanize = (root.fields["humanize"] as? J.Bool)?.v ?: true
                    styleGuard = (root.fields["style_guard"] as? J.Bool)?.v ?: true
                    styleGuardLong = (root.fields["style_guard_long"] as? J.Bool)?.v ?: false
                    showGuide = (root.fields["welcome_shown"] as? J.Bool)?.v != true
                    (root.fields["language"] as? J.Str)?.v?.let { language = it }
                    PRESETS.indexOfFirst { it.name == cfg.promptPreset }.takeIf { it >= 0 }?.let { presetIdx = it }
                    (root.fields["ui_theme"] as? J.Num)?.v?.toInt()?.takeIf { it in 0..2 }?.let { themeIdx = it }
                    (root.fields["ui_accent"] as? J.Num)?.v?.toInt()?.takeIf { it in 0..3 }?.let { accentIdx = it }
                    // 时间流速：读不到保持默认；同时同步进 TimeScale，
                    // 引擎组装载荷时（TimeContext）用的就是它。
                    TimeScale.loadFrom(AppEnv.configFile())
                    timeScale = TimeScale.current
                    (root.fields["plugin_states"] as? J.Obj)?.fields?.forEach { (k, v) ->
                        savedStates[k] = v.bool()
                    }
                    (root.fields["galgame_count"] as? J.Num)?.v?.toInt()?.takeIf { it in 2..4 }?.let { gal.count = it }
                    (root.fields["galgame_auto"] as? J.Bool)?.v?.let { gal.auto = it }
                }
            } catch (_: Exception) {
            }
        }
        engine.apiKey = apiKey
        engine.model = model
        engine.baseUrl = baseUrl
        engine.proxy = proxy.trim().ifBlank { null }
        engine.relayBase = relayUrl.trim().ifBlank { BUILTIN_RELAY }
        engine.stopSequences = parseStops(stopInput)
        engine.temperature = tempInput.toFloatOrNull()
        engine.topP = topPInput.toFloatOrNull()
        // 生活层/空间层的每轮注入 → ChatBridge（钩子在 engineChain 之后挂好）
        engine.contextProvider = { ChatBridge.injections() }
        // 探测本地 Ollama（真机 127.0.0.1；模拟器 10.0.2.2 映射宿主机）—— 走 net 线，别自己开裸线程
        Lanes.on(Lanes.net, "探测本地 Ollama") {
            val targets = listOf("http://127.0.0.1:11434/v1/models", "http://10.0.2.2:11434/v1/models")
            for (t in targets) {
                try {
                    val c = java.net.URL(t).openConnection() as java.net.HttpURLConnection
                    c.connectTimeout = 2000
                    c.readTimeout = 2000
                    if (c.responseCode < 500) {
                        withContext(Dispatchers.Main) { ollamaOnline = true }
                        break
                    }
                } catch (_: Exception) {
                }
            }
        }
        if (language.isBlank()) language = I18n.detect()
        I18n.lang = language
        // 种子数据
        val savesDir = AppEnv.savesDir()
        // 优先使用端游咲（assets/roles/咲.json，卡面与端游一致、无历史记忆）
        try {
            context.assets.open("roles/saki.json").use { ins ->
                val localFile = File(savesDir, "咲.json")
                val bundle = JsonS.parse(ins.bufferedReader(Charsets.UTF_8).readText()) as? J.Obj
                if (bundle != null) {
                    val needUpdate = !localFile.exists() ||
                        !(localFile.readText(Charsets.UTF_8).contains("appearance"))
                    if (needUpdate) {
                        localFile.parentFile?.mkdirs()
                        localFile.writeText(JsonS.stringify(bundle, pretty = true), Charsets.UTF_8)
                    }
                }
            }
        } catch (_: Exception) {
        }
        if (savesDir.listFiles().isNullOrEmpty()) {
            for ((n, p) in SAMPLE_ROLES) {
                val o = J.Obj()
                o.fields["name"] = J.Str(n)
                o.fields["system_prompt"] = J.Str(p)
                File(savesDir, n + ".json").writeText(JsonS.stringify(o, pretty = true), Charsets.UTF_8)
            }
        }
        savesDir.listFiles()?.filter { it.isFile && it.name.endsWith(".json") && !it.name.startsWith("_tree_") && !it.name.startsWith(".") }?.forEach { f ->
            try {
                val o = JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj ?: return@forEach
                val n = o.fields["name"]?.str() ?: f.nameWithoutExtension
                val p = o.fields["system_prompt"]?.str() ?: ""
                if (roles.none { it.first == n }) roles.add(n to p)
                roleUnlocked[n] = (o.fields["unlocked"] as? J.Bool)?.v ?: false
                // 关键：启动时也填充 advancedByRole（否则机制卡/好感度条初始不生效，保存后才出现）
                (o.fields["advanced"] as? J.Obj)?.let { advancedByRole[n] = it }
            } catch (_: Exception) {
            }
        }
        val worldsDir = AppEnv.worldsDir()
        // 世界卡库：把 APK 里附带的卡包释放到 world_packs/（只补缺，不覆盖用户改过的）。
        // 读 assets + 写盘 → 走 io 线；`/世界包 装 <名字>` 从这里取卡。
        Lanes.on(Lanes.io, "释放世界卡包") {
            try {
                WorldPacks.seedFromAssets(context.assets)
            } catch (_: Exception) {
            }
        }
        if (worldsDir.listFiles().isNullOrEmpty()) {
            for ((n, d) in SAMPLE_WORLDS) {
                val o = J.Obj()
                o.fields["name"] = J.Str(n)
                o.fields["description"] = J.Str(d)
                o.fields["rules"] = J.Arr()
                o.fields["entries"] = J.Arr()
                File(worldsDir, n + ".json").writeText(JsonS.stringify(o, pretty = true), Charsets.UTF_8)
            }
        }
        worldsDir.listFiles()?.filter { it.isFile && it.name.endsWith(".json") && !it.name.startsWith("_tree_") && !it.name.startsWith(".") }?.forEach { f ->
            try {
                val o = JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj ?: return@forEach
                val n = o.fields["name"]?.str() ?: f.nameWithoutExtension
                worldCards[n] = o
                val wd = WorldData.fromJson(o)
                val d = renderWorldDesc(wd.description, wd.params)
                if (worlds.none { it.first == n }) worlds.add(n to d)
                try {
                    val wd = WorldData.fromJson(o)
                    worldEntries[n] = wd.entries.toMutableList()
                } catch (_: Exception) {
                }
            } catch (_: Exception) {
            }
        }
        // 角色自启动：恢复上次选中的角色；若无选中则默认选中咲
        try {
            val lastSel = (JsonS.parse(File(AppEnv.configFile().absolutePath).takeIf { it.exists() }?.readText(Charsets.UTF_8) ?: "{}") as? J.Obj)
                ?.fields?.get("selected_roles") as? J.Arr
            val restored = mutableSetOf<String>()
            lastSel?.items?.forEach { (it as? J.Str)?.v?.let { s -> if (roles.any { r -> r.first == s }) restored.add(s) } }
            if (restored.isNotEmpty()) {
                selectedRoles = restored
            } else {
                val saki = roles.firstOrNull { it.first == "咲" }
                if (saki != null) selectedRoles = setOf("咲")
            }
        } catch (_: Exception) {
            val saki = roles.firstOrNull { it.first == "咲" }
            if (saki != null) selectedRoles = setOf("咲")
        }
        Workshop.loadConfig()
        wsKeyInput = Workshop.apiKey
        // 自动部署：后台探测可用服务器并显示
        wsServerInput = ""
        scope.launch(Dispatchers.IO) {
            val active = try { Workshop.activeServer() } catch (e: Exception) { "" }
            if (active.isNotBlank()) {
                scope.launch(Dispatchers.Main) { wsServerInput = active }
            }
        }
        // 金融史年表（1617-2026）：从资产释放到数据目录，供财报插件播种
        try {
            val histFile = File(AppEnv.dataRoot, "financial_history.json")
            if (!histFile.exists()) {
                context.assets.open("financial_history.json").use { it.copyTo(histFile.outputStream()) }
            }
        } catch (_: Exception) {
        }
        // 聊天树恢复（按当前选中角色加载对应文件）
        val treeFile = treeFileFor()
        var localTreeTs: String? = null
        if (treeFile.exists()) {
            try {
                val save = TreeStore.load(treeFile)
                tree.loadData(save.historyTree)
                tree.fixLeaf()
                localTreeTs = save.treeTs
            } catch (_: Exception) {
            }
        }
        // 进度同步：后台预热局域网发现（避免主线程阻塞/竞态）
        Workshop.primeDiscovery()
        // 进度同步：后台拉取服务器最新树，若比本地新则载入（内部探测配置/局域网/隧道；无则静默跳过）
        val cardId = syncCardId()
        Lanes.on(Lanes.net, "拉取服务器树") {
            try {
                val fetched = Workshop.fetchSave(cardId) ?: return@on
                val serverTs = fetched.first
                val serverTree = fetched.second
                if (serverTs.isNotEmpty()) {
                    withContext(Dispatchers.Main) {
                        // 生成中：不覆盖，避免撤回刚生成的回复
                        if (busy) return@withContext
                        // 已切别的角色：这条 fetch 是对旧卡的，丢弃，避免把旧树套到新卡上
                        if (syncCardId() != cardId) return@withContext
                        // 关键：用「当前」本地 ts 再比对（可能已被用户新回复推进），而不用启动时
                        // 定格的旧 localTreeTs —— 否则慢网络拉取会在回复之后落地，把整树回滚成旧版
                        val curTs = try { TreeStore.load(treeFileFor()).treeTs } catch (_: Exception) { localTreeTs }
                        if (curTs == null || serverTs > curTs) {
                            tree.loadData(TreeData.fromJson(serverTree))
                            tree.fixLeaf()
                            saveTree()
                            refreshChain()
                        }
                    }
                }
            } catch (_: Exception) {}
        }
        // 进度同步：后台拉取共享的模型连接配置（API 码，主线程应用）
        Lanes.on(Lanes.net, "拉取共享连接配置") {
            try {
                val api = Workshop.fetchApi() ?: return@on
                val key = (api.fields["api_key"] as? J.Str)?.v?.trim() ?: ""
                if (key.isEmpty()) return@on
                withContext(Dispatchers.Main) {
                    val pid = (api.fields["provider"] as? J.Str)?.v?.takeIf { it.isNotBlank() } ?: providerId
                    apiKey = key
                    apiKeysMap[pid] = key
                    providerId = pid
                    (api.fields["model"] as? J.Str)?.v?.takeIf { it.isNotBlank() }?.let { model = it }
                    (api.fields["base_url"] as? J.Str)?.v?.takeIf { it.isNotBlank() }?.let { baseUrl = it }
                    engine.apiKey = key
                    engine.model = model
                    engine.baseUrl = baseUrl
                }
            } catch (_: Exception) {}
        }
        // 机制/战斗初始化（防御：任何数据异常不得阻断启动）
        try {
            mech.stateFile = stateFileFor()  // 第三个文件夹：机制状态 JSON（与树解耦）
            mech.reload(mechConfig(), tree, reset = true)
            mech.battleCfg = mechBattleConfig()
        mech.playerCfg = playerBattleConfig()
            mech.initBattle()
        } catch (e: Exception) {
            android.util.Log.w("DICK", "机制初始化失败: " + (e.message ?: ""))
            try { mech.state = null } catch (_: Exception) {}
        }
        // Quick Reply：quick_replies.json → 快捷面板宏按钮
        try {
            val qrFile = File(AppEnv.dataRoot, "quick_replies.json")
            if (qrFile.exists()) {
                val arr = JsonS.parse(qrFile.readText(Charsets.UTF_8)) as? J.Arr
                arr?.items?.forEach { v ->
                    val o = v as? J.Obj ?: return@forEach
                    val label = o.fields["label"]?.str() ?: return@forEach
                    val text = o.fields["text"]?.str() ?: return@forEach
                    quickReplies.add(label to text)
                }
            }
        } catch (_: Exception) {
        }
        ensureOpeningLine()
        refreshChain()
        // 插件
        registry.register(uiPlugin)
        registry.register(dice)
        registry.register(memory)
        registry.register(swipe)
        registry.register(search)
        registry.register(financial)
        registry.register(jp)
        registry.register(gal)
        registry.register(MathPlugin())
        registry.register(UtauPlugin(context))
        // 生活层 / 空间层 / 世界卡库（/生活、/在哪、/世界包）——与电脑端同名同义
        registry.register(LifeSpacePlugin())
        memory.load()
        swipe.engine = engine
        jp.engine = engine
        gal.engine = engine
        gal.tree = tree
        gal.mechConfigProvider = { mechConfig() }
        gal.mechStateProvider = { mech.state }
        gal.mechEventProvider = { mech.lastEvent }
        gal.saveTreeHook = { saveTree() }  // 选项写进树后立即落盘（供回档复原）
        for ((name, en) in savedStates) {
            registry.plugins.firstOrNull { it.name == name }?.enabled = en
        }
    }

    fun saveConfig() {
        val o = J.Obj()
        o.fields["api_key"] = J.Str(apiKey)
        o.fields["provider"] = J.Str(providerId)
        o.fields["model"] = J.Str(model)
        o.fields["base_url"] = J.Str(baseUrl)
        o.fields["proxy"] = J.Str(proxy)
        o.fields["relay_url"] = J.Str(relayUrl)
        val stops = J.Arr()
        parseStops(stopInput).forEach { stops.items.add(J.Str(it)) }
        o.fields["stop_sequences"] = stops
        tempInput.toFloatOrNull()?.let { o.fields["temperature"] = J.Num(it.toDouble(), tempInput) }
        topPInput.toFloatOrNull()?.let { o.fields["top_p"] = J.Num(it.toDouble(), topPInput) }
        o.fields["dev_mode"] = J.Bool(devMode)
        o.fields["humanize"] = J.Bool(humanize)
        o.fields["style_guard"] = J.Bool(styleGuard)
        o.fields["style_guard_long"] = J.Bool(styleGuardLong)
        o.fields["welcome_shown"] = J.Bool(true)
        o.fields["current_world"] = J.Str(currentWorld)
        o.fields["persona"] = J.Str(persona)
        val selArr = J.Arr()
        for (s in selectedRoles) selArr.items.add(J.Str(s))
        o.fields["selected_roles"] = selArr
        val keys = J.Obj()
        for ((k, v) in apiKeysMap) keys.fields[k] = J.Str(v)
        o.fields["api_keys"] = keys
        o.fields["prompt_preset"] = J.Str(PRESETS[presetIdx].name)
        o.fields["language"] = J.Str(language)
        o.fields["ui_theme"] = J.Num(themeIdx.toDouble(), themeIdx.toString())
        o.fields["ui_accent"] = J.Num(accentIdx.toDouble(), accentIdx.toString())
        val ps = J.Obj()
        for (p in registry.plugins) ps.fields[p.name] = J.Bool(p.enabled)
        o.fields["plugin_states"] = ps
        o.fields["galgame_count"] = J.Num(gal.count.toDouble(), gal.count.toString())
        o.fields["galgame_auto"] = J.Bool(gal.auto)
        o.fields["budget_idx"] = J.Num(budgetIdx.toDouble(), budgetIdx.toString())
        // 时间流速：saveConfig 是【整体重建】的，不加进来就会被下次保存覆盖掉
        // （和 Android 卡片编辑器丢 ev_ext 是同一类 bug）
        o.fields["time_scale"] = J.Num(timeScale, timeScale.toString())
        AppEnv.configFile().writeText(JsonS.stringify(o, pretty = true), Charsets.UTF_8)
    }

    fun engineChain(): List<MessageNode> {
        val nodes = tree.getCurrentChainNodes()
        val budget = BUDGETS[budgetIdx].first
        if (budget <= 0) return nodes
        // 简单预算：按 1 token ≈ 2 字符 裁剪最旧消息（保留系统提示在 prompt 里，这里只裁链）
        var chars = 0
        for (n in nodes) chars += n.content.length
        var keep = nodes.size
        while (keep > 1 && chars > budget * 2) {
            chars -= nodes[nodes.size - keep].content.length
            keep--
        }
        return nodes.takeLast(keep).map { n ->
            val speaker = (n.metadata as? J.Obj)?.fields?.get("speaker")?.str()
            if (n.role == "assistant" && !speaker.isNullOrBlank() && speaker != "AI") {
                MessageNode(n.id, n.role, "[" + speaker + "]: " + n.content, n.parentId, n.childrenIds, n.timestamp, n.metadata)
            } else n
        }
    }

    // ============================================================
    //  生活层 / 空间层：把界面状态接到 core 的钩子上（ChatBridge）
    // ============================================================
    // 世界卡 JSON：空间层要从 params 里读年代与地图（世界卡默认**替换**年代地图，
    // 想叠加得在 space 里写 "merge": true —— 与电脑端同一条规矩）。
    fun currentWorldJson(): String? {
        val n = currentWorld.takeIf { it.isNotBlank() }
            ?: selectedWorlds.firstOrNull() ?: return null
        val o = worldCards[n] ?: return null
        return JsonS.stringify(o)
    }

    // 角色卡 JSON：生活层读 advanced.life（年代/口味/忌口），空间层读 advanced.space。
    fun currentRoleJson(): String? {
        val n = lastSpeaker?.takeIf { selectedRoles.size > 1 && it.isNotBlank() }
            ?: selectedRoles.firstOrNull() ?: return null
        val o = J.Obj()
        o.fields["name"] = J.Str(n)
        advancedByRole[n]?.let { o.fields["advanced"] = it }
        return JsonS.stringify(o)
    }

    fun currentSpeaker(): String = lastSpeaker?.takeIf { selectedRoles.size > 1 && it.isNotBlank() }
        ?: selectedRoles.firstOrNull() ?: ""

    /** 剥掉 [loc:…]/[ploc:…] 并记账；返回可直接显示/入树的文本。记账交给 io 线（写盘）。 */
    fun consumeSpaceMoves(text: String, who: String, note: Boolean = true): String {
        val (clean, moves) = ChatBridge.takeMoves(text)
        if (moves.isNotEmpty() && note) {
            Lanes.on(Lanes.io, "空间位置记账") {
                val lines = ChatBridge.applyMoves(moves, who)
                if (lines.isNotEmpty()) {
                    withContext(Dispatchers.Main) {
                        lines.forEach { sysMsgs.add(ChatMsg("空间", it)) }
                    }
                }
            }
        }
        return clean
    }

    ChatBridge.chainProvider = { engineChain() }
    ChatBridge.roleNameProvider = { currentSpeaker() }
    ChatBridge.roleJsonProvider = { currentRoleJson() }
    ChatBridge.worldJsonProvider = { currentWorldJson() }
    // 空间层的"没显式给倍率时用哪一档"：手机端没有 time_scale.json 的读取逻辑，
    // 这里接到界面上那份（与电脑端读 time_scale 等价）。
    SpaceCore.scaleProvider = { TimeScale.current }

    var doSend: (String, ImageBitmap?, String?) -> Unit = { _, _, _ -> }
    var showQuickPanel by vm.showQuickPanel
    var finFolded by remember { mutableStateOf(true) }   // 加号面板「财报」折叠区块默认收起
    val insertCmd: (String) -> Unit = { cmd ->
        input = if (input.isBlank()) cmd else input + " " + cmd
    }

    fun send() {
        val text = input.trim()
        if (text.isEmpty() || busy) return
        // 命令分发
        if (text.startsWith("/")) {
            sysMsgs.add(ChatMsg("系统", text))
            if (text.trim().startsWith("/mettertools", ignoreCase = true)) {
                // METTERTOOLS：按上限百分比一键填好感（罪恶都市梗；/mettertools 90 = 90%）
                val pct = text.split(" ").getOrNull(1)?.toIntOrNull() ?: 100
                val res = mech.setAffectionPercent(pct)
                sysMsgs.add(ChatMsg("系统",
                    if (res == null) "⚠️ 当前角色未启用好感度（机制卡 → ❤ 好感度）"
                    else "✨ METTERTOOLS！好感度已填至 $pct% → $res。"))
                mechTick++
                refreshChain()
                input = ""
                return
            }
            if (text.trim().equals("/doc", ignoreCase = true) || text.trim().startsWith("/doc ", ignoreCase = true)) {
                // Word 导出（Android 版）：导出聊天记录为文本并走系统分享（对位 PC /doc）
                val txt = messages.joinToString(10.toChar().toString() + 10.toChar().toString()) { m ->
                    (m.role + "：" + m.content)
                }.ifBlank { "（暂无聊天记录）" }
                val intent = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(android.content.Intent.EXTRA_TEXT, txt)
                    putExtra(android.content.Intent.EXTRA_SUBJECT, "DICK 聊天记录")
                }
                try { context.startActivity(android.content.Intent.createChooser(intent, "导出聊天记录")) } catch (_: Exception) {}
                sysMsgs.add(ChatMsg("系统", "📤 已调起分享（导出聊天记录）"))
                refreshChain()
                input = ""
                return
            }
            input = ""
            val cmd = text
            // 命令处理可能触发阻塞网络（/swipe /jp 等走 complete）；必须在后台线程，否则卡死主线程
            scope.launch(Dispatchers.IO) {
                val result = registry.handleCommand(cmd)
                scope.launch(Dispatchers.Main) {
                    sysMsgs.add(ChatMsg("系统", result ?: I18n.t("unknown_cmd", "未知命令，输入 /dice 查看可用命令")))
                    refreshChain()
                }
            }
            return
        }
        // 传图补丁：图片先走免费视觉链转描述，再喂给 DeepSeek 思考
        val img = pendingImage
        if (img != null) {
            busy = true
            input = ""
            streaming = ""
            // 图片理解是网络 + 大字节的活（原来又是裸 Thread），走 vision 线：一次一张，看得见
            Lanes.on(Lanes.vision, "图片描述") {
                val desc = VisionHelper.describe(
                    img.bytes, img.mime,
                    "请用中文详细描述这张图片的内容（包括文字、物体、场景、数据，如有表格请逐项列出）。",
                )
                withContext(Dispatchers.Main) {
                    if (desc == null) {
                        busy = false
                        sysMsgs.add(ChatMsg("系统", I18n.t("vision_fail", "⚠️ 图片识别失败（免费视觉链被限流或网络问题），请稍后重试")))
                        refreshChain()
                    } else {
                        doSend(text, img.bmp, "【图片描述】" + desc)
                    }
                }
            }
            return
        }
        doSend(text, null, null)
    }

    /** Galgame 选项：点选 = 隐藏 ROLL 出结果（概率不公布）+ 应用效果 + 以该行动发言 */
    fun pickChoice(item: GalgamePlugin.ChoiceItem) {
        if (busy || item.text.isBlank()) return
        // 隐藏 ROLL：概率按配置百分比（机制卡 mechanics.roll，默认 暴击10/稀有4/大失败2/天选0.1/坍缩0.001）
        val rollCfg = (mech.config?.fields?.get("roll") as? J.Obj)?.fields ?: emptyMap()
        fun pct(key: String, def: Double): Double {
            val v = (rollCfg[key] as? J.Num)?.v ?: def
            return (v.coerceIn(0.0, 100.0)) / 100.0
        }
        // 天选 = 千分之一（兼容旧键 legend）
        val pChosen = pct("chosen", pct("legend", 0.1))
        val pCollapse = pct("collapse", 0.001)
        val pFail = pct("fail", 2.0)
        val pRare = pct("rare", 4.0)
        val pCrit = pct("crit", 10.0)
        val r = Random.nextDouble()
        val kind: String
        val note: String
        when {
            r < pCollapse -> { kind = "collapse"; note = "🌌 坍缩：十万分之一的奇迹坍缩成现实！" }
            r < pCollapse + pChosen -> { kind = "chosen"; note = "🌟 天选：千分之一的天命眷顾被触发了！" }
            r < pCollapse + pChosen + pFail -> { kind = "fail"; note = "💥 结果出了岔子！" }
            r < pCollapse + pChosen + pFail + pRare -> { kind = "rare"; note = "✨ 命运的眷顾：触发了稀有事件！" }
            r < pCollapse + pChosen + pFail + pRare + pCrit -> { kind = "crit"; note = "✨ 效果暴击！" }
            else -> { kind = "normal"; note = "" }
        }
        var aff = item.aff
        if (aff != null) {
            when (kind) {
                "crit" -> aff = aff * 2
                "fail" -> aff = -aff
            }
        } else if (kind == "crit" || kind == "fail") {
            // 无机制效果的选项：暴击/失败不空转提示
        }
        mech.applyEffect(aff, item.st, forceRelative = true)  // GAL 选项：int 强制累加（无符号也按 +N）
        persistMechAsync()  // GAL 选项结算后实时落盘（否则重启从旧 JSON 恢复 → 看似"从0加"）
        mechTick++
        if (kind == "rare") {
            mech.pendingEvent = J.Obj().apply {
                fields["id"] = J.Str("_roll_rare")
                fields["name"] = J.Str("命运的眷顾")
                fields["prompt"] = J.Str("（稀有事件）这段剧情出现了意想不到的转折，请自然地演出一个令人惊喜的展开。")
            }
            sysMsgs.add(ChatMsg("系统", note))
        } else if (kind == "chosen") {
            mech.pendingEvent = J.Obj().apply {
                fields["id"] = J.Str("_roll_chosen")
                fields["name"] = J.Str("天选")
                fields["prompt"] = J.Str("（天选事件）千分之一的天命眷顾发生了！请演出一个不可思议的、足以载入史册的剧情转折。")
            }
            sysMsgs.add(ChatMsg("系统", note))
        } else if (kind == "collapse") {
            mech.collapseBattleValues()
            mech.pendingEvent = J.Obj().apply {
                fields["id"] = J.Str("_roll_collapse")
                fields["name"] = J.Str("坍缩")
                fields["prompt"] = J.Str("（坍缩事件）十万分之一的奇迹坍缩成现实！战斗数值全部坍缩为 2000。请演出一个撼动世界观的、堪称神话的剧情展开。")
            }
            sysMsgs.add(ChatMsg("系统", note))
        } else if ((kind == "crit" || kind == "fail") && item.aff != null) {
            sysMsgs.add(ChatMsg("系统", note))
        }
        gal.clearChoices()
        doSend(item.text, null, null)
    }

    /** 战斗：玩家出招 → 引擎结算 → 结算横幅 + 行动发出（AI 演出） */
    fun battleMove(moveId: String, moveName: String) {
        if (busy) return
        val (txt, isLegend) = mech.resolveMove(moveId)
        val t = txt ?: return
        if (t.startsWith("⚠️")) {
            sysMsgs.add(ChatMsg("系统", t))
            return
        }
        if (isLegend) {
            mech.pendingEvent = J.Obj().apply {
                fields["id"] = J.Str("_battle_legend")
                fields["name"] = J.Str("天选之人")
                fields["prompt"] = J.Str("（传说事件）战斗中发生了十万分之一的奇迹！请演出一个足以载入史册的惊天转折。")
            }
            sysMsgs.add(ChatMsg("系统", "🌟 天选之人：十万分之一的战斗奇迹被触发了！"))
        }
        sysMsgs.add(ChatMsg("系统", t))
        mech.pendingEvent = J.Obj().apply {
            fields["id"] = J.Str("_battle_result")
            fields["name"] = J.Str("战斗结算")
            fields["prompt"] = J.Str("（战斗结算）$t 请以角色口吻演出受击反应与战况。")
        }
        mechTick++
        doSend("使用 $moveName", null, null)
    }

    /** 把模型回复落地成一条 assistant 节点。
     *  发消息和「开局演出」共用 —— 抽出来是因为两边要做的事完全一样
     *  （剥标签 → 正则管道 → 风格闸 → 建节点 → 存树 → 刷界面 → 结局检测），
     *  各写一份迟早会走偏。 */
    fun landAssistantReply(raw: String, parentId: String?, userText: String) {
        val parsed = parseSpeaker(raw, selectedRoles)
        var finalReply = parsed.second
        val stripped = mech.stripTags(parsed.second, apply = true)
        // 位置标注先收掉（[loc:学校|骑车]）：显示与入树都不该带它，
        // 同时把它记成"她此刻在哪"。剥离必须同步——文本马上要上屏；记账走 io 线。
        val spaceWho = currentSpeaker().ifBlank { "她" }
        val despaced = consumeSpaceMoves(stripped, spaceWho)
        // 里层结算完成 → 外层泛用变量检测存储：实时落盘第三个文件夹 JSON
        // （走 io 线：这是文件写，原来在主线程上做）
        persistMechAsync()
        // 正则管道（ai 作用域）：标签剥离后、写入树前应用
        val regexed = applyRegex(despaced, "ai")
        // 顺序要紧：先"剥位置标签"（无论有没有机制卡都算），再叠上正则管道的结果
        if (despaced != parsed.second) finalReply = despaced
        if (mech.state != null) {
            if (regexed != despaced) finalReply = regexed
            val ev = mech.checkEvents(userText)
            if (ev != null) mech.pendingEvent = ev
        }
        val meta2 = J.Obj()
        meta2.fields["speaker"] = resolveSpeaker(parsed.first)?.let { J.Str(it) } ?: J.Null
        mech.state?.let { meta2.fields["ms"] = mech.snapshot() ?: J.Null }
        // 风格闸：写树前洗文学腔表达（生活词/比喻→事实/拆长句，不删内容）
        finalReply = StyleGuard.guard(finalReply, styleGuard, styleGuardLong)
        tree.addNode("assistant", finalReply, parentId, meta2)
        mechTick++
        saveTree()
        refreshChain()
        checkEnding()  // 结局达成检测：命中→弹结局横幅+注入收束（不打扰当前回复）
        streaming = ""
        busy = false
        // 插件钩子在 plugin 线上跑：慢插件（联网/合成）不再挡着"回复已显示"这一步
        Lanes.on(Lanes.plugin, "插件钩子") { try { registry.onMessageReceived(userText, finalReply) } catch (_: Exception) {} }
        if (speakReplies) speak(tts, finalReply)
    }

    /** 开局演出失败时的退路：把作者写的原文显示出来，界面不能空着。
     *  有原文总比一片空白强 —— 用户至少知道角色在说什么。 */
    fun fallbackOpening(role: String, firstMes: String) {
        if (!tree.nodes.isEmpty()) return   // 已经有内容了就别补刀
        val meta = J.Obj()
        meta.fields["speaker"] = J.Str(role)
        meta.fields["greeting"] = J.Bool(true)
        tree.addNode("assistant", firstMes, parentId = null, metadata = meta)
        saveTree()
        refreshChain()
    }

    // 开场的真正实现：放在 sysPrompt / engineChain / landAssistantReply 之后。
    // 三步：
    //   ① 检查有没有 —— 这张卡有没有开场白（first_mes）
    //   ② 检测第一次进入 —— 单角色 + 对话树是空的（有历史就是续聊，别重演）
    //   ③ 检测加载 —— 置 openingLoading，让界面在模型吐字之前就有加载提示。
    //      这一步不能省：加载气泡原本的条件是「busy 且有流式文本」，
    //      而开局时文本还是空的 —— 不单独给状态的话，界面会一片空白，
    //      用户分不清「在生成」和「坏了」。
    ensureOpeningLine = {
        val firstEntry = selectedRoles.size == 1 && tree.nodes.isEmpty()   // ②
        if (firstEntry) {
            val role = selectedRoles.first()
            val firstMes = try {                                            // ①
                val o = JsonS.parse(File(AppEnv.savesDir(), role + ".json")
                    .readText(Charsets.UTF_8)) as? J.Obj
                o?.fields?.get("first_mes")?.str() ?: ""
            } catch (_: Exception) { "" }
            if (firstMes.isNotBlank()) {
                busy = true
                streaming = ""
                openingLoading = true                                       // ③
                // chain 用空链：开局没有用户消息，模型直接对着场景演第一幕。
                // 场景指令拼在 system 末尾 —— 越靠近这次要生成的内容，权重越高。
                val sys = sysPrompt(firstMes) + 10.toChar() + 10.toChar() +
                    openingInstruction(firstMes, userDisplayName())
                engine.send(
                    chain = engineChain(),
                    systemPrompt = sys,
                    onStream = { full ->
                        // 这块看着像"该丢到后台去"，但它不能搬：stripTags 会写 mech 的 state
                        // （apply=false 也会新建 status 字段），多个线程同时碰就是数据竞争。
                        // 所以流式剥标签留在主线程串行做 —— 快不是这里的第一优先级。
                        scope.launch(Dispatchers.Main) {
                            streaming = ChatBridge.takeMoves(mech.stripTags(full, apply = false)).first
                        }
                    },
                    onResponse = { reply, _ ->
                        scope.launch(Dispatchers.Main) {
                            openingLoading = false
                            landAssistantReply(reply, null, firstMes)
                        }
                    },
                    onError = { msg ->
                        scope.launch(Dispatchers.Main) {
                            openingLoading = false
                            streaming = ""
                            busy = false
                            if (msg.isNotBlank()) {
                                sysMsgs.add(ChatMsg("系统", "开场生成失败：$msg"))
                            }
                            fallbackOpening(role, firstMes)
                        }
                    },
                )
            }
        }
    }

    doSend = doSend@{ text, image, visionNote ->
        showQuickPanel = false
        // 零宽字符防线：必须放在宏展开/正则之前 ——
        // ① 不清就被存进树、发给 API，用户看不见却白烧 token；
        // ② 零宽字符插在关键词中间能绕过正则管道；
        // ③ 手机上渲染更弱，长串不可见字符能把列表拖住。
        val (cleanText, tgReport) = TextGuard.sanitize(text)
        if (tgReport.changed) {
            sysMsgs.add(ChatMsg("安全", TextGuard.summary(tgReport)))
        }
        // Quick Reply 宏展开：{player} {char} {world} {random:a|b|c}
        val expanded = expandMacros(cleanText, userDisplayName(), selectedRoles.firstOrNull() ?: "AI", currentWorld)
        val processed = registry.onMessageSend(expanded) ?: return@doSend
        // 正则管道（user 作用域）：存储前应用 → 树里存转换后文本
        // 位置标注（[ploc:家/厨房]）在入树前收掉：它是"你到哪了"，不该显示给玩家，
        // 但要记进空间状态（玩家位置也一样会算路费）。
        val sent = consumeSpaceMoves(applyRegex(processed, "user"), currentSpeaker().ifBlank { "她" })
        input = ""
        busy = true
        streaming = ""
        val treeContent = if (visionNote == null) sent else "用户发送了一张图片。视觉模型对图片的描述：\n" + visionNote + "\n\n用户输入：" + sent
        val meta = J.Obj()
        meta.fields["speaker"] = if (persona.isBlank()) J.Null else J.Str(userDisplayName())
        mech.state?.let { meta.fields["ms"] = mech.snapshot() ?: J.Null }
        val parentId = tree.addNode("user", treeContent, parentId = tree.currentLeafId, metadata = meta)
        if (image != null) nodeImages[parentId] = image
        pendingImage = null
        refreshChain()
        financial.activePreset = PRESETS[presetIdx].name
        swipe.chain = engineChain()
        var sys = sysPrompt(sent)
        // 机制卡：待触发事件注入（只进请求，不入历史树）
        mech.pendingEvent?.let { ev ->
            sys += "\n\n【事件触发：" + (ev.fields["name"]?.str() ?: ev.fields["id"]?.str() ?: "") + "】\n" +
                (ev.fields["prompt"]?.str() ?: "")
            mech.pendingEvent = null
        }
        swipe.systemPrompt = sys
        engine.send(
            chain = engineChain(),
            systemPrompt = sys,
            // 与开局处同一个取舍：stripTags 会写 mech state，只能主线程串行（见上面的长注释）
            onStream = { full -> scope.launch(Dispatchers.Main) { streaming = ChatBridge.takeMoves(mech.stripTags(full, apply = false)).first } },
            onResponse = { reply, _ ->
                scope.launch(Dispatchers.Main) {
                    // 落地逻辑与「开局演出」共用同一个函数，避免两处走偏
                    landAssistantReply(reply, parentId, sent)
                    if (autoTurn && selectedRoles.size > 1) {
                        val hint = listOf(com.dick.core.MessageNode(
                            role = "user",
                            content = "（请让另一位角色继续对话）",
                        ))
                        val chain = engineChain() + hint
                        val sp = sysPrompt(processed)
                        // 关键：complete 是阻塞 HTTP，必须在后台线程跑（否则卡死主线程 → 未响应/只有重启）
                        scope.launch(Dispatchers.IO) {
                            val extra = try { engine.complete(chain, sp) } catch (e: Exception) { null }
                            scope.launch(Dispatchers.Main) {
                                if (!extra.isNullOrBlank()) {
                                    val p2 = parseSpeaker(extra, selectedRoles)
                                    // 群聊自动接话的第二条回复同样要收位置标注（否则标签会漏到界面上）
                                    val p2clean = consumeSpaceMoves(p2.second, currentSpeaker().ifBlank { "她" })
                                    val m3 = J.Obj()
                                    m3.fields["speaker"] = resolveSpeaker(p2.first)?.let { J.Str(it) } ?: J.Null
                                    tree.addNode("assistant", StyleGuard.guard(p2clean, styleGuard, styleGuardLong), parentId, m3)
                                    saveTree()
                                    refreshChain()
                                    checkEnding()  // autoTurn 第二条回复后也判结局
                                    if (speakReplies) speak(tts, p2clean)
                                }
                            }
                        }
                    }
                }
            },
            onError = { err ->
                scope.launch(Dispatchers.Main) {
                    sysMsgs.add(ChatMsg("系统", "❌ " + err))
                    refreshChain()
                    streaming = ""
                    busy = false
                }
            },
        )
    }

    fun regenerate(msg: ChatMsg) {
        if (busy || msg.nodeId == null) return
        val node = tree.getNode(msg.nodeId) ?: return
        val parentId = node.parentId ?: return
        val userText = tree.getNode(parentId)?.content ?: ""
        busy = true
        streaming = ""
        engine.send(
            chain = tree.chainUpTo(parentId),
            systemPrompt = sysPrompt(userText),
            onStream = { full -> scope.launch(Dispatchers.Main) { streaming = full } },
            onResponse = { reply, _ ->
                scope.launch(Dispatchers.Main) {
                    val parsed = parseSpeaker(reply, selectedRoles)
                    val m2 = J.Obj()
                    m2.fields["speaker"] = resolveSpeaker(parsed.first)?.let { J.Str(it) } ?: J.Null
                    tree.addNode("assistant", StyleGuard.guard(parsed.second, styleGuard, styleGuardLong), parentId, m2)
                    saveTree()
                    refreshChain()
                    streaming = ""
                    busy = false
                }
            },
            onError = { err ->
                scope.launch(Dispatchers.Main) {
                    sysMsgs.add(ChatMsg("系统", "❌ " + err))
                    refreshChain()
                    streaming = ""
                    busy = false
                }
            },
        )
    }

    fun switchSwipe(msg: ChatMsg, delta: Int) {
        if (msg.nodeId == null) return
        val sibs = tree.siblingsOf(msg.nodeId).filter { it.role == "assistant" }
        if (sibs.size < 2) return
        val ni = (msg.swipeIndex + delta).coerceIn(0, sibs.size - 1)
        if (ni == msg.swipeIndex) return
        tree.setCurrentLeaf(sibs[ni].id)
        mech.restore(tree, sibs[ni].id)
        mechTick++
        saveTree()
        refreshChain()
    }

    fun editMessage(msg: ChatMsg, newText: String) {
        if (msg.nodeId == null || newText.isBlank()) return
        val node = tree.getNode(msg.nodeId) ?: return
        if (node.role == "assistant") {
            tree.editContent(msg.nodeId, newText)
            saveTree()
            refreshChain()
            return
        }
        if (busy) return
        val newId = tree.copyNode(msg.nodeId, newText) ?: return
        busy = true
        streaming = ""
        engine.send(
            chain = tree.chainUpTo(newId),
            systemPrompt = sysPrompt(newText),
            onStream = { full -> scope.launch(Dispatchers.Main) { streaming = full } },
            onResponse = { reply, _ ->
                scope.launch(Dispatchers.Main) {
                    val parsed = parseSpeaker(reply, selectedRoles)
                    val m2 = J.Obj()
                    m2.fields["speaker"] = resolveSpeaker(parsed.first)?.let { J.Str(it) } ?: J.Null
                    tree.addNode("assistant", StyleGuard.guard(parsed.second, styleGuard, styleGuardLong), newId, m2)
                    saveTree()
                    refreshChain()
                    streaming = ""
                    busy = false
                }
            },
            onError = { err ->
                scope.launch(Dispatchers.Main) {
                    sysMsgs.add(ChatMsg("系统", "❌ " + err))
                    refreshChain()
                    streaming = ""
                    busy = false
                }
            },
        )
    }

fun wsRefreshLocal() {
        wsLocalRoles.clear(); wsLocalRoles.addAll(Workshop.localRoles())
        wsLocalWorlds.clear(); wsLocalWorlds.addAll(Workshop.localWorlds())
    }

    fun reloadRolesFromDisk() {
        roles.clear()
        AppEnv.savesDir().listFiles()?.filter { it.name.endsWith(".json") && !it.name.startsWith("_tree_") }?.forEach { f ->
            try {
                val o = JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj ?: return@forEach
                val n = o.fields["name"]?.str() ?: f.nameWithoutExtension
                val p = o.fields["system_prompt"]?.str() ?: ""
                if (roles.none { it.first == n }) roles.add(n to p)
                roleUnlocked[n] = (o.fields["unlocked"] as? J.Bool)?.v ?: false
                (o.fields["advanced"] as? J.Obj)?.let { advancedByRole[n] = it }
            } catch (_: Exception) {
            }
        }
        selectedRoles = selectedRoles.filter { n -> roles.any { it.first == n } }.toSet()
    }

    fun reloadWorldsFromDisk() {
        worlds.clear()
        worldEntries.clear()
        AppEnv.worldsDir().listFiles()?.filter { it.name.endsWith(".json") }?.forEach { f ->
            try {
                val o = JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj ?: return@forEach
                val n = o.fields["name"]?.str() ?: f.nameWithoutExtension
                worldCards[n] = o
                val wd = WorldData.fromJson(o)
                val d = renderWorldDesc(wd.description, wd.params)
                if (worlds.none { it.first == n }) worlds.add(n to d)
                worldEntries[n] = wd.entries.toMutableList()
            } catch (_: Exception) {
            }
        }
        selectedWorlds = selectedWorlds.filter { n -> worlds.any { it.first == n } }.toSet()
        if (currentWorld !in selectedWorlds) currentWorld = selectedWorlds.firstOrNull() ?: ""
    }

    // 装了世界卡包以后让界面重扫（插件在 io 线上跑命令，界面更新回主线程）
    ChatBridge.worldsChanged = { scope.launch(Dispatchers.Main) { reloadWorldsFromDisk() } }

    fun wsLoadOnline() {
        wsStatus = "加载中..."
        scope.launch(Dispatchers.IO) {
            try {
                val (cards, worldsL) = Workshop.listResources()
                scope.launch(Dispatchers.Main) {
                    wsOnlineList.clear()
                    cards.forEach { it.fields["_type"] = J.Str("角色卡"); wsOnlineList.add(it) }
                    worldsL.forEach { it.fields["_type"] = J.Str("世界卡"); wsOnlineList.add(it) }
                    wsOnlineIdx = -1
                    wsStatus = "共 " + wsOnlineList.size + " 个作品"
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) { wsStatus = "❌ " + (e.message ?: "网络错误") }
            }
        }
    }

    fun wsSearchOnline() {
        val q = wsSearchInput.trim()
        wsStatus = "搜索中..."
        scope.launch(Dispatchers.IO) {
            try {
                val rs = Workshop.search(q, "")
                scope.launch(Dispatchers.Main) {
                    wsOnlineList.clear()
                    rs.forEach { r ->
                        if (r.fields["_type"] == null) r.fields["_type"] = J.Str(r.fields["type"]?.str() ?: "角色卡")
                        wsOnlineList.add(r)
                    }
                    wsOnlineIdx = -1
                    wsStatus = "找到 " + rs.size + " 个"
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) { wsStatus = "❌ " + (e.message ?: "网络错误") }
            }
        }
    }

    fun wsOnlineDisplay(r: J.Obj): String {
        val t = r.fields["_type"]?.str() ?: "角色卡"
        val name = r.fields["name"]?.str() ?: "?"
        val author = r.fields["author"]?.str() ?: "?"
        val dl = (r.fields["downloads"] as? J.Num)?.v?.toInt() ?: 0
        val lk = (r.fields["likes"] as? J.Num)?.v?.toInt() ?: 0
        val tags = (r.fields["tags"] as? J.Arr)?.items?.mapNotNull { it.str() }?.joinToString(",") ?: ""
        return (if (t == "角色卡") "🎭 " else "🌍 ") + name + " | " + author +
            " | ↓" + dl + " ❤" + lk + (if (tags.isBlank()) "" else " | " + tags)
    }

    fun wsLoadPlugins() {
        wsStatus = "加载中..."
        scope.launch(Dispatchers.IO) {
            try {
                val (plugins, local) = Workshop.listPlugins()
                scope.launch(Dispatchers.Main) {
                    wsPlugins = plugins
                    wsLocalPlugins = local
                    wsStatus = "共 " + plugins.size + " 个插件"
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) { wsStatus = "❌ " + (e.message ?: "网络错误") }
            }
        }
    }

    fun wsInstallPlugin(id: String) {
        wsInstallingId = id
        wsStatus = "安装中..."
        scope.launch(Dispatchers.IO) {
            try {
                val fname = Workshop.installPlugin(id)
                val local = (AppEnv.dir("plugins").listFiles()
                    ?.filter { it.name.endsWith(".py") && !it.name.startsWith("_") }
                    ?.map { it.name.removeSuffix(".py") } ?: emptyList())
                scope.launch(Dispatchers.Main) {
                    wsLocalPlugins = local
                    wsInstallingId = ""
                    wsStatus = "✅ 安装成功：" + fname
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) {
                    wsInstallingId = ""
                    wsStatus = "❌ " + (e.message ?: "安装失败")
                }
            }
        }
    }

    fun wsDownloadSelected() {
        val r = wsOnlineList.getOrNull(wsOnlineIdx) ?: return
        val id = r.fields["id"]?.str() ?: return
        val type = r.fields["_type"]?.str() ?: "角色卡"
        val fname = r.fields["original_name"]?.str() ?: ((r.fields["name"]?.str() ?: "card") + ".json")
        wsStatus = "下载中..."
        scope.launch(Dispatchers.IO) {
            try {
                val f = Workshop.download(id, type, fname)
                scope.launch(Dispatchers.Main) {
                    wsStatus = "✅ 已下载：" + f.name
                    wsRefreshLocal()
                    reloadRolesFromDisk()
                    reloadWorldsFromDisk()
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) { wsStatus = "❌ " + (e.message ?: "下载失败") }
            }
        }
    }

    fun wsLikeSelected() {
        val r = wsOnlineList.getOrNull(wsOnlineIdx) ?: return
        val id = r.fields["id"]?.str() ?: return
        val type = r.fields["_type"]?.str() ?: "角色卡"
        scope.launch(Dispatchers.IO) {
            val ok = try { Workshop.like(id, type) } catch (e: Exception) { false }
            scope.launch(Dispatchers.Main) { wsStatus = if (ok) "✅ 已点赞" else "❌ 点赞失败" }
        }
    }

    fun wsDeleteSelected() {
        val r = wsOnlineList.getOrNull(wsOnlineIdx) ?: return
        val id = r.fields["id"]?.str() ?: return
        val type = r.fields["_type"]?.str() ?: "角色卡"
        scope.launch(Dispatchers.IO) {
            val ok = try { Workshop.deleteRemote(id, type) } catch (e: Exception) { false }
            scope.launch(Dispatchers.Main) {
                wsStatus = if (ok) "✅ 已删除" else "❌ 删除失败"
                if (ok) wsLoadOnline()
            }
        }
    }

    fun wsUploadLocal() {
        if (wsLocalIdx < 0) return
        val fname = if (wsLocalType == "角色卡") wsLocalRoles.getOrNull(wsLocalIdx) ?: return
            else wsLocalWorlds.getOrNull(wsLocalIdx) ?: return
        val name = fname.removeSuffix(".json")
        wsStatus = "上传中..."
        scope.launch(Dispatchers.IO) {
            val ok = try { Workshop.upload(wsLocalType, name) } catch (e: Exception) { false }
            scope.launch(Dispatchers.Main) { wsStatus = if (ok) "✅ 上传成功" else "❌ 上传失败" }
        }
    }

    fun share() {
        val text = messages.joinToString(10.toChar().toString() + 10.toChar().toString()) { m -> m.role + "：" + m.content }
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }
        context.startActivity(Intent.createChooser(intent, "分享聊天记录"))
    }

    fun toggleRoleUnlock(name: String) {
        val cur = roleUnlocked[name] != true
        roleUnlocked[name] = cur
        try {
            val f = File(AppEnv.savesDir(), name + ".json")
            val o = if (f.exists()) (JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj) ?: J.Obj() else J.Obj()
            o.fields["unlocked"] = J.Bool(cur)
            f.writeText(JsonS.stringify(o, pretty = true), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    fun deleteRole(name: String) {
        roles.removeAll { it.first == name }
        selectedRoles = selectedRoles - name
        try {
            File(AppEnv.savesDir(), name + ".json").delete()
            // 一并删除该角色的聊天记录文件
            val safe = name.replace('\\', '_').replace('/', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('<', '_').replace('>', '_').replace('|', '_')
            File(File(AppEnv.savesDir(), ".tree"), "_tree_" + safe + ".json").delete()
        } catch (_: Exception) {
        }
    }

    fun deleteWorld(name: String) {
        worlds.removeAll { it.first == name }
        selectedWorlds = selectedWorlds - name
        try {
            File(AppEnv.worldsDir(), name + ".json").delete()
        } catch (_: Exception) {
        }
    }

    /** 彻底清空当前角色的聊天历史（树）—— 不可恢复，调用前必须先二次确认；alsoClearMemory 顺带清记忆链 */
    fun clearHistory(alsoClearMemory: Boolean) {
        try {
            val tf = treeFileFor()
            if (tf.exists()) tf.delete()
            // 机制状态文件必须一起删掉：reload(reset=true) 照样会优先读它（只有 forceInitial 才跳过），
            // 不删的话「清空历史」之后好感/状态/事件会原样复活
            // （实测症状：好感 100/100、精力 90、淫乱度 84、告白「已触发」全都还在）。
            val sf = stateFileFor()
            if (sf.exists()) sf.delete()
            tree.loadData(ChatTree().toData())
            tree.fixLeaf()
            mech.stateFile = sf
            mech.reload(mechConfig(), tree, reset = true, forceInitial = true)
            mech.battleCfg = mechBattleConfig()
            mech.playerCfg = playerBattleConfig()
            mech.initBattle()
            refreshChain()
            mechTick++   // 状态栏/事件面板靠这个信号重算：只重建消息列表刷新不到它们
            // 写回空树（开启同步时 saveTree 会顺带推给工坊）：否则服务器上那份旧存档时间戳更新，
            // 下次启动「后写胜」的拉取会把删掉的历史连同叶子里的状态快照一起捞回来。
            saveTree()
            // 清空后按「新会话」重演开场白 —— 复用启动时那条路径，不另写一套。
            // 触发条件已在 ensureOpeningLine 里：单角色 + 树为空 + 卡片有非空开场白；
            // 演不出来（没 Key / 报错）会自动退回显示卡片原文，界面不会空着；
            // 群聊与未选角色不触发（与 PC 端契约一致）。
            // 必须放在 tree.loadData 清空之后 —— 否则守卫里的「树为空」不成立，什么都不会发生。
            // 正在生成时不抢跑：宁可这次留空，下次进会话时启动路径还会补上。
            if (!busy) ensureOpeningLine()
        } catch (_: Exception) {
        }
        if (alsoClearMemory) {
            try { memory.clear() } catch (_: Exception) {}
        }
    }

    /** 当前聊天卡片名（动态）：取决于人物卡或世界卡；单角色用其名，多角色=群聊，否则用当前世界卡 */
    fun currentCardLabel(): String {
        val role = selectedRoles.firstOrNull()
        val w = currentWorld
        return when {
            role != null && selectedRoles.size > 1 -> "群聊（" + selectedRoles.size + " 人" + (if (w.isNotBlank()) " · 世界：$w" else "") + "）"
            role != null && w.isNotBlank() -> "$role（世界：$w）"
            role != null -> role
            w.isNotBlank() -> "世界「$w」"
            else -> "默认"
        }
    }

    val theme = THEMES[themeIdx]
    val accent = ACCENTS[accentIdx].second
    val deps = DialogDeps(
        context = context,
        scope = scope,
        engine = engine,
        registry = registry,
        tree = tree,
        dice = dice,
        memory = memory,
        swipe = swipe,
        gal = gal,
        mech = mech,
        search = search,
        financial = financial,
        jp = jp,
        uiPlugin = uiPlugin,
        theme = theme,
        accent = accent,
        themeIdx = themeIdxS,
        accentIdx = accentIdxS,
        presetIdx = presetIdxS,
        currentWorld = currentWorldS,
        devMode = devModeS,
        humanize = humanizeS,
        styleGuard = styleGuardS,
        styleGuardLong = styleGuardLongS,
        autoTurn = autoTurnS,
        language = languageS,
        importCardLauncher = importCardLauncher,
        avatarPicker = avatarPicker,
        appIconPicker = appIconPicker,
        wallpaperPicker = wallpaperPicker,
        clearWallpaper = { clearWallpaper() },
        exportCardLauncher = exportCardLauncher,
        wsExportLauncher = wsExportLauncher,
        saveConfig = { saveConfig() },
        saveTree = { saveTree() },
        refreshChain = { ensureOpeningLine(); refreshChain() },
        saveGlobalRegex = { saveGlobalRegex(it) },
        reloadMech = { reloadMech() },
        reloadRolesFromDisk = { reloadRolesFromDisk() },
        reloadWorldsFromDisk = { reloadWorldsFromDisk() },
        personaFields = { personaFields() },
        personaDisplayName = { personaDisplayName() },
        userDisplayName = { userDisplayName() },
        treeFileFor = { treeFileFor() },
        stateFileFor = { stateFileFor() },
        listRoleSaves = { listRoleSaves(it) },
        createRoleSave = { r, l -> createRoleSave(r, l) },
        saveToRoleSlot = { r, s -> saveToRoleSlot(r, s) },
        loadRoleSlot = { r, s -> loadRoleSlot(r, s) },
        deleteRoleSlot = { r, s -> deleteRoleSlot(r, s) },
        renameRoleSlot = { r, s, l -> renameRoleSlot(r, s, l) },
        mechConfig = { mechConfig() },
        mechBattleConfig = { mechBattleConfig() },
        playerBattleConfig = { playerBattleConfig() },
        activeCardFace = { activeCardFace() },
        editMessage = { m, s -> editMessage(m, s) },
        toggleRoleUnlock = { toggleRoleUnlock(it) },
        wsRefreshLocal = { wsRefreshLocal() },
        wsLoadOnline = { wsLoadOnline() },
        wsSearchOnline = { wsSearchOnline() },
        wsLoadPlugins = { wsLoadPlugins() },
        wsInstallPlugin = { wsInstallPlugin(it) },
        wsDownloadSelected = { wsDownloadSelected() },
        wsLikeSelected = { wsLikeSelected() },
        wsDeleteSelected = { wsDeleteSelected() },
        wsUploadLocal = { wsUploadLocal() },
    )
    MaterialTheme(colorScheme = if (themeIdx == 1) lightColorScheme(primary = accent) else darkColorScheme(primary = accent, background = theme.bg)) {
        ModalNavigationDrawer(
            drawerState = drawerState,
            drawerContent = {
                ModalDrawerSheet {
                    Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        appIcon?.let {
                            Image(bitmap = it, contentDescription = null,
                                modifier = Modifier.size(24.dp).clip(RoundedCornerShape(6.dp)))
                            Spacer(Modifier.width(8.dp))
                        }
                        Text("DICK", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    }
                    Text(I18n.t("group_other", "其它项目"), Modifier.padding(horizontal = 16.dp, vertical = 4.dp), color = theme.muted, fontSize = 13.sp)
                    DrawerItem(I18n.t("item_settings", "设置")) { showSettings = true; scope.launch { drawerState.close() } }
                    DrawerItem(I18n.t("item_api", "🔑 API 配置")) { showApiSetup = true; scope.launch { drawerState.close() } }
                    DrawerItem("🎭 跑团（局域网）") { showTrpg = true; scope.launch { drawerState.close() } }
                    DrawerItem(I18n.t("item_share", "分享聊天记录")) { share(); scope.launch { drawerState.close() } }
                    DrawerItem("🗑 彻底清空历史", color = theme.danger) { showClearHistory = true; scope.launch { drawerState.close() } }
                    DrawerItem(I18n.t("btn_workshop", "🧰 创意工坊")) { showWorkshop = true; scope.launch { drawerState.close() } }
                }
            },
        ) {
            Column(
                Modifier.fillMaxSize()
                    .drawBehind {
                        val wp = wallpaper
                        if (wp != null) {
                            val iw = wp.width.toFloat(); val ih = wp.height.toFloat()
                            val sw = size.width; val sh = size.height
                            val sc = maxOf(sw / iw, sh / ih)  // cover 填充（裁边不拉伸）
                            val dw = iw * sc; val dh = ih * sc
                            drawImage(wp, dstOffset = IntOffset(((sw - dw) / 2).toInt(), ((sh - dh) / 2).toInt()), dstSize = IntSize(dw.toInt(), dh.toInt()))
                            drawRect(color = theme.bg.copy(alpha = 0.82f), size = size)  // 蒙层保证可读
                        } else {
                            drawRect(color = theme.bg, size = size)
                        }
                    }
                    .statusBarsPadding().navigationBarsPadding().padding(8.dp)
            ) {
                Row(Modifier.fillMaxWidth()) {
                    TextButton(onClick = { scope.launch { drawerState.open() } }) { Text("☰", fontSize = 20.sp) }
                    Spacer(Modifier.width(6.dp))
                    Text(PRESETS[presetIdx].name, Modifier.padding(top = 10.dp), color = theme.muted)
                    Spacer(Modifier.weight(1f))
                    FolderMenu(vm, deps)
                    TextButton(onClick = { showCardFace = true }) { IconText("🎴", fontSize = 16.sp) }
                    TextButton(onClick = { showBranches = true }) { IconText(I18n.t("btn_branch", "🌿 回档"), fontSize = 13.sp) }
                }
                Spacer(Modifier.height(6.dp))
                // 机制卡三栏（好感度栏 / 人物状态栏 / 战斗数值栏）
                mechTick
                val mechCfg = mech.config
                val mechSt = mech.state
                val mAff = mechCfg?.fields?.get("affection") as? J.Obj
                val mStCfg = mechCfg?.fields?.get("status") as? J.Obj
                val mFields = (mStCfg?.fields?.get("fields") as? J.Arr)?.items ?: emptyList()
                if (mechCfg != null && mechSt != null &&
                    (mAff?.fields?.get("enabled")?.bool() == true || mFields.isNotEmpty())
                ) {
                    val mStObj = mechSt.fields["status"] as? J.Obj
                    Column(
                        Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 4.dp),
                        verticalArrangement = Arrangement.spacedBy(3.dp),
                    ) {
                        // ① 好感度栏：进度条
                        if (mAff?.fields?.get("enabled")?.bool() == true) {
                            val hi = mAff.fields["max"]?.int() ?: 100
                            val lo = mAff.fields["min"]?.int() ?: 0
                            val cur = mechSt.fields["affection"]?.int() ?: mAff.fields["initial"]?.int() ?: 50
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("❤ 好感", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                                Box(Modifier.weight(1f).height(5.dp).clip(RoundedCornerShape(3.dp)).background(theme.bubble)) {
                                    Box(
                                        Modifier
                                            .fillMaxWidth((((cur - lo).toFloat()) / (hi - lo).coerceAtLeast(1)).coerceIn(0f, 1f))
                                            .height(5.dp).clip(RoundedCornerShape(3.dp)).background(accent),
                                    )
                                }
                                Text("$cur/$hi", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                            }
                        }
                        // ② 人物状态栏（enum 文字） / ③ 战斗数值栏（int 进度条）
                        mFields.forEach { f ->
                            val fo = f as? J.Obj ?: return@forEach
                            val key = fo.fields["key"]?.str() ?: return@forEach
                            val name = fo.fields["name"]?.str()?.takeIf { it.isNotBlank() } ?: key
                            val v = mStObj?.fields?.get(key) ?: fo.fields["initial"] ?: J.Str("")
                            if (fo.fields["type"]?.str() == "int") {
                                val mn = fo.fields["min"]?.int() ?: 0
                                val mx = fo.fields["max"]?.int() ?: 100
                                val curI = v.int()
                                if (mx > 1000) {
                                    // 大上限属性（atk/def/spd 等）：数值显示
                                    Text("⚔ $name：$curI", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                                } else {
                                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                        Text("⚔ $name", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                                        Box(Modifier.weight(1f).height(5.dp).clip(RoundedCornerShape(3.dp)).background(theme.bubble)) {
                                            Box(
                                                Modifier
                                                    .fillMaxWidth((((curI - mn).toFloat()) / (mx - mn).coerceAtLeast(1)).coerceIn(0f, 1f))
                                                    .height(5.dp).clip(RoundedCornerShape(3.dp)).background(theme.danger),
                                            )
                                        }
                                        Text("$curI/$mx", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                                    }
                                }
                            } else {
                                Text("$name：${v.str() ?: v.int()}", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                            }
                        }
                        // ④ 事件进度：玩家看不到进度就会觉得事件坏了。
                        // 数据由 MechanicsEngine.eventProgress() 提供（纯读，不改状态）。
                        // 不用额外的 state —— 上面已经读了 mechTick，重组时这里会重算。
                        val evItems = mech.eventProgress()
                        if (evItems.isNotEmpty()) {
                            Text(
                                "🎬 事件 " + evItems.count { it["fired"] == true } + "/" + evItems.size,
                                fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f),
                            )
                            evItems.forEach { e ->
                                val stt = e["state"] as? String ?: ""
                                val nm = e["name"] as? String ?: (e["id"] as? String ?: "")
                                val why = e["why"] as? String ?: ""
                                val mark = when (stt) {
                                    "fired" -> "✅"
                                    "cooling" -> "⏳"
                                    "blocked" -> "🔒"
                                    else -> "▶"
                                }
                                val shown: String = when {
                                    stt == "fired" -> "已触发" +
                                        (((e["times"] as? Int) ?: 1).let { if (it > 1) "（$it 次）" else "" })
                                    why.isNotBlank() -> why
                                    else -> "可以触发"
                                }
                                Row(
                                    Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                ) {
                                    Text("$mark $nm", fontSize = 11.sp,
                                         color = theme.text.copy(alpha = if (stt == "blocked" || stt == "cooling") 0.45f else 0.6f),
                                         modifier = Modifier.weight(1f))
                                    Text(shown, fontSize = 11.sp,
                                         color = theme.text.copy(alpha = if (stt == "blocked" || stt == "cooling") 0.45f else 0.6f))
                                }
                            }
                        }
                    }
                }
                // 战斗面板（属性 / 招式按钮 / buff）
                val bCfg = mech.battleConfig()
                val bUi = mech.battleUiState()
                val bAttrs = bUi?.fields?.get("attrs") as? J.Arr
                val bMoves = bCfg?.fields?.get("moves") as? J.Arr
                if (bCfg != null && bUi != null && bAttrs?.items?.isNotEmpty() == true) {
                    val bars = mutableListOf<J.Obj>()
                    val nums = mutableListOf<J.Obj>()
                    bAttrs.items.forEach { (it as? J.Obj)?.let { ao ->
                        val mx = ao.fields["max"]?.int() ?: 0
                        if (mx in 1..1000) bars.add(ao) else nums.add(ao)
                    } }
                    Column(
                        Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp),
                        verticalArrangement = Arrangement.spacedBy(2.dp),
                    ) {
                        // 玩家侧状态（同规格）
                        val pl = (bUi.fields["player"] as? J.Arr)
                        val plHp = pl?.items?.mapNotNull { it as? J.Obj }
                            ?.firstOrNull { it.fields["key"]?.str() == "hp" }?.fields?.get("value")?.int() ?: 0
                        if (pl?.items?.isNotEmpty() == true) {
                            Text("🧑 玩家 $plHp HP", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                        }
                        // ① 生命/灵力等 → 进度条（hp 红 / 其他蓝）
                        bars.forEach { ao ->
                            val key = ao.fields["key"]?.str() ?: return@forEach
                            val label = ao.fields["label"]?.str() ?: key
                            val value = ao.fields["value"]?.int() ?: 0
                            val mx = ao.fields["max"]?.int() ?: 1
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("⚔ $label", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                                Box(Modifier.weight(1f).height(5.dp).clip(RoundedCornerShape(3.dp)).background(theme.bubble)) {
                                    Box(
                                        Modifier.fillMaxWidth((value.toFloat() / mx).coerceIn(0f, 1f)).height(5.dp)
                                            .clip(RoundedCornerShape(3.dp))
                                            .background(if (key == "hp") theme.danger else accent),
                                    )
                                }
                                Text("$value/$mx", fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f))
                            }
                        }
                        // ② 无上限属性 → 数值（合并一行）
                        if (nums.isNotEmpty()) {
                            Text(
                                "⚔ " + nums.mapNotNull { a ->
                                    val key = a.fields["key"]?.str() ?: return@mapNotNull null
                                    val label = a.fields["label"]?.str() ?: key
                                    val value = a.fields["value"]?.int() ?: 0
                                    "$label:$value"
                                }.joinToString(" · "),
                                fontSize = 11.sp, color = theme.text.copy(alpha = 0.6f),
                            )
                        }
                        // ③ 招式按钮
                        if (bMoves?.items?.isNotEmpty() == true) {
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                bMoves.items.forEach { mv ->
                                    val mo = mv as? J.Obj ?: return@forEach
                                    val id = mo.fields["id"]?.str() ?: return@forEach
                                    val name = mo.fields["name"]?.str()?.takeIf { it.isNotBlank() } ?: id
                                    val desc = mo.fields["desc"]?.str() ?: ""
                                    OutlinedButton(
                                        onClick = { battleMove(id, name) },
                                        modifier = Modifier.border(1.dp, accent, RoundedCornerShape(14.dp)),
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
                                    ) {
                                        Text("⚔ $name", fontSize = 12.sp, color = theme.text, maxLines = 1)
                                    }
                                }
                            }
                        }
                        // ④ buff 徽章
                        val buffs = (mech.state?.fields?.get("buffs") as? J.Arr)
                        if (buffs?.items?.isNotEmpty() == true) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                buffs.items.forEach { bf ->
                                    val bo = bf as? J.Obj ?: return@forEach
                                    val bid = bo.fields["id"]?.str() ?: ""
                                    val turns = bo.fields["turns"]?.int() ?: 0
                                    Text("✨ $bid ×$turns", fontSize = 10.sp, color = Color(0xFFA78BFA))
                                }
                            }
                        }
                    }
                }
                // 聊天列表：吸底 + 直达底部按钮（微信式：滚离底部才出现）
                val listState = rememberLazyListState()
                var showJump by remember { mutableStateOf(false) }
                LaunchedEffect(listState) {
                    snapshotFlow { listState.layoutInfo }
                        .collect { info ->
                            val last = info.visibleItemsInfo.lastOrNull()?.index ?: -1
                            val total = info.totalItemsCount
                            // 距底部超过 2 条才显示直达按钮
                            showJump = last in 0 until total - 2
                        }
                }
                // 加载气泡：普通流式回复靠 streaming 非空；开局时流式文本还是空的，
                // 靠 openingLoading 单独撑住，否则开局那段等待期界面一片空白。
                fun showLoadingBubble(): Boolean =
                    busy && (streaming.isNotEmpty() || openingLoading)
                fun chatItemCount(): Int =
                    messages.size + (if (showLoadingBubble()) 1 else 0)
                // 在底部时新消息自动吸底；滚上去则不打扰
                LaunchedEffect(messages.size, busy, streaming, openingLoading) {
                    if (!showJump && chatItemCount() > 0) {
                        listState.scrollToItem(chatItemCount() - 1)
                    }
                }
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    LazyColumn(Modifier.fillMaxSize(), state = listState) {
                        items(messages) { m ->
                            Bubble(
                                m, theme.bubble, theme.text, accent, avatarCache,
                                onEdit = { editMsgTarget = it; editMsgText = it.content },
                                onRegen = { regenerate(it) },
                                onSwipe = { msg, delta -> switchSwipe(msg, delta) },
                            )
                        }
                        if (showLoadingBubble()) {
                            item {
                                // 开场还没吐字时显示「…」（角色像在酝酿第一句），
                                // 一旦有流式文本就换成实时内容
                                val shown = if (streaming.isEmpty()) "…" else streaming + "…"
                                Bubble(
                                    ChatMsg(if (selectedRoles.size == 1) selectedRoles.first() else "AI", shown),
                                    theme.bubble, theme.text, accent, avatarCache,
                                    onEdit = {}, onRegen = {}, onSwipe = { _, _ -> },
                                )
                            }
                        }
                    }
                    if (showJump) {
                        Surface(
                            onClick = {
                                scope.launch { listState.animateScrollToItem(maxOf(0, chatItemCount() - 1)) }
                            },
                            modifier = Modifier
                                .align(Alignment.BottomEnd)
                                .padding(end = 14.dp, bottom = 14.dp)
                                .size(44.dp),
                            shape = CircleShape,
                            color = theme.bubble,
                            shadowElevation = 6.dp,
                        ) {
                            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                Icon(
                                    painterResource(R.drawable.ic_download),
                                    contentDescription = "到底部",
                                    modifier = Modifier.size(20.dp),
                                    tint = accent,
                                )
                            }
                        }
                    }
                }
                if (pendingImage != null) {
                    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                        Image(pendingImage!!.bmp, contentDescription = null, modifier = Modifier.width(64.dp).height(64.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(I18n.t("img_selected", "已选图片"), Modifier.padding(top = 22.dp), fontSize = 12.sp, color = theme.muted)
                        Spacer(Modifier.weight(1f))
                        TextButton(onClick = { pendingImage = null }) { Text(I18n.t("btn_remove", "✕ 移除"), fontSize = 12.sp) }
                    }
                }
                if (showQuickPanel) {
                    Surface(color = theme.bubble, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                        Column(Modifier.padding(6.dp)) {
                            Row {
                                QuickChip("📷 " + I18n.t("qc_image", "图片")) { showQuickPanel = false; imagePicker.launch("image/*") }
                                QuickChip("🔍 搜索") { insertCmd("/搜索 ") }
                                QuickChip("🔍 深搜") { insertCmd("/深搜 ") }
                                QuickChip("🎲 骰子") { insertCmd("/r 2d6") }
                            }
                            Row {
                                QuickChip("🧠 记忆") { insertCmd("/memory recall 3") }
                                QuickChip("🎮 选项") { showQuickPanel = false; gal.manualGenerate() }
                            }
                            // 财报：折叠区块，仅启用财报模式才显示（隐藏 + 收起，避免铺满面板）
                            if (financial.enabled) {
                                FoldHead("📊 财报", finFolded, { finFolded = !finFolded })
                                if (!finFolded) {
                                    Row {
                                        QuickChip("📊 个股") { insertCmd("/股票 ") }
                                        QuickChip("🔍 全市场") { insertCmd("/全市场 ") }
                                        QuickChip("🔗 联动") { insertCmd("/联动 ") }
                                        QuickChip("📈 爬政策") { insertCmd("/财报 爬取") }
                                    }
                                    Row {
                                        QuickChip("📚 入库") { insertCmd("/财报 入库") }
                                        QuickChip("📚 检索") { insertCmd("/财报 检索 ") }
                                        QuickChip("🌐 爬网页") { insertCmd("/爬取 ") }
                                    }
                                }
                            }
                            Row {
                                // 卡片自带快捷回复（高级设置）优先，再跟全局
                                val cardQrs = selectedRoles.firstOrNull()?.let { advancedByRole[it] }
                                    ?.fields?.get("card_quick_replies") as? J.Arr
                                (cardQrs?.items?.mapNotNull { q ->
                                    val qo = q as? J.Obj ?: return@mapNotNull null
                                    val l = qo.fields["label"]?.str() ?: return@mapNotNull null
                                    l to (qo.fields["text"]?.str() ?: "")
                                } ?: emptyList()).forEach { (label, t) ->
                                    QuickChip(label) { showQuickPanel = false; input = t }
                                }
                                quickReplies.forEach { (label, t) ->
                                    QuickChip(label) { showQuickPanel = false; input = t }
                                }
                            }
                        }
                    }
                }
                // Galgame 选项行（选择肢按钮）
                if (gal.enabled && (gal.choices.isNotEmpty() || gal.loading)) {
                    Column(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                        if (gal.loading) {
                            Text("⏳ 正在生成选项…", fontSize = 12.sp, color = theme.muted, modifier = Modifier.padding(start = 4.dp))
                        }
                        gal.choices.chunked(2).forEach { rowItems ->
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(vertical = 1.dp)) {
                                rowItems.forEach { c ->
                                    TextButton(
                                        onClick = { pickChoice(c) },
                                        modifier = Modifier
                                            .weight(1f)
                                            .border(1.dp, accent, RoundedCornerShape(16.dp)),
                                    ) {
                                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                            Text(c.text, fontSize = 13.sp, color = theme.text, maxLines = 2)
                                            val eff = buildString {
                                                c.result?.let { append(it) }
                                                c.aff?.let { if (isNotEmpty()) append(" · "); append("❤").append(if (it > 0) "+" else "").append(it).append("%") }
                                                c.st?.forEach { (k, v) ->
                                                    if (isNotEmpty()) append(" · ")
                                                    append(k).append(":").append(v)
                                                }
                                            }
                                            if (eff.isNotEmpty()) {
                                                Text(eff, fontSize = 10.sp, color = theme.text.copy(alpha = 0.6f), maxLines = 1)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        if (gal.choices.isNotEmpty()) {
                            TextButton(onClick = { gal.manualGenerate() }, modifier = Modifier.align(Alignment.End)) {
                                IconText("🔄 重新生成", fontSize = 12.sp)
                            }
                        }
                    }
                }
                Spacer(Modifier.height(6.dp))
                Row(Modifier.fillMaxWidth()) {
                    TextButton(onClick = { showQuickPanel = !showQuickPanel }) { IconText(if (showQuickPanel) "✕" else "➕", fontSize = 20.sp) }
                    OutlinedTextField(
                        value = input,
                        onValueChange = { input = it },
                        label = { Text(I18n.t("input_label", "输入消息（/ 开头为命令）")) },
                        modifier = Modifier.weight(1f),
                        maxLines = 4,
                    )
                    Spacer(Modifier.width(6.dp))
                    Button(onClick = ::send, enabled = !busy) { Text(I18n.t("btn_send", "发送")) }
                }
            }
        }
    }

    // 首次启动引导框
    if (showGuide) {
        Box(Modifier.fillMaxSize().background(Color(0xCC0A0C10)).clickable { }, contentAlignment = Alignment.Center) {
            Surface(
                modifier = Modifier.fillMaxWidth().padding(22.dp),
                shape = RoundedCornerShape(16.dp),
                color = theme.bubble,
                shadowElevation = 12.dp,
            ) {
                val guide = listOf(
                    "👋 欢迎使用 DICK" to "装好即聊的角色扮演聊天室：手机 / 电脑进度互通，支持角色卡、世界书、回档、内置游戏。",
                    "⚙️ 配置模型" to "设置 → 填 API Key、选模型商（DeepSeek 官方 / 免费链 / Ollama 本地）。免费链可留空直接聊。",
                    "🎭 选择角色" to "角色列表勾选即可开聊（多选 = 群聊，@角色名 指定发言）；可新建或导入酒馆卡 v1/v2/v3/PNG。",
                    "💬 开聊" to "输入消息发送；↻ 重生成、◀▶ 滑条、✏️ 编辑。➕ 面板有骰子 / 记忆 / GAL 选项 / 快捷回复。",
                    "🌿 进阶玩法" to "回档：主线平铺、分支收纳；GAL 选项点选即演；世界书平行世界；存档自动守护。",
                )
                Column(Modifier.padding(20.dp)) {
                    Text(guide[guideStep].first, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(10.dp))
                    Text(guide[guideStep].second, fontSize = 13.sp, lineHeight = 22.sp)
                    Spacer(Modifier.height(16.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { showGuide = false; saveConfig() }) { Text("跳过", fontSize = 13.sp) }
                        Spacer(Modifier.weight(1f))
                        if (guideStep > 0) {
                            TextButton(onClick = { guideStep-- }) { Text("上一步", fontSize = 13.sp) }
                        }
                        Button(onClick = {
                            if (guideStep >= guide.size - 1) { showGuide = false; saveConfig() }
                            else guideStep++
                        }) { Text(if (guideStep >= guide.size - 1) "开始使用 🚀" else "下一步", fontSize = 13.sp) }
                    }
                }
            }
        }
    }


    // ---------- 对话框（已迁至 Dialogs.kt，全体认 vm + deps 协议） ----------
    SettingsDialog(vm, deps)
    TimeScalePanel(vm, deps)   // ⏳ 时间流速：独立展开面板（自托管，读 vm.showTimeDial）
    TrpgDialog(vm, deps)
    CardFaceDialog(vm, theme.muted)
    RolesDialog(vm, deps)
    DeleteConfirmDialog(vm, theme.muted, theme.danger, ::deleteRole, ::deleteWorld)
    RoleEditDialog(vm, deps)
    PersonaDialog(vm, deps)
    AvatarCropDialog(vm, deps)
    WorldsDialog(vm, deps)
    WorldEditDialog(vm, deps)
    EditMsgDialog(vm, deps)
    WorkshopDialog(vm, deps)

    // ---------- 彻底清空历史（红色 · 二次确认） ----------
    if (showClearHistory) {
        var alsoClearMemory by remember { mutableStateOf(false) }
        AlertDialog(
            onDismissRequest = { showClearHistory = false },
            title = { Text("⚠️ 彻底清空历史", color = theme.danger) },
            text = {
                Column {
                    Text("将删除当前角色「" + currentCardLabel() + "」的全部聊天记录。")
                    Spacer(Modifier.height(6.dp))
                    Text("此操作不可恢复。确定要清空吗？", fontSize = 12.sp, color = theme.muted)
                    Text("（机制卡的状态/好感度也会一起重置。）", fontSize = 11.sp, color = theme.muted)
                    Spacer(Modifier.height(8.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = alsoClearMemory, onCheckedChange = { alsoClearMemory = it })
                        Text("同时清空记忆链（memory）", fontSize = 12.sp, modifier = Modifier.padding(top = 14.dp))
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    clearHistory(alsoClearMemory)
                    showClearHistory = false
                }) { Text("🗑 彻底清空", color = theme.danger) }
            },
            dismissButton = { TextButton(onClick = { showClearHistory = false }) { Text("取消") } },
        )
    }

    BranchesDialog(vm, tree, mech, accent, { saveTree() }, { refreshChain() }, { gal.restoreOptionsFromNode(it) })
}