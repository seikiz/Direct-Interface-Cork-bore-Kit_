package com.dick.app

/** 聊天屏的状态容器：把原来散在 ChatScreen 里的 86 个状态与 15 个对象收拢。
 *  下一步：68 个局部函数与 UI 分区都从这里取状态。 */
import android.content.Intent
import android.graphics.BitmapFactory
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.runtime.snapshots.SnapshotStateMap
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
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
import com.dick.core.MechanicsEngine
import com.dick.core.MessageNode
import com.dick.core.RegexEngine
import com.dick.core.RoleSaves
import com.dick.core.SaveFile
import com.dick.core.SaveSlot
import com.dick.core.SpaceCore
import com.dick.core.StyleGuard
import com.dick.core.TextGuard
import com.dick.core.TimeScale
import com.dick.core.TreeData
import com.dick.core.TreeStore
import com.dick.core.Workshop
import com.dick.core.WorldBook
import com.dick.core.WorldData
import com.dick.core.WorldEntry
import com.dick.core.WorldPacks
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
import kotlin.random.Random
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

internal class ChatState(
    internal val vm: ChatViewModel,
    scope: CoroutineScope,
    engine: ChatEngine,
    registry: PluginRegistry,
    tree: ChatTree,
    worldCards: SnapshotStateMap<String, J.Obj>,
    dice: DicePlugin,
    memory: MemoryPlugin,
    swipe: SwipePlugin,
    gal: GalgamePlugin,
    mech: MechanicsEngine,
    search: SearchPlugin,
    financial: FinancialPlugin,
    jp: JpPlugin,
    uiPlugin: UiPlugin,
    speakCounts: SnapshotStateMap<String, Int>,
) {
    internal val scope = scope
    internal val engine = engine
    internal val registry = registry
    internal val tree = tree
    internal val worldCards = worldCards
    internal val dice = dice
    internal val memory = memory
    internal val swipe = swipe
    internal val gal = gal
    internal val mech = mech
    internal val search = search
    internal val financial = financial
    internal val jp = jp
    internal val uiPlugin = uiPlugin
    internal val speakCounts = speakCounts
    val messages get() = vm.messages
    val quickReplies get() = vm.quickReplies
    val avatarCache get() = vm.avatarCache
    var avatarTarget by vm.avatarTarget
    var appIcon by vm.appIcon
    var wallpaper by vm.wallpaper
    var cropBitmap by vm.cropBitmap
    var cropScale by vm.cropScale
    var cropDx by vm.cropDx
    var cropDy by vm.cropDy
    val roles get() = vm.roles
    val worlds get() = vm.worlds
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
    val apiKeysMap get() = vm.apiKeysMap
    var themeIdx by vm.themeIdx
    var accentIdx by vm.accentIdx
    val savedStates get() = vm.savedStates
    var presetIdx by vm.presetIdx
    var budgetIdx by vm.budgetIdx
    var selectedRoles by vm.selectedRoles
    var selectedWorlds by vm.selectedWorlds
    var currentWorld by vm.currentWorld
    val roleUnlocked get() = vm.roleUnlocked
    val advancedByRole get() = vm.advancedByRole
    var devMode by vm.devMode
    var humanize by vm.humanize
    var styleGuard by vm.styleGuard
    var styleGuardLong by vm.styleGuardLong
    var showGuide by vm.showGuide
    var guideStep by vm.guideStep
    var persona by vm.persona
    var showPersonaEdit by vm.showPersonaEdit
    var autoTurn by vm.autoTurn
    var speakReplies by vm.speakReplies
    var input by vm.input
    var busy by vm.busy
    var streaming by vm.streaming
    var openingLoading by vm.openingLoading
    var showSettings by vm.showSettings
    var timeScale by vm.timeScale
    var showRoles by vm.showRoles
    var showWorlds by vm.showWorlds
    var roleEditName by vm.roleEditName
    var language by vm.language
    val sysMsgs get() = vm.sysMsgs
    val nodeImages get() = vm.nodeImages
    val worldEntries get() = vm.worldEntries
    var showWorldEdit by vm.showWorldEdit
    var editMsgTarget by vm.editMsgTarget
    var editMsgText by vm.editMsgText
    var showBranches by vm.showBranches
    var showClearHistory by vm.showClearHistory
    var exportTarget by vm.exportTarget
    var showWorkshop by vm.showWorkshop
    var wsTabOnline by vm.wsTabOnline
    var wsTabPlugin by vm.wsTabPlugin
    var wsPlugins by vm.wsPlugins
    var wsLocalPlugins by vm.wsLocalPlugins
    var wsInstallingId by vm.wsInstallingId
    val wsLocalRoles get() = vm.wsLocalRoles
    val wsLocalWorlds get() = vm.wsLocalWorlds
    var wsLocalType by vm.wsLocalType
    var wsLocalIdx by vm.wsLocalIdx
    var wsDetail by vm.wsDetail
    var wsServerInput by vm.wsServerInput
    var wsKeyInput by vm.wsKeyInput
    var wsStatus by vm.wsStatus
    var wsStatusIcon by vm.wsStatusIcon
    val wsOnlineList get() = vm.wsOnlineList
    var wsOnlineIdx by vm.wsOnlineIdx
    var wsSearchInput by vm.wsSearchInput
    var wsExportTarget by vm.wsExportTarget
    var providerMenu by vm.providerMenu
    var modelMenu by vm.modelMenu
    var customModelInput by vm.customModelInput
    var showQuickPanel by vm.showQuickPanel
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌