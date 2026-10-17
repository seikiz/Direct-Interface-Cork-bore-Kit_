package com.dick.app

import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.graphics.ImageBitmap
import androidx.lifecycle.ViewModel
import com.dick.core.J
import com.dick.core.WorldEntry

/**
 * ChatViewModel —— App 状态的"协议"（唯一事实源）。
 *
 * 把所有 App 级 UI 状态集中到这里；组件各自持有一份委托引用
 * （如 `var busy by vm.busy`），大家通过同一份状态"听懂"彼此，
 * 而不必各自 remember 一份。ViewModel 生命随 Activity 存活 → 转屏/重建不丢状态。
 */
class ChatViewModel : ViewModel() {
    // ---- 聊天<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌/引擎 ----
    var mechTick = mutableStateOf(0)
    val messages = mutableStateListOf<ChatMsg>()
    val quickReplies = mutableStateListOf<Pair<String, String>>()
    val sysMsgs = mutableStateListOf<ChatMsg>()

    // ---- 角色/世界 ----
    val roles = mutableStateListOf<Pair<String, String>>()
    val worlds = mutableStateListOf<Pair<String, String>>()
    var selectedRoles = mutableStateOf(setOf<String>())
    var selectedWorlds = mutableStateOf(setOf<String>())

    // ---- 模型/API ----
    var apiKey = mutableStateOf("")
    var model = mutableStateOf("deepseek-flash")
    var baseUrl = mutableStateOf("https://api.deepseek.com")
    var proxy = mutableStateOf("")
    var relayUrl = mutableStateOf(BUILTIN_RELAY)
    var stopInput = mutableStateOf("")
    var regexInput = mutableStateOf("")
    var tempInput = mutableStateOf("")
    var topPInput = mutableStateOf("")
    var providerId = mutableStateOf("deepseek")
    var ollamaOnline = mutableStateOf(false)
    var budgetIdx = mutableStateOf(0)
    /** 软件时间流速（世界那边比现实快多少倍）。持久化在 config.json。 */
    var timeScale = mutableStateOf(com.dick.core.TimeScale.DEFAULT_SCALE)
    var providerMenu = mutableStateOf(false)
    var modelMenu = mutableStateOf(false)
    var customModelInput = mutableStateOf("")

    // ---- 应用级偏好（2026-11 收口：原来散在 App() 的 rememberSaveable 里，屏各存一份副本）----
    // 为什么收进来：设置屏改一个开关，引擎/顶栏/聊天要立刻读到同一份；两份副本 = 迟早不同步。
    // 语义与原来一致：启动时 loadConfig() 覆盖默认值，保存时 saveConfig() 写出（config.json）。
    var themeIdx = mutableStateOf(0)                              // THEMES 下标
    var accentIdx = mutableStateOf(0)                             // ACCENTS 下标
    var presetIdx = mutableStateOf(0)                             // PRESETS 下标
    var currentWorld = mutableStateOf("")                         // 当前世界卡（单选）
    var devMode = mutableStateOf(false)                           // 开发者模式（解锁高级设置）
    var humanize = mutableStateOf(true)                           // 去 AI 味
    var styleGuard = mutableStateOf(true)                         // 风格闸
    var styleGuardLong = mutableStateOf(false)                    // 长句模式
    var autoTurn = mutableStateOf(false)                          // 群聊自动接话
    var language = mutableStateOf("")                             // 界面语言（I18n.lang 的落盘值）

    // ---- 界面开关 ----
    var showGuide = mutableStateOf(false)
    var guideStep = mutableStateOf(0)
    var persona = mutableStateOf("")
    var showPersonaEdit = mutableStateOf(false)
    var speakReplies = mutableStateOf(false)
    var input = mutableStateOf("")
    var busy = mutableStateOf(false)
    var streaming = mutableStateOf("")
    /** 「正在加载开场白」。
     *  为什么需要单独一个状态：加载气泡的条件是 `busy && streaming 非空`，
     *  而开局时流式文本还是空的 —— 界面会一片空白。普通发消息时用户自己那句话说出来了、
     *  知道在等；开局本来就是空的，空白就等于「坏了」。所以开局要单独给一个加载态。 */
    var openingLoading = mutableStateOf(false)
    var showSettings = mutableStateOf(false)
    /**  时间流速独立面板（不再塞在设置弹窗里 —— 见 Dialogs.kt 的 TimeScalePanel） */
    var showTimeDial = mutableStateOf(false)
    /** 生活 / 空间 / 世界卡库设置面板（见 LifeSpaceSettings.kt） */
    var showLifeSpace = mutableStateOf(false)
    var showApiSetup = mutableStateOf(false)
    /**  API 教程面板（2026-11）：与网页端 web/screens/api_guide.html 同一份内容 */
    var showApiGuide = mutableStateOf(false)
    var showTrpg = mutableStateOf(false)
    var showCardFace = mutableStateOf(false)
    var showRoles = mutableStateOf(false)
    var showWorlds = mutableStateOf(false)
    var rolesWorldsExpanded = mutableStateOf(false)
    var editMsgText = mutableStateOf("")
    var showBranches = mutableStateOf(false)
    var showWorkshop = mutableStateOf(false)
    var showClearHistory = mutableStateOf(false)  // 彻底清空历史（二次确认）

    // ---- 工坊 ----
    var wsTabOnline = mutableStateOf(false)
    var wsTabPlugin = mutableStateOf(false)
    var wsInstallingId = mutableStateOf("")
    val wsLocalRoles = mutableStateListOf<String>()
    val wsLocalWorlds = mutableStateListOf<String>()
    var wsLocalType = mutableStateOf("角色卡")
    var wsLocalIdx = mutableStateOf(-1)
    var wsPreview = mutableStateOf("")
    var wsServerInput = mutableStateOf("")
    var wsKeyInput = mutableStateOf("")
    var wsStatus = mutableStateOf("")
    // 状态行的图标名（Material Symbols）：文案只留纯文本，图标由产生状态的那一处点名，
    // 渲染点（WorkshopScreen 的 DickTag）直接接过去 —— 界面文案里不再出现 emoji 字符。
    var wsStatusIcon = mutableStateOf<String?>(null)
    val wsOnlineList = mutableStateListOf<J.Obj>()
    var wsOnlineIdx = mutableStateOf(-1)
    var wsSearchInput = mutableStateOf("")

    // ---- 加号面板 ----
    var showQuickPanel = mutableStateOf(false)
    var finFolded = mutableStateOf(true)

    // ---- 删除确认 / 角色管理依赖 ----
    var pendingDelete = mutableStateOf<Pair<String, String>?>(null) // (名称, "role"/"world")
    val roleUnlocked = mutableStateMapOf<String, Boolean>()
    val advancedByRole = mutableStateMapOf<String, J.Obj>()
    val avatarCache = mutableStateMapOf<String, ImageBitmap?>()
    val apiKeysMap = mutableStateMapOf<String, String>()
    val savedStates = mutableStateMapOf<String, Boolean>()
    val nodeImages = mutableStateMapOf<String, ImageBitmap?>()
    val worldEntries = mutableStateMapOf<String, List<WorldEntry>>()

    // ---- 对话框/裁剪等瞬态状态（随 ViewModel 存活，转屏不丢） ----
    var roleEditName = mutableStateOf<String?>(null)        // 正在编辑的角色名（null=关；""=新建）
    var showWorldEdit = mutableStateOf<String?>(null)       // world 编辑目标（null=关；""=新建）
    var editMsgTarget = mutableStateOf<ChatMsg?>(null)      // 正在编辑的消息
    var exportTarget = mutableStateOf<Pair<String, String>?>(null) // (角色名, "json"/"png")
    var avatarTarget = mutableStateOf<String?>(null)        // 正在换头像的目标名字
    var wsExportTarget = mutableStateOf<String?>(null)      // 工坊导出文件名
    var wsPlugins = mutableStateOf<List<J.Obj>>(emptyList())
    var wsLocalPlugins = mutableStateOf<List<String>>(emptyList())
    var appIcon = mutableStateOf<ImageBitmap?>(null)
    var wallpaper = mutableStateOf<ImageBitmap?>(null)  // 聊天背景壁纸（null=默认主题底色）
    var cropBitmap = mutableStateOf<android.graphics.Bitmap?>(null)
    var cropScale = mutableStateOf(1f)
    var cropDx = mutableStateOf(0f)
    var cropDy = mutableStateOf(0f)
    var cropStagePx = mutableStateOf(0f)
}
