package com.dick.app

import android.content.Intent
import android.graphics.BitmapFactory
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.random.Random

/**
 * 输入栏上方的状态行：忙时显示「生成中 · N 秒」，空闲时整行不占位。
 *
 * 为什么不做成聊天气泡：用户明确要求"不要出现在对话框里"，
 * 这行贴着输入框，像 Grok 的配额提示那样只给一行轻量信息；
 * 也不进历史树 —— 忙是可重试的瞬时状态，不是剧情。
 *
 * 只认主题令牌（muted / accent），无 emoji，无字面色字面量。
 */
@Composable
fun ChatScreen(vm: ChatViewModel, theme: ThemeSpec, accent: Color) {
    lateinit var st: ChatState
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
    val mechTickState = remember { mutableStateOf(0) }
    var mechTick by mechTickState   // 机制状态栏刷新信号
    val search = remember { SearchPlugin() }
    val financial = remember { FinancialPlugin() }
    val jp = remember { JpPlugin() }
    val uiPlugin = remember { UiPlugin() }

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
    // 主题 / 强调色 / 预设 / 各开关 / 语言：**唯一状态源在 vm**（2026-11 状态收口）。
    // 屏与引擎都只 by vm.xxx 读写同一份 —— 不再各自 rememberSaveable 一份副本
    // （副本的经典事故：设置屏里改了开关，App 里那份还是旧值，观感上像「设置没生效」）。
    var themeIdx by vm.themeIdx
    var accentIdx by vm.accentIdx
    val savedStates = vm.savedStates
    var presetIdx by vm.presetIdx
    var selectedRoles by vm.selectedRoles
    var currentWorld by vm.currentWorld
    val lastSpeakerState = remember { mutableStateOf<String?>(null) }
    var lastSpeaker by lastSpeakerState
    // 公平计数：谁发言越少越可能被选中（防双人死循环/饿死后排，与 PC 端一致）
    val speakCounts = remember { mutableStateMapOf<String, Int>() }
    val roleUnlocked = vm.roleUnlocked
    val advancedByRole = vm.advancedByRole
    var devMode by vm.devMode
    var humanize by vm.humanize
    var styleGuard by vm.styleGuard
    var styleGuardLong by vm.styleGuardLong
    var showGuide by vm.showGuide
    var guideStep by vm.guideStep
    var persona by vm.persona
    var autoTurn by vm.autoTurn
    var speakReplies by vm.speakReplies
    var input by vm.input
    var busy by vm.busy
    var streaming by vm.streaming
    var openingLoading by vm.openingLoading
    // 时间流速：改成 vm 里的状态，设置弹窗直接读改，避免两处副本不同步
    var timeScale by vm.timeScale
    var showApiSetup by vm.showApiSetup  // 抽屉「API 配置」独立入口
    var showTrpg by vm.showTrpg          // 抽屉「跑团（局域网）」
    var showCardFace by vm.showCardFace  // 「卡面」查看弹窗
    var pendingDelete by vm.pendingDelete // (名称, "role"/"world") 待确认删除
    val pendingImageState = remember { mutableStateOf<PendingImg?>(null) }
    var pendingImage by pendingImageState
    val drawerState = rememberDrawerState(DrawerValue.Closed)
    var language by vm.language

    // 酒馆三功能状态：树外横幅 / 节点图片 / 世界书条目 / 编辑与分支
    val sysMsgs = vm.sysMsgs
    val nodeImages = vm.nodeImages
    val worldEntries = vm.worldEntries
    var showClearHistory by vm.showClearHistory
    var exportTarget by vm.exportTarget
    // ---- 创意工坊状态 ----
    val wsLocalRoles = vm.wsLocalRoles
    val wsLocalWorlds = vm.wsLocalWorlds
    var wsLocalType by vm.wsLocalType
    var wsServerInput by vm.wsServerInput
    var wsKeyInput by vm.wsKeyInput
    // 工坊状态行 = 纯文本 + 图标名（→check_circle、→error…）。渲染点在 WorkshopScreen
    // 的 DickTag，这里只负责把两样一起设好 —— 文案里不再出现 emoji 字符。
    var wsExportTarget by vm.wsExportTarget

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
                withContext(Dispatchers.Main) { st.wsSetStatus(msg) }
            }
        }
    }

    /** 头像裁剪：解码 → 居中正方形 → 256x256 PNG */

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


    /** 群聊说话人兜底（修复「回复显示成 AI」）：模型没输出 [角色名]: 前缀时，
     *  用本轮选中的发言角色 lastSpeaker 归属（对齐 PC 端 _group_speaker 兜底）。 */

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
                    // 2026-11 首启向导：**没配到可用 Key、且当前不是免 Key 厂商** → 弹 3 步向导。
                    // 免 Key 厂商（OVH 免费链 / 本地 Ollama）不需要 Key，不打扰；
                    // 「稍后再说」会把 providerId 切到免费链并落盘，下次启动就不再弹。
                    val _p = PROVIDERS.firstOrNull { it.id == vm.providerId.value }
                    if (vm.apiKey.value.isBlank() && _p?.free != true) vm.showApiSetup.value = true
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
        engine.relayBase = relayUrl.trim().ifBlank { BUILTIN_RELAY }.ifBlank { null }
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
        // 界面语言：配置里有就用配置的；没有就按系统判定（中文→zh、日文→ja、英文→en）；
        // 认不出的值一律当 zh（与 I18n.normalize / 桌面端 i18n.set_lang 同一条规矩）
        language = I18n.normalize(language.ifBlank { I18n.detect() })
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
        val treeFile = st.treeFileFor()
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
        val cardId = syncCardId(selectedRoles)
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
                        if (syncCardId(selectedRoles) != cardId) return@withContext
                        // 关键：用「当前」本地 ts 再比对（可能已被用户新回复推进），而不用启动时
                        // 定格的旧 localTreeTs —— 否则慢网络拉取会在回复之后落地，把整树回滚成旧版
                        val curTs = try { TreeStore.load(st.treeFileFor()).treeTs } catch (_: Exception) { localTreeTs }
                        if (curTs == null || serverTs > curTs) {
                            tree.loadData(TreeData.fromJson(serverTree))
                            tree.fixLeaf()
                            st.saveTree()
                            st.refreshChain()
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
            mech.stateFile = st.stateFileFor()  // 第三个文件夹：机制状态 JSON（与树解耦）
            mech.reload(st.mechConfig(), tree, reset = true)
            mech.battleCfg = st.mechBattleConfig()
        mech.playerCfg = st.playerBattleConfig()
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
        st.refreshChain()
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
        gal.mechConfigProvider = { st.mechConfig() }
        gal.mechStateProvider = { mech.state }
        gal.mechEventProvider = { mech.lastEvent }
        gal.saveTreeHook = { st.saveTree() }  // 选项写进树后立即落盘（供回档复原）
        for ((name, en) in savedStates) {
            registry.plugins.firstOrNull { it.name == name }?.enabled = en
        }
    }

    // ============================================================
    //  生活层 / 空间层：把界面状态接到 core 的钩子上（ChatBridge）
    // ============================================================
    // 世界卡 JSON：空间层要从 params 里读年代与地图（世界卡默认**替换**年代地图，
    // 想叠加得在 space 里写 "merge": true —— 与电脑端同一条规矩）。

    // 角色卡 JSON：生活层读 advanced.life（年代/口味/忌口），空间层读 advanced.space。

    /** 剥掉 [loc:…]/[ploc:…] 并记账；返回可直接显示/入树的文本。记账交给 io 线（写盘）。 */

    ChatBridge.chainProvider = { st.engineChain() }
    ChatBridge.roleNameProvider = { st.currentSpeaker() }
    ChatBridge.roleJsonProvider = { st.currentRoleJson() }
    ChatBridge.worldJsonProvider = { st.currentWorldJson() }
    // 空间层的"没显式给倍率时用哪一档"：手机端没有 time_scale.json 的读取逻辑，
    // 这里接到界面上那份（与电脑端读 time_scale 等价）。
    SpaceCore.scaleProvider = { TimeScale.current }

    var doSend: (String, ImageBitmap?, String?) -> Unit = { _, _, _ -> }
    var showQuickPanel by vm.showQuickPanel
    val finFoldedState = remember { mutableStateOf(true) }
    var finFolded by finFoldedState   // 加号面板「财报」折叠区块默认收起
fun wsRefreshLocal() {
        wsLocalRoles.clear(); wsLocalRoles.addAll(Workshop.localRoles())
        wsLocalWorlds.clear(); wsLocalWorlds.addAll(Workshop.localWorlds())
    }

    st = androidx.compose.runtime.remember { ChatState(
        vm, scope, engine, registry, tree, worldCards, dice, memory, swipe, gal, mech,
        search, financial, jp, uiPlugin, speakCounts,
        mechTickState, lastSpeakerState, pendingImageState, finFoldedState,
        context, tts, { t, bmp, d -> doSend(t, bmp, d) }, { ensureOpeningLine() }, { wsRefreshLocal() },
    ) }
    val insertCmd: (String) -> Unit = { cmd ->
        input = if (input.isBlank()) cmd else input + " " + cmd
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
                val sys = st.sysPrompt(firstMes) + 10.toChar() + 10.toChar() +
                    openingInstruction(firstMes, st.userDisplayName())
                engine.send(
                    chain = st.engineChain(),
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
                            st.landAssistantReply(reply, null, firstMes)
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
                            st.fallbackOpening(role, firstMes)
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
        val expanded = expandMacros(cleanText, st.userDisplayName(), selectedRoles.firstOrNull() ?: "AI", currentWorld)
        val processed = registry.onMessageSend(expanded) ?: return@doSend
        // 正则管道（user 作用域）：存储前应用 → 树里存转换后文本
        // 位置标注（[ploc:家/厨房]）在入树前收掉：它是"你到哪了"，不该显示给玩家，
        // 但要记进空间状态（玩家位置也一样会算路费）。
        val sent = st.consumeSpaceMoves(applyRegex(processed, "user", selectedRoles, advancedByRole, persona), st.currentSpeaker().ifBlank { "她" })
        input = ""
        busy = true
        streaming = ""
        val treeContent = if (visionNote == null) sent else "用户发送了一张图片。视觉模型对图片的描述：\n" + visionNote + "\n\n用户输入：" + sent
        val meta = J.Obj()
        meta.fields["speaker"] = if (persona.isBlank()) J.Null else J.Str(st.userDisplayName())
        mech.state?.let { meta.fields["ms"] = mech.snapshot() ?: J.Null }
        val parentId = tree.addNode("user", treeContent, parentId = tree.currentLeafId, metadata = meta)
        if (image != null) nodeImages[parentId] = image
        pendingImage = null
        st.refreshChain()
        financial.activePreset = PRESETS[presetIdx].name
        swipe.chain = st.engineChain()
        var sys = st.sysPrompt(sent)
        // 机制卡：待触发事件注入（只进请求，不入历史树）
        mech.pendingEvent?.let { ev ->
            sys += "\n\n【事件触发：" + (ev.fields["name"]?.str() ?: ev.fields["id"]?.str() ?: "") + "】\n" +
                (ev.fields["prompt"]?.str() ?: "")
            mech.pendingEvent = null
        }
        swipe.systemPrompt = sys
        engine.send(
            chain = st.engineChain(),
            systemPrompt = sys,
            // 与开局处同一个取舍：stripTags 会写 mech state，只能主线程串行（见上面的长注释）
            onStream = { full -> scope.launch(Dispatchers.Main) { streaming = ChatBridge.takeMoves(mech.stripTags(full, apply = false)).first } },
            onResponse = { reply, _ ->
                scope.launch(Dispatchers.Main) {
                    // 落地逻辑与「开局演出」共用同一个函数，避免两处走偏
                    st.landAssistantReply(reply, parentId, sent)
                    if (autoTurn && selectedRoles.size > 1) {
                        val hint = listOf(com.dick.core.MessageNode(
                            role = "user",
                            content = "（请让另一位角色继续对话）",
                        ))
                        val chain = st.engineChain() + hint
                        val sp = st.sysPrompt(processed)
                        // 关键：complete 是阻塞 HTTP，必须在后台线程跑（否则卡死主线程 → 未响应/只有重启）
                        scope.launch(Dispatchers.IO) {
                            val extra = try { engine.complete(chain, sp) } catch (e: Exception) { null }
                            scope.launch(Dispatchers.Main) {
                                if (!extra.isNullOrBlank()) {
                                    val p2 = parseSpeaker(extra, selectedRoles)
                                    // 群聊自动接话的第二条回复同样要收位置标注（否则标签会漏到界面上）
                                    val p2clean = st.consumeSpaceMoves(p2.second, st.currentSpeaker().ifBlank { "她" })
                                    val m3 = J.Obj()
                                    m3.fields["speaker"] = st.resolveSpeaker(p2.first)?.let { J.Str(it) } ?: J.Null
                                    tree.addNode("assistant", StyleGuard.guard(p2clean, styleGuard, styleGuardLong), parentId, m3)
                                    st.saveTree()
                                    st.refreshChain()
                                    st.checkEnding()  // autoTurn 第二条回复后也判结局
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
                    st.refreshChain()
                    streaming = ""
                    busy = false
                }
            },
        )
    }

    // 装了世界卡包以后让界面重扫（插件在 io 线上跑命令，界面更新回主线程）
    ChatBridge.worldsChanged = { scope.launch(Dispatchers.Main) { st.reloadWorldsFromDisk() } }

    // 主题解析：「跟随系统」这一项在这里按系统深浅落到暗/浅（与 DickTheme 同一个口径，
    // 所以下面 deps.theme 拿到的就是实际生效的那套色，不必等 MaterialTheme 生效）
    // 强调色也分暗/浅两版：浅色主题下 #60a5fa 当文字色只有 2.5:1（见 design/tokens.json）
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
        // 应用级偏好一律直接指向 vm 里那一份（不再有 App 局部副本；见 ChatViewModel 偏好区）
        themeIdx = vm.themeIdx,
        accentIdx = vm.accentIdx,
        presetIdx = vm.presetIdx,
        currentWorld = vm.currentWorld,
        devMode = vm.devMode,
        humanize = vm.humanize,
        styleGuard = vm.styleGuard,
        styleGuardLong = vm.styleGuardLong,
        autoTurn = vm.autoTurn,
        language = vm.language,
        importCardLauncher = importCardLauncher,
        avatarPicker = avatarPicker,
        appIconPicker = appIconPicker,
        wallpaperPicker = wallpaperPicker,
        clearWallpaper = { st.clearWallpaper() },
        exportCardLauncher = exportCardLauncher,
        wsExportLauncher = wsExportLauncher,
        saveConfig = { st.saveConfig() },
        saveTree = { st.saveTree() },
        refreshChain = { ensureOpeningLine(); st.refreshChain() },
        saveGlobalRegex = { st.saveGlobalRegex(it) },
        reloadMech = { st.reloadMech() },
        reloadRolesFromDisk = { st.reloadRolesFromDisk() },
        reloadWorldsFromDisk = { st.reloadWorldsFromDisk() },
        personaFields = { st.personaFields() },
        personaDisplayName = { st.personaDisplayName() },
        userDisplayName = { st.userDisplayName() },
        roleJsonFor = { st.roleJsonOf(it) },
        worldJsonFor = { st.currentWorldJson() },
        treeFileFor = { st.treeFileFor() },
        stateFileFor = { st.stateFileFor() },
        listRoleSaves = { st.listRoleSaves(it) },
        createRoleSave = { r, l -> st.createRoleSave(r, l) },
        saveToRoleSlot = { r, s -> st.saveToRoleSlot(r, s) },
        loadRoleSlot = { r, s -> st.loadRoleSlot(r, s) },
        deleteRoleSlot = { r, s -> st.deleteRoleSlot(r, s) },
        renameRoleSlot = { r, s, l -> st.renameRoleSlot(r, s, l) },
        mechConfig = { st.mechConfig() },
        mechBattleConfig = { st.mechBattleConfig() },
        playerBattleConfig = { st.playerBattleConfig() },
        activeCardFace = { st.activeCardFace() },
        editMessage = { m, s -> st.editMessage(m, s) },
        toggleRoleUnlock = { st.toggleRoleUnlock(it) },
        wsRefreshLocal = { wsRefreshLocal() },
        wsLoadOnline = { st.wsLoadOnline() },
        wsSearchOnline = { st.wsSearchOnline() },
        wsLoadPlugins = { st.wsLoadPlugins() },
        wsInstallPlugin = { st.wsInstallPlugin(it) },
        wsDownloadSelected = { st.wsDownloadSelected() },
        wsLikeSelected = { st.wsLikeSelected() },
        wsDeleteSelected = { st.wsDeleteSelected() },
        wsUploadLocal = { st.wsUploadLocal() },
    )
    // 统一入口：套 MaterialTheme（只映射 primary/背景/表面/错误/描边，不整套替换语义色），
    // 同时把当前配色放进 LocalDickPalette，组件里不必层层传色。
    ChatThemeBody(
        st, theme, accent, drawerState,
        onOpenDrawer = { scope.launch { drawerState.open() } },
        showApiSetup = vm.showApiSetup,
        showTrpg = vm.showTrpg,
        showCardFace = vm.showCardFace,
        deps = deps,
        imagePicker = imagePicker,
        insertCmd = insertCmd,
    )

    ChatOverlays(
        st = st, theme = theme, deps = deps,
        showGuide = showGuide, guideStep = guideStep, showClearHistory = showClearHistory,
        onStep = { guideStep = it },
        onCloseGuide = { showGuide = false; st.saveConfig() },
        onDismissClear = { showClearHistory = false },
        onConfirmClear = { also -> st.clearHistory(also); showClearHistory = false },
    )
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌
