package com.dick.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.activity.compose.ManagedActivityResultLauncher
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.AppEnv
import com.dick.core.ChatEngine
import com.dick.core.ChatTree
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.MechanicsEngine
import com.dick.core.TreeStore
import com.dick.core.TrpgSession
import com.dick.core.WorldData
import com.dick.core.WorldEntry
import com.dick.core.Workshop
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Dialogs.kt —— DialogBlock（自 App.kt 迁出，全体认 ChatViewModel 协议）。
 * 新加对话框 = 在这里新写一个 @Composable fun XxxDialog(vm, ...) 即可。
 */

/** 删除确认（角色/世界） */
@Composable
fun DeleteConfirmDialog(
    vm: ChatViewModel,
    muted: Color,
    danger: Color,
    onDeleteRole: (String) -> Unit,
    onDeleteWorld: (String) -> Unit,
) {
    val pd = vm.pendingDelete.value ?: return
    val (name, kind) = pd
    val label = if (kind == "role") "角色卡「$name」" else "世界卡「$name」"
    AlertDialog(
        onDismissRequest = { vm.pendingDelete.value = null },
        title = { Text("⚠️ 确认删除") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("确定删除$label 吗？")
                Spacer(Modifier.height(6.dp))
                Text(
                    if (kind == "role") "(会一并删除它的聊天记录，不可恢复。)" else "(会一并删除它的世界书内容，不可恢复。)",
                    fontSize = 12.sp, color = muted,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = {
                if (kind == "role") onDeleteRole(name) else onDeleteWorld(name)
                vm.pendingDelete.value = null
            }) { Text("🗑️ 删除", color = danger) }
        },
        dismissButton = { TextButton(onClick = { vm.pendingDelete.value = null }) { Text("取消") } },
    )
}

/** 卡面查看（角色卡面可视化） */
@Composable
fun CardFaceDialog(vm: ChatViewModel, muted: Color) {
    if (vm.showCardFace.value) {
        val role = vm.selectedRoles.value.firstOrNull()
        val html = role?.let { vm.advancedByRole[it]?.fields?.get("card_face")?.str() } ?: ""
        AlertDialog(
            onDismissRequest = { vm.showCardFace.value = false },
            title = { IconText("🎴 卡面") },
            text = {
                if (html.isNotBlank()) {
                    HtmlCard(html, Modifier.fillMaxWidth().height(420.dp))
                } else {
                    Column(Modifier.padding(8.dp)) {
                        Text("该角色未设置卡面。", fontSize = 13.sp, color = muted)
                        Text("在「角色 → ✏️ 编辑 → 开发者模式 → 卡面」导入 HTML 或自行编辑。", fontSize = 12.sp, color = muted)
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { vm.showCardFace.value = false }) { Text(I18n.t("btn_cancel", "取消")) } },
        )
    }
}

/** 回档（树状回溯：主线平铺 + 分支收纳 + 点击跳回） */
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
    var showBranches by vm.showBranches
    if (showBranches) {
        AlertDialog(
            onDismissRequest = { showBranches = false },
            title = { IconText("🌿 回档（二维分支 · 双指缩放/拖动 · 点节点跳到那里）") },
            text = { TreeGraph(vm, tree, mech, accent, saveTree, refreshChain, restoreOptions) },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { showBranches = false }) { Text(I18n.t("btn_cancel", "取消")) } },
        )
    }
}

/** 二维分支树图节点（布局用：x=叶子列号，y=深度） */
private class GNodeV(
    val id: String, val x: Float, val y: Float, val role: String, val content: String,
    val isOption: Boolean, val isCurrent: Boolean, val onPath: Boolean, val options: List<String>,
)

/** 由 ChatTree 算出一棵"叶子居中"的二维布局：返回节点列表 + 父子连线 */
private fun computeTreeLayout(tree: ChatTree, leafId: String?): Pair<List<GNodeV>, List<Pair<GNodeV, GNodeV>>> {
    val nodes = tree.nodes
    val root = tree.rootId ?: return emptyList<GNodeV>() to emptyList<Pair<GNodeV, GNodeV>>()
    val subtreeW = HashMap<String, Float>()
    val xPos = HashMap<String, Float>()
    val depthM = HashMap<String, Int>()
    fun dfsDepth(id: String, d: Int) {
        depthM[id] = d
        nodes[id]?.childrenIds?.forEach { dfsDepth(it, d + 1) }
    }
    dfsDepth(root, 0)
    fun calcW(id: String): Float {
        val node = nodes[id] ?: return 0f
        subtreeW[id] = if (node.childrenIds.isEmpty()) 1f else node.childrenIds.fold(0f) { acc, c -> acc + calcW(c) }
        return subtreeW[id]!!
    }
    calcW(root)
    var leaf = 0f
    fun assignX(id: String): Float {
        val node = nodes[id] ?: return 0f
        xPos[id] = if (node.childrenIds.isEmpty()) leaf++ else {
            val xs = node.childrenIds.map { assignX(it) }
            (xs.first() + xs.last()) / 2f
        }
        return xPos[id]!!
    }
    assignX(root)
    val path = HashSet<String>()
    var p = leafId; var guard = 0
    while (p != null && guard++ < 1000) { path.add(p); p = nodes[p]?.parentId }
    val out = ArrayList<GNodeV>()
    val edges = ArrayList<Pair<GNodeV, GNodeV>>()
    fun build(id: String): GNodeV {
        val node = nodes[id]!!
        val meta = node.metadata as? J.Obj
        val isOption = meta?.fields?.get("gal_options") != null
        val opts = (meta?.fields?.get("gal_options") as? J.Arr)?.items?.mapNotNull { (it as? J.Obj)?.fields?.get("text")?.str() } ?: emptyList()
        val gn = GNodeV(id, xPos[id]!!, depthM[id]!!.toFloat(), node.role,
            node.content.replace('\n', ' ').take(16), isOption, id == leafId, id in path, opts)
        out.add(gn)
        node.childrenIds.forEach { child -> edges.add(gn to build(child)) }
        return gn
    }
    build(root)
    return out to edges
}

/** 结局预设文本 → endings 数组（每行 id|结局名|事件链,逗号|好感≥|隐藏|描述） */
private fun parseEndings(text: String): J.Arr {
    val arr = J.Arr()
    text.split("\n").forEach { line ->
        val t = line.trim()
        if (t.isEmpty()) return@forEach
        val p = t.split("|")
        if (p.size < 2) return@forEach
        val id = p[0].trim(); if (id.isEmpty()) return@forEach
        val e = J.Obj()
        e.fields["id"] = J.Str(id)
        e.fields["name"] = J.Str(p[1].trim().ifEmpty { id })
        val whenObj = J.Obj()
        p.getOrNull(2)?.trim()?.takeIf { it.isNotEmpty() }?.let { chain ->
            val ids = chain.split(",", "，").map { it.trim() }.filter { it.isNotEmpty() }
            val a = J.Arr(); ids.forEach { a.items.add(J.Str(it)) }
            whenObj.fields["events_chain"] = a
        }
        p.getOrNull(3)?.trim()?.toIntOrNull()?.let { whenObj.fields["aff_ge"] = J.Num(it.toDouble()) }
        val hidden = (p.getOrNull(4)?.trim() ?: "") in setOf("1", "yes", "hidden", "隐藏", "藏", "true")
        if (hidden) e.fields["hidden"] = J.Bool(true)
        if (whenObj.fields.isNotEmpty()) e.fields["when"] = whenObj
        p.drop(5).joinToString("|").trim().takeIf { it.isNotEmpty() }?.let { e.fields["desc"] = J.Str(it) }
        arr.items.add(e)
    }
    return arr
}

/** endings 数组 → 结局预设文本（与 parseEndings 对称） */
private fun endingsToText(arr: J.Arr?): String {
    return arr?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { e ->
        val id = e.fields["id"]?.str() ?: return@mapNotNull null
        val name = e.fields["name"]?.str() ?: id
        val whenObj = e.fields["when"] as? J.Obj
        val chain = (whenObj?.fields?.get("events_chain") as? J.Arr)?.items?.mapNotNull { it.str() }?.joinToString(",") ?: ""
        val affGe = whenObj?.fields?.get("aff_ge")?.int()?.toString() ?: ""
        val hidden = if ((e.fields["hidden"] as? J.Bool)?.v == true) "1" else ""
        val desc = e.fields["desc"]?.str() ?: ""
        listOf(id, name, chain, affGe, hidden, desc).joinToString("|")
    }?.joinToString("\n") ?: ""
}

/** 二维分支树图：叶子居中布局 + 双指缩放/拖动 + 选项点标 🎮/描边 + 点击即回档 */
@Composable
fun TreeGraph(vm: ChatViewModel, tree: ChatTree, mech: MechanicsEngine, accent: Color, saveTree: () -> Unit, refreshChain: () -> Unit, restoreOptions: (String?) -> Unit) {
    val (nodes, edges) = remember(tree) { computeTreeLayout(tree, tree.currentLeafId) }
    val xSpacing = 150f; val ySpacing = 96f
    val maxX = nodes.maxOfOrNull { it.x } ?: 0f
    val maxY = nodes.maxOfOrNull { it.y } ?: 0f
    val worldW = maxOf(1f, maxX * xSpacing + 160f)
    val worldH = maxOf(1f, maxY * ySpacing + 120f)
    var scale by remember { mutableStateOf(0.8f) }
    var panX by remember { mutableStateOf(0f) }
    var panY by remember { mutableStateOf(0f) }
    var viewW by remember { mutableStateOf(1) }
    var viewH by remember { mutableStateOf(1) }
    LaunchedEffect(viewW, viewH) {
        val s = minOf(viewW / worldW, viewH / worldH).coerceIn(0.25f, 2.2f)
        scale = s
        panX = (viewW - worldW * s) / 2f
        panY = (viewH - worldH * s) / 2f
    }
    val ctx = LocalContext.current
    var branchMode by remember { mutableStateOf(false) }
    Column {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { branchMode = false }) { Text("🔀 回档", fontSize = 12.sp, fontWeight = if (!branchMode) FontWeight.Bold else null, color = if (!branchMode) accent else Color.Unspecified) }
            TextButton(onClick = { branchMode = true }) { Text("✏️ 建分支", fontSize = 12.sp, fontWeight = if (branchMode) FontWeight.Bold else null, color = if (branchMode) accent else Color.Unspecified) }
            Spacer(Modifier.weight(1f))
            Text(if (branchMode) "点节点=从这点继续 · 下一条会分出新分支" else "点节点=跳回那里", fontSize = 10.sp, color = Color(0xFF6B7280))
        }
    Box(
        Modifier.fillMaxWidth().height(470.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(Color(0xFF0F1115))
            .onSizeChanged { viewW = it.width; viewH = it.height }
            .pointerInput(Unit) {
                detectTransformGestures { _, pan, zoom, _ ->
                    scale = (scale * zoom).coerceIn(0.25f, 3f)
                    panX += pan.x; panY += pan.y
                }
            }
    ) {
        Canvas(Modifier.fillMaxSize()) {
            fun s(wx: Float, wy: Float): Offset = Offset(wx * xSpacing * scale + panX, wy * ySpacing * scale + panY)
            edges.forEach { (a, b) ->
                val c = if (b.onPath) Color(0xFF9AA1AB) else Color(0xFFD4D7DC)
                drawLine(c, s(a.x, a.y), s(b.x, b.y), strokeWidth = 2f)
            }
        }
        nodes.forEach { n ->
            val px = n.x * xSpacing * scale + panX
            val py = n.y * ySpacing * scale + panY
            val chipW = 138f; val chipH = 42f
            // 灰白成就（MC progress 风）配色
            val bg = when {
                n.isCurrent -> Color(0xFFffffff)
                n.isOption -> Color(0xFFF0F1F3)
                n.onPath -> Color(0xFFFBFBFC)
                else -> Color(0xFFE9EBEF)
            }
            val border = when {
                n.isCurrent -> Color(0xFF9AA1AB)   // 当前：深灰描边（已解锁）
                n.isOption -> Color(0xFF9AA1AB)
                n.onPath -> Color(0xFFD4D7DC)
                else -> Color(0xFFC9CCD2)
            }
            val tc = when {
                n.isCurrent -> Color(0xFF3A3F46)
                n.onPath -> Color(0xFF4A4F57)
                else -> Color(0xFF7B828B)
            }
            Box(
                Modifier
                    .offset { IntOffset((px - chipW / 2).toInt(), (py - chipH / 2).toInt()) }
                    .size(chipW.dp, chipH.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(bg)
                    .border(2.dp, border, RoundedCornerShape(8.dp))
                    .then(if (n.isCurrent) Modifier.border(1.dp, Color(0xFFffffff), RoundedCornerShape(8.dp)) else Modifier)
                    .clickable {
                        tree.setCurrentLeaf(n.id)
                        mech.restore(tree, n.id)
                        vm.mechTick.value++
                        saveTree()
                        restoreOptions(n.id)
                        refreshChain()
                        vm.showBranches.value = false
                        if (branchMode) Toast.makeText(ctx, "已定位到这里 · 下一条消息会从这里分出新分支", Toast.LENGTH_SHORT).show()
                    },
                contentAlignment = Alignment.CenterStart,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 6.dp)) {
                    // 成就图标框（灰白像素格）
                    val ic = if (n.role == "user") "〔你〕" else if (n.role == "system") "⚙" else if (n.isOption) "▣" else "〔AI〕"
                    Box(
                        Modifier.size(width = 26.dp, height = 26.dp)
                            .clip(RoundedCornerShape(5.dp))
                            .background(Color(0xFFE7E9EC))
                            .border(1.dp, Color(0xFFCFD3D8), RoundedCornerShape(5.dp)),
                        contentAlignment = Alignment.Center,
                    ) { Text(ic, fontSize = 8.sp, color = tc) }
                    Spacer(Modifier.width(5.dp))
                    Column {
                        Text((if (n.isOption) "▣ " else "") + n.content.ifBlank { "（空）" },
                            fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, color = tc)
                        Text(if (n.isCurrent) "当前进度" else if (n.isOption) "选项节点" else (if (n.onPath) "当前剧情线" else "分支剧情"),
                            fontSize = 8.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Color(0xFF9AA1AB))
                    }
                }
            }
            // 选项点：把存过的选项作为可点小签显示（点=从该选项新建分支）
            n.options.take(3).forEachIndexed { i, opt ->
                val ox = px - chipW / 2
                val oy = py + chipH / 2 + 4 + i * 20
                Box(
                    Modifier
                        .offset { IntOffset(ox.toInt(), oy.toInt()) }
                        .width(chipW.dp).height(20.dp)
                        .clip(RoundedCornerShape(4.dp))
                        .background(Color(0xFFF0F1F3))
                        .border(1.dp, Color(0xFFBCC1C8), RoundedCornerShape(4.dp))
                        .clickable {
                            tree.setCurrentLeaf(n.id)
                            saveTree()
                            restoreOptions(n.id)
                            refreshChain()
                            vm.input.value = opt
                            vm.showBranches.value = false
                            Toast.makeText(ctx, "已选「$opt」 · 发送即可从这里分出新分支", Toast.LENGTH_SHORT).show()
                        },
                    contentAlignment = Alignment.CenterStart,
                ) {
                    Text("▸ " + opt, fontSize = 9.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        color = Color(0xFF6B7078), modifier = Modifier.padding(horizontal = 4.dp))
                }
            }
        }
    }
    }
}

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
    // rememberSaveable 应用级偏好（转屏/进程重建保留）
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
    val treeFileFor: () -> File,
    val stateFileFor: () -> File,
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

/** 设置（API 配置 + 主设置） */
@Composable
fun SettingsDialog(vm: ChatViewModel, deps: DialogDeps) {
    val context = deps.context
    val theme = deps.theme
    val accent = deps.accent
    val engine = deps.engine
    val registry = deps.registry
    val gal = deps.gal
    val uiPlugin = deps.uiPlugin
    val apiKeysMap = vm.apiKeysMap
    var providerId by vm.providerId
    var baseUrl by vm.baseUrl
    var model by vm.model
    var apiKey by vm.apiKey
    var ollamaOnline by vm.ollamaOnline
    var customModelInput by vm.customModelInput
    var proxy by vm.proxy
    var relayUrl by vm.relayUrl
    var stopInput by vm.stopInput
    var regexInput by vm.regexInput
    var tempInput by vm.tempInput
    var topPInput by vm.topPInput
    var budgetIdx by vm.budgetIdx
    var speakReplies by vm.speakReplies
    var showPersonaEdit by vm.showPersonaEdit
    var themeIdx by deps.themeIdx
    var accentIdx by deps.accentIdx
    var presetIdx by deps.presetIdx
    var devMode by deps.devMode
    var humanize by deps.humanize
    var styleGuard by deps.styleGuard
    var styleGuardLong by deps.styleGuardLong
    var autoTurn by deps.autoTurn
    var language by deps.language
    val personaDisplayName = deps.personaDisplayName
    val saveConfig = deps.saveConfig
    val saveGlobalRegex = deps.saveGlobalRegex
    val appIconPicker = deps.appIconPicker
    var appIcon by vm.appIcon
    val wallpaperPicker = deps.wallpaperPicker
    val clearWallpaper = deps.clearWallpaper
    var wallpaper by vm.wallpaper
    if (vm.showApiSetup.value) {
    AlertDialog(
        onDismissRequest = { vm.showApiSetup.value = false },
        title = { Text("🔑 API 配置（模型商 / 模型 / Key）") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text("模型商", fontSize = 13.sp, color = theme.muted)
                val curProvider = PROVIDERS.firstOrNull { it.id == providerId }
                PROVIDERS.forEach { p ->
                    TextButton(
                        onClick = { providerId = p.id; baseUrl = p.baseUrl; model = p.models.first(); apiKey = apiKeysMap[p.id] ?: "" },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text((if (p.id == providerId) "● " else "○ ") + p.name + (if (p.free) "（免 Key）" else "") +
                            (if (p.id == "ollama") (if (ollamaOnline) " · 本地已连接" else " · 本地未检测到") else ""),
                            fontSize = 13.sp, color = if (p.id == providerId) accent else Color.Unspecified)
                    }
                }
                TextButton(onClick = {
                    val p = PROVIDERS.firstOrNull { it.id == providerId }
                    if (p != null) { try { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(p.buyUrl))) } catch (_: Exception) {} }
                }) { IconText(I18n.t("btn_buy", "🔑 去官网注册/充值"), fontSize = 12.sp) }
                Spacer(Modifier.height(6.dp))
                Text("模型", fontSize = 13.sp, color = theme.muted)
                (curProvider?.models ?: emptyList()).forEach { m ->
                    TextButton(onClick = { model = m }, modifier = Modifier.fillMaxWidth()) {
                        Text((if (m == model) "● " else "○ ") + m, fontSize = 12.sp,
                            color = if (m == model) accent else Color.Unspecified)
                    }
                }
                if (model.isNotBlank() && model !in (curProvider?.models ?: emptyList())) {
                    TextButton(onClick = {}, modifier = Modifier.fillMaxWidth()) {
                        Text("● " + model + "（当前）", fontSize = 12.sp, color = accent)
                    }
                }
                OutlinedTextField(value = customModelInput, onValueChange = { customModelInput = it },
                    label = { Text("自定义模型 ID") }, singleLine = true)
                TextButton(onClick = { if (customModelInput.isNotBlank()) model = customModelInput.trim() }) { Text("使用自定义模型", fontSize = 12.sp) }
                OutlinedTextField(value = apiKey, onValueChange = { apiKey = it },
                    label = { Text(if (curProvider?.free == true) "API Key（免 Key，可留空）" else "API Key") }, singleLine = true,
                    enabled = curProvider?.free != true)
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(value = baseUrl, onValueChange = { baseUrl = it }, label = { Text("Base URL（选模型商自动填）") }, singleLine = true)
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(value = proxy, onValueChange = { proxy = it }, label = { Text("代理（可选，通道不通时填，如 http://127.0.0.1:7890）") }, singleLine = true)
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(value = relayUrl, onValueChange = { relayUrl = it }, label = { Text("内置代理通道（直连失败自动走中转）") }, singleLine = true)
                Text(if (engine.relayOn) "● 中转通道已启用（直连失败已自动切换）" else "○ 直连模式（直连失败自动走中转）",
                    fontSize = 11.sp, color = theme.muted)
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(value = stopInput, onValueChange = { stopInput = it },
                    label = { Text("停止序列（指令模板，逗号分隔，如 <|im_end|>, </s>）") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                apiKeysMap[providerId] = apiKey.trim()
                engine.apiKey = apiKey.trim()
                engine.model = model
                engine.baseUrl = baseUrl.trim().ifBlank { "https://api.deepseek.com" }
                engine.proxy = proxy.trim().ifBlank { null }
                val effRelay = relayUrl.trim().ifBlank { BUILTIN_RELAY }
                if (engine.relayBase != effRelay) engine.relayOn = false
                engine.relayBase = effRelay
                engine.stopSequences = parseStops(stopInput)
                engine.allowEmptyKey = PROVIDERS.firstOrNull { it.id == providerId }?.free == true
                saveConfig()
                val k = apiKey.trim()
                Thread {
                    try { Workshop.pushApi(k, baseUrl.trim().ifBlank { "https://api.deepseek.com" }, model, providerId) } catch (_: Exception) {}
                }.start()
                vm.showApiSetup.value = false
            }) { Text(I18n.t("btn_save", "保存")) }
        },
        dismissButton = { TextButton(onClick = { vm.showApiSetup.value = false }) { Text(I18n.t("btn_cancel", "取消")) } },
    )
    }
    if (vm.showSettings.value) {
    AlertDialog(
        onDismissRequest = { vm.showSettings.value = false },
        title = { Text(I18n.t("dlg_settings", "DICK · 设置")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Spacer(Modifier.height(6.dp))
                OutlinedTextField(value = regexInput, onValueChange = { regexInput = it },
                    label = { Text("🔤 正则规则（每行 id|名称|正则|替换|作用域；ai/user/both）\n例：rm_star|动作去星号|\\*([^*]+)\\*|（$1）|both") },
                    minLines = 4)
                Spacer(Modifier.height(6.dp))
                Row {
                    OutlinedTextField(value = tempInput, onValueChange = { tempInput = it },
                        label = { Text("温度（留空=默认）") }, singleLine = true, modifier = Modifier.weight(1f))
                    Spacer(Modifier.width(6.dp))
                    OutlinedTextField(value = topPInput, onValueChange = { topPInput = it },
                        label = { Text("top_p（留空=默认）") }, singleLine = true, modifier = Modifier.weight(1f))
                }
                Spacer(Modifier.height(6.dp))
                Button(onClick = {
                    language = if (language == "en") "zh" else "en"
                    I18n.lang = language
                }) { Text(I18n.t("lang_title", "语言") + "：" + (if (language == "en") "English" else "中文")) }
                Spacer(Modifier.height(6.dp))
                Button(onClick = { presetIdx = (presetIdx + 1) % PRESETS.size }) { Text(I18n.t("lbl_preset", "预设：") + PRESETS[presetIdx].name) }
                Spacer(Modifier.height(6.dp))
                Button(onClick = { budgetIdx = (budgetIdx + 1) % BUDGETS.size }) { Text(I18n.budgetLabel(BUDGETS[budgetIdx].first)) }
                Spacer(Modifier.height(6.dp))
                OutlinedButton(onClick = { appIconPicker.launch("image/*") }, modifier = Modifier.fillMaxWidth()) {
                    IconText("🎨 应用图标" + (if (appIcon != null) "（已设置，点击更换）" else "（点击从相册选择）"), fontSize = 13.sp)
                }
                Spacer(Modifier.height(6.dp))
                OutlinedButton(onClick = { wallpaperPicker.launch("image/*") }, modifier = Modifier.fillMaxWidth()) {
                    IconText("🖼️ 壁纸（聊天背景）" + (if (wallpaper != null) "（已设置，点击更换）" else "（点击从相册选择）"), fontSize = 13.sp)
                }
                if (wallpaper != null) {
                    Spacer(Modifier.height(4.dp))
                    OutlinedButton(onClick = { clearWallpaper() }, modifier = Modifier.fillMaxWidth()) {
                        IconText("🧹 恢复默认背景", fontSize = 13.sp)
                    }
                }
                Spacer(Modifier.height(6.dp))
                OutlinedButton(onClick = { showPersonaEdit = true }, modifier = Modifier.fillMaxWidth()) {
                    IconText("🧑 " + I18n.t("btn_persona_card", "玩家角色卡") + (if (personaDisplayName().isNotBlank()) "：" + personaDisplayName() else ""), fontSize = 13.sp)
                }
                Spacer(Modifier.height(6.dp))
                Row { Checkbox(checked = autoTurn, onCheckedChange = { autoTurn = it }); Text(I18n.t("chk_auto", "群聊自动接话"), Modifier.padding(top = 14.dp)) }
                Row { Checkbox(checked = speakReplies, onCheckedChange = { speakReplies = it }); Text(I18n.t("chk_tts", "朗读 AI 回复（系统 TTS）"), Modifier.padding(top = 14.dp)) }
                Row { Checkbox(checked = devMode, onCheckedChange = { devMode = it }); Text("🔧 开发者模式（解锁角色卡高级设置/内置游戏）", Modifier.padding(top = 14.dp)) }
                Row { Checkbox(checked = humanize, onCheckedChange = { humanize = it }); Text("🧍 去 AI 味（具体细节/生活有变化/口语不完美/引用共同记忆）", Modifier.padding(top = 14.dp)) }
                Row { Checkbox(checked = styleGuard, onCheckedChange = { styleGuard = it }); Text("🎛 风格闸（去文学化漂移：生活词/比喻→事实/拆长句）", Modifier.padding(top = 8.dp)) }
                Row { Checkbox(checked = styleGuardLong, onCheckedChange = { styleGuardLong = it }); Text("🌊 长句模式（不拆长句，允许更流畅/文学化表达）", Modifier.padding(top = 4.dp)) }
                Spacer(Modifier.height(10.dp))
                var foldPlugins by remember { mutableStateOf(false) }
                FoldHead("🔌 插件", foldPlugins, onToggle = { foldPlugins = !foldPlugins })
                if (foldPlugins) {
                for (p in registry.plugins) {
                    var enabled by remember(p) { mutableStateOf(p.enabled) }
                    Row {
                        Checkbox(checked = enabled, onCheckedChange = { enabled = it; p.enabled = it })
                        Column(Modifier.padding(top = 10.dp)) {
                            Text(p.name + " v" + p.version, fontSize = 13.sp)
                            Text(p.description, fontSize = 11.sp, color = Color(0xFF6B7280))
                        }
                    }
                    if (p === uiPlugin && enabled) {
                        Row {
                            Button(onClick = { themeIdx = (themeIdx + 1) % THEMES.size }) { Text(I18n.t("lbl_theme", "主题：") + THEMES[themeIdx].name, fontSize = 12.sp) }
                            Spacer(Modifier.width(8.dp))
                            Button(onClick = { accentIdx = (accentIdx + 1) % ACCENTS.size }) { Text(I18n.t("lbl_accent", "强调色：") + ACCENTS[accentIdx].first, fontSize = 12.sp) }
                        }
                        Spacer(Modifier.height(6.dp))
                    }
                    if (p === gal && enabled) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("每轮选项：", fontSize = 12.sp)
                            TextButton(onClick = { gal.count = maxOf(2, gal.count - 1) }) { Text("−", fontSize = 16.sp) }
                            Text(gal.count.toString(), fontSize = 13.sp)
                            TextButton(onClick = { gal.count = minOf(4, gal.count + 1) }) { Text("＋", fontSize = 16.sp) }
                            Spacer(Modifier.width(12.dp))
                            Checkbox(checked = gal.auto, onCheckedChange = { gal.auto = it })
                            Text("自动生成", fontSize = 12.sp, modifier = Modifier.padding(top = 14.dp))
                        }
                        Spacer(Modifier.height(4.dp))
                    }
                }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                apiKeysMap[providerId] = apiKey.trim()
                engine.apiKey = apiKey.trim()
                engine.model = model
                engine.baseUrl = baseUrl.trim().ifBlank { "https://api.deepseek.com" }
                engine.proxy = proxy.trim().ifBlank { null }
                val effRelay = relayUrl.trim().ifBlank { BUILTIN_RELAY }
                if (engine.relayBase != effRelay) engine.relayOn = false  // 改了中转地址 → 回到直连优先
                engine.relayBase = effRelay
                engine.stopSequences = parseStops(stopInput)
                engine.temperature = tempInput.toFloatOrNull()
                engine.topP = topPInput.toFloatOrNull()
                engine.allowEmptyKey = PROVIDERS.firstOrNull { it.id == providerId }?.free == true
                saveGlobalRegex(regexInput)
                saveConfig()
                val k = apiKey.trim()
                Thread {
                    try {
                        Workshop.pushApi(k, baseUrl.trim().ifBlank { "https://api.deepseek.com" }, model, providerId)
                    } catch (_: Exception) {}
                }.start()
                vm.showSettings.value = false
            }) { Text(I18n.t("btn_save", "保存")) }
        },
        dismissButton = { TextButton(onClick = { vm.showSettings.value = false }) { Text(I18n.t("btn_cancel", "取消")) } },
    )
    }
}

/** 跑团（去中心化 · 房间管理） */
@Composable
fun TrpgDialog(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    if (vm.showTrpg.value) {
    val context = deps.context
    val engine = deps.engine
    var sessions by remember { mutableStateOf(listOf<J.Obj>()) }   // 发现的房间
    var base by remember { mutableStateOf("") }                    // 主机地址（连到某房间前）
    var roomId by remember { mutableStateOf("") }                  // 当前房间 id
    var roomInfo by remember { mutableStateOf<J.Obj?>(null) }      // 当前房间元数据
    var myPc by remember { mutableStateOf("") }
    var story by remember { mutableStateOf(listOf<J.Obj>()) }
    var pcs by remember { mutableStateOf(listOf<String>()) }
    var turn by remember { mutableStateOf("") }
    var action by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var gmSession by remember { mutableStateOf<TrpgSession?>(null) }  // 手机当 GM 的本地会话
    var gmStarted by remember { mutableStateOf(false) }               // 本机 GM 已开始（进入游玩）
    var rooms by remember { mutableStateOf(listOf<J.Obj>()) }         // 当前主机的房间列表

    // 房间内状态轮询（成员连房间）
    LaunchedEffect(base, roomId) {
        if (base.isBlank() || roomId.isBlank()) return@LaunchedEffect
        while (vm.showTrpg.value && base.isNotBlank() && roomId.isNotBlank()) {
            try {
                val st = if (gmSession.value != null) {
                    JsonS.parse((gmSession.value!!).stateJson()) as? J.Obj
                } else Workshop.trpgRoomState(base, roomId)
                if (st != null) {
                    story = (st.fields["story"] as? J.Arr)?.items?.filterIsInstance<J.Obj>() ?: emptyList()
                    pcs = (st.fields["pcs"] as? J.Arr)?.items?.mapNotNull { it.str() } ?: emptyList()
                    turn = st.fields["turn"]?.str() ?: ""
                    if (gmSession.value != null) { roomInfo = null } // 本地当GM无需元数据
                }
            } catch (_: Exception) {}
            delay(2000)
        }
    }

    fun leaveAll() {
        if (base.isNotBlank() && roomId.isNotBlank() && myPc.isNotBlank() && gmSession.value == null) {
            try { Workshop.trpgRoomLeave(base, roomId, myPc) } catch (_: Exception) {}
        }
        gmSession.value = null; gmStarted = false
        vm.showTrpg.value = false; base = ""; roomId = ""; myPc = ""; story = emptyList(); pcs = emptyList(); action = ""; roomInfo = null
    }

    AlertDialog(
        onDismissRequest = { leaveAll() },
        title = { Text("🎭 跑团 · 房间") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (base.isBlank()) {
                    // ---- 一：选主机 / 当 GM ----
                    Button(onClick = {
                        // 当 GM：本地建会话，直接用主机地址（本机）
                        val cfg = J.Obj().apply {
                            fields["api_key"] = J.Str(vm.apiKey.value)
                            fields["base_url"] = J.Str(vm.baseUrl.value)
                            fields["model"] = J.Str(vm.model.value)
                        }
                        // 用一个本地占位 base，但走本地 session 无需 HTTP
                        gmSession.value = TrpgSession(engine, gm = "", pcs = emptyList(),
                            cardPrompt = { "" })
                        base = "local://gm"
                        roomId = "gm"
                        roomInfo = null
                    }, modifier = Modifier.fillMaxWidth()) { Text("🎤 我当 GM（本机开房）") }
                    Text("或连接局域网主机：", fontSize = 11.sp, color = theme.muted)
                    Button(onClick = { sessions = Workshop.discoverTrpg() }, modifier = Modifier.fillMaxWidth()) { Text("📡 查找附近跑团") }
                    if (sessions.isEmpty()) Text("同一 Wi-Fi 让任一设备开房（PC 或手机当 GM），再查找；也可直接输入地址", fontSize = 11.sp, color = theme.muted)
                    sessions.forEach { s ->
                        TextButton(onClick = { base = s.fields["url"]?.str() ?: ""; rooms = Workshop.trpgRooms(base) }, modifier = Modifier.fillMaxWidth()) {
                            Text("🎲 " + (s.fields["gm"]?.str() ?: "房间") + " @ " + (s.fields["url"]?.str() ?: ""), fontSize = 13.sp)
                        }
                    }
                } else if (gmSession.value != null && !gmStarted) {
                    // ---- 二：本机当 GM 模式（未开始配置） ----
                    Text("🎤 本机 GM · 设 GM/队伍", fontSize = 12.sp)
                    OutlinedTextField(value = gmSession.value!!.gm, onValueChange = { gmSession.value!!.gm = it },
                        label = { Text("GM 卡名") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Text("房间名：", fontSize = 11.sp)
                    val roomNameS = remember { mutableStateOf("") }
                    OutlinedTextField(value = roomNameS.value, onValueChange = { roomNameS.value = it },
                        label = { Text("给房间起名") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    if (pcs.isEmpty()) Text("点下方「开始」用默认队伍（凛、咲）", fontSize = 11.sp, color = theme.muted)
                    Button(onClick = {
                        val gm = gmSession.value!!.gm.ifBlank { "咲" }
                        val pcList = if (pcs.isEmpty()) listOf("凛","咲") else pcs
                        gmSession.value!!.let { s -> s.gm = gm; s.pcs.clear(); s.pcs.addAll(pcList); s.turn = pcList.firstOrNull() ?: "" }
                        myPc = pcList.firstOrNull() ?: ""   // 本机 GM 默认操控第一名 PC
                        gmStarted = true
                        busy = false
                    }, modifier = Modifier.fillMaxWidth()) { Text("▶ 开始跑团") }
                } else if (roomId.isBlank()) {
                    // ---- 三：选房间（连接主机后） ----
                    Text("房间：${base}", fontSize = 11.sp, color = theme.muted)
                    TextButton(onClick = { rooms = Workshop.trpgRooms(base) }, modifier = Modifier.fillMaxWidth()) { Text("↻ 刷新房间列表") }
                    if (rooms.isEmpty()) Text("主机暂无房间，或点击下方创建", fontSize = 11.sp, color = theme.muted)
                    rooms.forEach { r ->
                        val n = r.fields["name"]?.str() ?: "未命名房间"
                        val g = r.fields["gm"]?.str() ?: ""; val j = r.fields["joined"]?.str() ?: "0"
                        TextButton(onClick = { roomId = r.fields["id"]?.str() ?: ""; roomInfo = r }, modifier = Modifier.fillMaxWidth()) {
                            Text("🏠 $n · GM:$g · ${j}人", fontSize = 13.sp)
                        }
                    }
                    // 创建房间（连到主机）
                    val createName = remember { mutableStateOf("") }
                    val createGm = remember { mutableStateOf("") }
                    OutlinedTextField(value = createName.value, onValueChange = { createName.value = it }, label = { Text("新房间名") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(value = createGm.value, onValueChange = { createGm.value = it }, label = { Text("GM 卡名") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Button(onClick = {
                        val id = Workshop.trpgCreateRoom(base, createName.value.ifBlank { "新房间" }, createGm.value.ifBlank { "咲" }, listOf("凛","咲"))
                        if (id != null) { roomId = id; rooms = Workshop.trpgRooms(base) }
                    }, modifier = Modifier.fillMaxWidth()) { Text("➕ 在此主机创建房间") }
                } else {
                    // ---- 四：房间内游玩（成员或本地GM） ----
                    Text("已入房间：" + (roomInfo?.fields?.get("name")?.str() ?: roomId), fontSize = 11.sp, color = theme.muted)
                    if (myPc.isBlank()) {
                        Text("选择你的角色：", fontSize = 12.sp)
                        pcs.forEach { pc ->
                            TextButton(onClick = {
                                val ok = gmSession.value != null || Workshop.trpgRoomJoin(base, roomId, pc)
                                if (ok) myPc = pc
                            }, modifier = Modifier.fillMaxWidth()) { Text("👤 " + pc, fontSize = 13.sp) }
                        }
                        if (pcs.isEmpty()) Text("等待主机设置队伍…", fontSize = 11.sp, color = theme.muted)
                    } else {
                        Text("当前行动者：" + (turn.ifBlank { myPc }), fontSize = 12.sp, color = theme.muted)
                        story.forEach { s ->
                            val actor = s.fields["actor"]?.str() ?: ""
                            val gm = s.fields["gm"]?.str() ?: ""
                            Text("👤 " + actor + "：" + (s.fields["action"]?.str() ?: ""), fontSize = 12.sp, color = theme.muted)
                            if (gm.isNotBlank()) Text("🗣 GM：" + gm, fontSize = 13.sp, color = theme.text)
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(value = action, onValueChange = { action = it },
                                label = { Text("$myPc 的行动") }, singleLine = true, modifier = Modifier.weight(1f))
                            Button(onClick = {
                                if (action.isBlank()) return@Button
                                busy = true
                                if (gmSession.value != null) {
                                    gmSession.value!!.act(myPc, action)
                                } else {
                                    Workshop.trpgRoomAct(base, roomId, myPc, action)
                                }
                                action = ""; busy = false
                            }, enabled = !busy) { Text("行动") }
                        }
                        TextButton(onClick = { leaveAll() }, modifier = Modifier.fillMaxWidth()) { Text("🏁 退出本局", fontSize = 13.sp, color = theme.danger) }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { leaveAll() }) { Text("完成") } },
        dismissButton = { TextButton(onClick = { leaveAll() }) { Text("取消") } },
    )
    }
}

/** 选角色（多选=群聊） */
@Composable
fun RolesDialog(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val scope = deps.scope
    val tree = deps.tree
    val mech = deps.mech
    val gal = deps.gal
    val roles = vm.roles
    val saveTree = deps.saveTree
    val saveConfig = deps.saveConfig
    val refreshChain = deps.refreshChain
    val treeFileFor = deps.treeFileFor
    val stateFileFor = deps.stateFileFor
    val mechConfig = deps.mechConfig
    val mechBattleConfig = deps.mechBattleConfig
    val playerBattleConfig = deps.playerBattleConfig
    val toggleRoleUnlock = deps.toggleRoleUnlock
    val avatarPicker = deps.avatarPicker
    val importCardLauncher = deps.importCardLauncher
    val exportCardLauncher = deps.exportCardLauncher
    val avatarCache = vm.avatarCache
    val roleUnlocked = vm.roleUnlocked
    var selectedRoles by vm.selectedRoles
    var avatarTarget by vm.avatarTarget
    var exportTarget by vm.exportTarget
    var roleEditName by vm.roleEditName
    var pendingDelete by vm.pendingDelete
    if (vm.showRoles.value) {
    AlertDialog(
        onDismissRequest = { vm.showRoles.value = false },
        title = { Text(I18n.t("dlg_roles", "选择角色（多选=群聊）")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                for ((n, _) in roles) {
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .padding(vertical = 10.dp)
                            .border(1.dp, Color(0xFF262B34), RoundedCornerShape(10.dp))
                            .padding(horizontal = 8.dp, vertical = 4.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = n in selectedRoles, onCheckedChange = { ck ->
                                saveTree()
                                selectedRoles = if (ck) selectedRoles + n else selectedRoles - n
                                saveConfig()
                                gal.clearChoices()
                                scope.launch(Dispatchers.Main) {
                                    val tf = treeFileFor()
                                    tree.loadData(if (tf.exists()) {
                                        try { TreeStore.load(tf).historyTree } catch (_: Exception) { ChatTree().toData() }
                                    } else ChatTree().toData())
                                    tree.fixLeaf()
                                    mech.stateFile = stateFileFor()
                                    mech.resetConfigTracking()
                                    mech.reload(mechConfig(), tree, reset = true)
                                    mech.battleCfg = mechBattleConfig()
                                    mech.playerCfg = playerBattleConfig()
                                    mech.initBattle()
                                    refreshChain()
                                }
                            })
                            Avatar(n, avatarCache)
                            Text(n, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.weight(1f))
                            if (roleUnlocked[n] == true) {
                                IconText("🔥", fontSize = 13.sp, color = theme.danger)
                            }
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(start = 4.dp)) {
                            TextButton(onClick = { avatarTarget = n; avatarPicker.launch("image/*") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("🖼️ 头像", fontSize = 12.sp) }
                            TextButton(onClick = { toggleRoleUnlock(n) }, modifier = Modifier.heightIn(min = 44.dp)) {
                                IconText(if (roleUnlocked[n] == true) "🔥 破甲·开" else "🔥 破甲", fontSize = 12.sp, color = if (roleUnlocked[n] == true) theme.danger else Color.Unspecified)
                            }
                            TextButton(onClick = { roleEditName = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("✏️ 编辑", fontSize = 12.sp) }
                            TextButton(onClick = { exportTarget = n to "json"; exportCardLauncher.launch("application/json") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("⬇️ JSON", fontSize = 12.sp) }
                            TextButton(onClick = { exportTarget = n to "png"; exportCardLauncher.launch("image/png") }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("📤 PNG", fontSize = 12.sp) }
                            TextButton(onClick = { pendingDelete = n to "role" }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("🗑️", color = theme.danger, fontSize = 14.sp) }
                        }
                    }
                }
            }
        },
        confirmButton = {
            Row {
                TextButton(onClick = {
                    importCardLauncher.launch(arrayOf("image/png", "image/webp", "application/json"))
                }) { IconText(I18n.t("btn_import_card", "📥 导入角色卡"), fontSize = 12.sp) }
                Spacer(Modifier.weight(1f))
                TextButton(onClick = { roleEditName = "" }) { Text(I18n.t("btn_new_role", "新建角色")) }
            }
        },
        dismissButton = { TextButton(onClick = { vm.showRoles.value = false }) { Text(I18n.t("btn_done", "完成")) } },
    )
    }
}

/** 角色编辑（新手友好：结构化字段 + 机制卡/战斗系统折叠） */
@Composable
fun RoleEditDialog(vm: ChatViewModel, deps: DialogDeps) {
    val context = deps.context
    val theme = deps.theme
    val roles = vm.roles
    var selectedRoles by vm.selectedRoles
    val roleUnlocked = vm.roleUnlocked
    val advancedByRole = vm.advancedByRole
    var roleEditName by vm.roleEditName
    var devMode by deps.devMode
    val reloadMech = deps.reloadMech
    if (roleEditName != null) {
    val editing = roleEditName!!
    var rName by remember { mutableStateOf(editing) }
    var rLegacy by remember { mutableStateOf("") }
    var rAppearance by remember { mutableStateOf("") }
    var rPersonality by remember { mutableStateOf("") }
    var rBackground by remember { mutableStateOf("") }
    var rSpeech by remember { mutableStateOf("") }
    var rFirstMes by remember { mutableStateOf("") }
    var rMesExample by remember { mutableStateOf("") }
    var rNotes by remember { mutableStateOf("") }
    var rUnlocked by remember { mutableStateOf(false) }
    var rGameName by remember { mutableStateOf("") }
    var rGameRules by remember { mutableStateOf("") }
    var rGameState by remember { mutableStateOf("") }
    var rExtraPrompt by remember { mutableStateOf("") }
    var rCardFace by remember { mutableStateOf("") }
    var rCardFacePrev by remember { mutableStateOf(false) }
    val cardFaceImpLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { u ->
            try {
                val bytes = context.contentResolver.openInputStream(u)?.use { it.readBytes() }
                if (bytes != null) rCardFace = String(bytes, Charsets.UTF_8)
            } catch (_: Exception) {}
        }
    }
    var rDevNotes by remember { mutableStateOf("") }
    var rCardQr by remember { mutableStateOf("") }
    var rRegex by remember { mutableStateOf("") }
    var rMechAff by remember { mutableStateOf(false) }
    var rMechAffInit by remember { mutableStateOf("50") }
    var rMechAffMax by remember { mutableStateOf("100") }
    var rMechAffCrit by remember { mutableStateOf("0.001") }
    var rMechSt by remember { mutableStateOf("") }
    var rMechEv by remember { mutableStateOf("") }
    var rEndings by remember { mutableStateOf("") }
    var foldEndings by remember { mutableStateOf(false) }
    var rBattleEnabled by remember { mutableStateOf(false) }
    var rBattleAttrs by remember { mutableStateOf("hp|生命|100|100\natk|攻击|10\ndef|防御|5") }
    var rBattleMech by remember { mutableStateOf("") }
    var rBattleFormulas by remember { mutableStateOf("damage=max(1, player_atk*2-def)\ncrit_chance=0.1\ncrit_mult=2") }
    var rBattleMoves by remember { mutableStateOf("") }
    var rBattleBuffs by remember { mutableStateOf("") }
    var foldMech by remember { mutableStateOf(false) }
    var foldSt by remember { mutableStateOf(false) }
    var foldBattle by remember { mutableStateOf(false) }
    var foldCardFace by remember { mutableStateOf(false) }
    LaunchedEffect(editing) {
        if (editing.isNotBlank() && rLegacy.isEmpty() && rPersonality.isEmpty() && rAppearance.isEmpty()) {
            try {
                val o = JsonS.parse(File(AppEnv.savesDir(), editing + ".json").readText(Charsets.UTF_8)) as? J.Obj
                if (o != null) {
                    rLegacy = o.fields["legacy"]?.str() ?: ""
                    rAppearance = o.fields["appearance"]?.str() ?: ""
                    rPersonality = o.fields["personality"]?.str() ?: ""
                    rBackground = o.fields["background"]?.str() ?: ""
                    rSpeech = o.fields["speech"]?.str() ?: ""
                    rFirstMes = o.fields["first_mes"]?.str() ?: ""
                    rMesExample = o.fields["mes_example"]?.str() ?: ""
                    rNotes = o.fields["notes"]?.str() ?: ""
                    rUnlocked = (o.fields["unlocked"] as? J.Bool)?.v ?: false
                    val adv = o.fields["advanced"] as? J.Obj
                    val game = adv?.fields?.get("game") as? J.Obj
                    rGameName = game?.fields?.get("name")?.str() ?: ""
                    rGameRules = game?.fields?.get("rules")?.str() ?: ""
                    rGameState = game?.fields?.get("state")?.str() ?: ""
                    rExtraPrompt = adv?.fields?.get("extra_prompt")?.str() ?: ""
                    rCardFace = adv?.fields?.get("card_face")?.str() ?: ""
                    rDevNotes = adv?.fields?.get("dev_notes")?.str() ?: ""
                    rCardQr = (adv?.fields?.get("card_quick_replies") as? J.Arr)
                        ?.items?.mapNotNull { q ->
                            val qo = q as? J.Obj ?: return@mapNotNull null
                            val l = qo.fields["label"]?.str() ?: return@mapNotNull null
                            l + "|" + (qo.fields["text"]?.str() ?: "")
                        }?.joinToString("\n") ?: ""
                    rRegex = (adv?.fields?.get("regex_rules") as? J.Arr)
                        ?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { x ->
                            val id = x.fields["id"]?.str() ?: return@mapNotNull null
                            listOf(id, x.fields["name"]?.str() ?: id,
                                x.fields["pattern"]?.str() ?: "",
                                x.fields["replace"]?.str() ?: "",
                                x.fields["scope"]?.str() ?: "both").joinToString("|")
                        }?.joinToString("\n") ?: ""
                    val mech = adv?.fields?.get("mechanics") as? J.Obj
                    val maff = mech?.fields?.get("affection") as? J.Obj
                    rMechAff = maff?.fields?.get("enabled")?.bool() == true
                    rMechAffInit = maff?.fields?.get("initial")?.int()?.toString() ?: "50"
                    rMechAffMax = maff?.fields?.get("max")?.int()?.toString() ?: "100"
                    rMechAffCrit = ((maff?.fields?.get("crit") as? J.Num)?.v ?: 0.001).toString()
                    rMechSt = ((mech?.fields?.get("status") as? J.Obj)?.fields?.get("fields") as? J.Arr)
                        ?.items?.mapNotNull { f ->
                            val fo = f as? J.Obj ?: return@mapNotNull null
                            val key = fo.fields["key"]?.str() ?: return@mapNotNull null
                            val name = fo.fields["name"]?.str() ?: key
                            val type = fo.fields["type"]?.str() ?: "enum"
                            val init = fo.fields["initial"]?.str() ?: (fo.fields["initial"]?.int()?.toString() ?: "")
                            val extra = if (type == "int") {
                                (fo.fields["min"]?.int() ?: 0).toString() + "-" + (fo.fields["max"]?.int() ?: 100)
                            } else {
                                (fo.fields["options"] as? J.Arr)?.items?.mapNotNull { it.str() }?.joinToString(",") ?: ""
                            }
                            listOf(key, name, type, init, extra).joinToString("|")
                        }?.joinToString("\n") ?: ""
                    rMechEv = (mech?.fields?.get("events") as? J.Arr)
                        ?.items?.mapNotNull { e ->
                            val eo = e as? J.Obj ?: return@mapNotNull null
                            val id = eo.fields["id"]?.str() ?: return@mapNotNull null
                            val name = eo.fields["name"]?.str() ?: ""
                            val affGe = eo.fields["aff_ge"]?.int()?.toString() ?: ""
                            val kws = (eo.fields["keywords"] as? J.Arr)?.items?.mapNotNull { it.str() }?.joinToString(",") ?: ""
                            val prompt = eo.fields["prompt"]?.str() ?: ""
                            listOf(id, name, affGe, kws, prompt).joinToString("|")
                        }?.joinToString("\n") ?: ""
                    rEndings = endingsToText(mech?.fields?.get("endings") as? J.Arr)
                    foldEndings = rEndings.isNotBlank()
                    val battle = adv?.fields?.get("battle") as? J.Obj
                    rBattleEnabled = battle?.fields?.get("enabled")?.bool() == true
                    if (battle != null) {
                        val battrs = battle.fields["attrs"] as? J.Obj
                        rBattleAttrs = battrs?.fields?.mapNotNull { (k, v) ->
                            val a = v as? J.Obj ?: return@mapNotNull null
                            listOf(k, a.fields["label"]?.str() ?: k,
                                a.fields["initial"]?.int()?.toString() ?: "10",
                                a.fields["max"]?.int()?.toString() ?: "").joinToString("|")
                        }?.joinToString("\n") ?: rBattleAttrs
                        rBattleMech = (battle.fields["mech_attrs"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { a ->
                            val key = a.fields["key"]?.str() ?: return@mapNotNull null
                            listOf(key, a.fields["label"]?.str() ?: key,
                                a.fields["initial"]?.int()?.toString() ?: "10",
                                a.fields["max"]?.int()?.toString() ?: "").joinToString("|")
                        }?.joinToString("\n") ?: ""
                        rBattleFormulas = (battle.fields["formulas"] as? J.Obj)?.fields
                            ?.map { (k, v) -> "$k=${v.str() ?: ""}" }?.joinToString("\n") ?: rBattleFormulas
                        rBattleMoves = (battle.fields["moves"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { m ->
                            val id = m.fields["id"]?.str() ?: return@mapNotNull null
                            val cost = (m.fields["cost"] as? J.Obj)?.fields?.map { (k, v) -> "$k:${v.int()}" }?.joinToString(",") ?: ""
                            val bf = (m.fields["buffs"] as? J.Arr)?.items?.firstOrNull() as? J.Obj
                            val bfTxt = bf?.let { "${it.fields["id"]?.str() ?: ""}:${it.fields["turns"]?.int() ?: 3}" } ?: ""
                            listOf(id, m.fields["name"]?.str() ?: id,
                                m.fields["formula"]?.str() ?: "", cost, bfTxt,
                                m.fields["desc"]?.str() ?: "").joinToString("|")
                        }?.joinToString("\n") ?: ""
                        rBattleBuffs = (battle.fields["buffs"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { b ->
                            val id = b.fields["id"]?.str() ?: return@mapNotNull null
                            val at = (b.fields["attrs"] as? J.Obj)?.fields?.map { (k, v) -> "$k:${v.int()}" }?.joinToString(",") ?: ""
                            listOf(id, b.fields["name"]?.str() ?: id,
                                b.fields["turns"]?.int()?.toString() ?: "3", at,
                                b.fields["desc"]?.str() ?: "").joinToString("|")
                        }?.joinToString("\n") ?: ""
                    }
                    foldMech = rMechAff || rMechEv.isNotBlank()
                    foldSt = rMechSt.isNotBlank()
                    foldBattle = rBattleEnabled
                    if (rLegacy.isEmpty() && rPersonality.isEmpty() && rAppearance.isEmpty()) {
                        rLegacy = o.fields["system_prompt"]?.str() ?: ""
                    }
                }
            } catch (_: Exception) {
            }
        }
    }
    AlertDialog(
        onDismissRequest = { roleEditName = null },
        title = { Text(if (editing.isBlank()) I18n.t("btn_new_role", "新建角色") else "编辑角色：" + editing) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(value = rName, onValueChange = { rName = it }, label = { Text(I18n.t("lbl_name", "名字")) }, singleLine = true, enabled = editing.isBlank())
                IconText("📜 完整设定（旧版原文，填了会整体覆盖，可留空）", fontSize = 11.sp, color = theme.muted, modifier = Modifier.padding(top = 6.dp))
                OutlinedTextField(value = rLegacy, onValueChange = { rLegacy = it }, label = { Text("Legacy 原文") }, minLines = 2)
                IconText("🎨 结构化字段（精细设定）", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 10.dp))
                OutlinedTextField(value = rAppearance, onValueChange = { rAppearance = it }, label = { Text("外貌") }, minLines = 2)
                OutlinedTextField(value = rPersonality, onValueChange = { rPersonality = it }, label = { Text("性格") }, minLines = 2)
                OutlinedTextField(value = rBackground, onValueChange = { rBackground = it }, label = { Text("过去经历") }, minLines = 2)
                OutlinedTextField(value = rSpeech, onValueChange = { rSpeech = it }, label = { Text("说话方式（语气/口癖/句式）") }, minLines = 2)
                OutlinedTextField(value = rFirstMes, onValueChange = { rFirstMes = it }, label = { Text("开场白") }, minLines = 2)
                OutlinedTextField(value = rMesExample, onValueChange = { rMesExample = it }, label = { Text("对话示例") }, minLines = 2)
                OutlinedTextField(value = rNotes, onValueChange = { rNotes = it }, label = { Text("备注") }, minLines = 2)
                Row {
                    Checkbox(checked = rUnlocked, onCheckedChange = { rUnlocked = it })
                    IconText("🔥 启用破甲模式（无限制对话）", Modifier.padding(top = 14.dp), fontSize = 12.sp)
                }
                FoldHead("🎛️ 机制卡（好感度 / 事件）", foldMech, onToggle = { foldMech = !foldMech })
                if (foldMech) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(bottom = 4.dp)) {
                        TextButton(onClick = {
                            rMechAff = true; rMechAffInit = "50"; rMechAffMax = "100"; rMechAffCrit = "0.001"
                            rMechSt = "mood|心情|enum|平静|平静,开心,害羞,生气,委屈\nenergy|精力|int|100|0-100"
                            rMechEv = "confess|告白|80|告白,喜欢|她鼓起勇气向你告白，请演出这一重要时刻"
                            foldMech = true; foldSt = true
                        }) { Text("💘 恋爱日常", fontSize = 12.sp) }
                        TextButton(onClick = {
                            rBattleEnabled = true
                            rBattleAttrs = "hp|生命|100|100\natk|攻击|10\ndef|防御|5"
                            rBattleMech = "spd|速度|8|100\nmp|灵力|20|50"
                            rBattleFormulas = "damage=max(1, player_atk*2-def)\ncrit_chance=0.1\ncrit_mult=2"
                            rBattleMoves = "fire|火球术|player_atk*3-def|mp:5||投掷火球\nstrike|平砍|player_atk-def|\nheal|治愈|20||regen:2|恢复体力"
                            rBattleBuffs = "regen|再生|2|hp:5|每回合恢复5生命\npoison|中毒|3|hp:-5|每回合损失5生命"
                            foldBattle = true
                        }) { Text("⚔️ 战斗冒险", fontSize = 12.sp) }
                        TextButton(onClick = {
                            rMechEv = "meet|初遇|0|你好,初次见面|第一次相遇，自然演出\nstorm|风暴夜|30|暴风雨,打雷|暴风雨夜，她害怕地靠近你\nconfess|告白|80|告白,喜欢|她鼓起勇气向你告白"
                            foldMech = true
                        }) { Text("🎬 事件剧本", fontSize = 12.sp) }
                        TextButton(onClick = {
                            rMechAff = false; rMechSt = ""; rMechEv = ""
                            rBattleEnabled = false; rBattleAttrs = ""; rBattleMech = ""
                            rBattleFormulas = ""; rBattleMoves = ""; rBattleBuffs = ""
                        }) { Text("🗑️ 清空", fontSize = 12.sp) }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = rMechAff, onCheckedChange = { rMechAff = it })
                        Text("❤ 启用好感度（AI 每轮用 [aff:+N] 标注变化）", fontSize = 12.sp)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedTextField(value = rMechAffInit, onValueChange = { rMechAffInit = it }, label = { Text("初始值") }, singleLine = true, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = rMechAffMax, onValueChange = { rMechAffMax = it }, label = { Text("上限") }, singleLine = true, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = rMechAffCrit, onValueChange = { rMechAffCrit = it }, label = { Text("暴击概率") }, singleLine = true, modifier = Modifier.weight(1f))
                    }
                    OutlinedTextField(value = rMechEv, onValueChange = { rMechEv = it }, label = { Text("事件（每行 ID|名称|好感≥|关键词,逗号|触发提示）") }, minLines = 3)
                }
                FoldHead("📊 状态字段", foldSt, onToggle = { foldSt = !foldSt })
                if (foldSt) {
                    OutlinedTextField(value = rMechSt, onValueChange = { rMechSt = it }, label = { Text("状态字段（每行 键|显示名|类型|初始值|范围或选项）\n例：mood|心情|enum|平静|平静,开心,生气") }, minLines = 3)
                }
                FoldHead("⚔️ 战斗系统（可选）", foldBattle, onToggle = { foldBattle = !foldBattle })
                if (foldBattle) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = rBattleEnabled, onCheckedChange = { rBattleEnabled = it })
                        Text("启用战斗（出招结算 / 伤害公式 / buff）", fontSize = 12.sp)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedTextField(value = rBattleAttrs, onValueChange = { rBattleAttrs = it }, label = { Text("基础属性（每行 键|名|初值|上限）\n例：hp|生命|100|100") }, minLines = 4, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = rBattleMech, onValueChange = { rBattleMech = it }, label = { Text("机制属性·第四属性（每行 键|名|初值|上限）\n例：spd|速度|8|100") }, minLines = 4, modifier = Modifier.weight(1f))
                    }
                    OutlinedTextField(value = rBattleFormulas, onValueChange = { rBattleFormulas = it }, label = { Text("伤害公式（每行 名称=表达式，变量用属性键）\n例：damage=max(1, player_atk*2-def)") }, minLines = 3)
                    OutlinedTextField(value = rBattleMoves, onValueChange = { rBattleMoves = it }, label = { Text("招式（每行 ID|名称|公式|消耗键:值|效果:id:回合|描述）") }, minLines = 3)
                    OutlinedTextField(value = rBattleBuffs, onValueChange = { rBattleBuffs = it }, label = { Text("状态效果 buff（每行 ID|名称|回合|效果键:值|描述）") }, minLines = 3)
                }
                FoldHead("🏁 结局预设（达成事件链）", foldEndings, onToggle = { foldEndings = !foldEndings })
                if (foldEndings) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(bottom = 2.dp)) {
                        TextButton(onClick = {
                            rEndings = "good|告白成功|初见,约会,告白|90||她终于说出了那句喜欢\nbad|形同陌路|争吵,决裂|20||你们最终还是走散了\nhidden|雨夜告白|初见,雨夜,告白|1|藏|只有走完整条线才会亮起的结局……"
                        }) { Text("💘 恋爱线", fontSize = 12.sp) }
                        TextButton(onClick = {
                            rEndings = "bad|平淡收场|疏远,淡忘|30||日子照常，只是再也没了心动"
                        }) { Text("🌧 平淡/坏", fontSize = 12.sp) }
                        TextButton(onClick = {
                            rEndings = "hidden|雨夜告白|初见,雨夜,告白|1|藏|只有走完整条线才会亮起的隐藏结局……\n" +
                                "hidden|真相大白|秘密,线索,摊牌|1|藏|你终于问出了那句藏在心底很久的话。\n" +
                                "hidden|时间线|重来,循环,抉择|1|藏|这一次，你没有选择离开。\n" +
                                "hidden|幻梦|沉睡,迷梦,醒来|1|藏|你睁开眼，分不清刚才是不是一场梦。\n" +
                                "hidden|失控|占有,出格,失控|1|藏|她笑着看着你，眼里却没了光。"
                        }) { Text("🎁 隐藏结局", fontSize = 12.sp) }
                        TextButton(onClick = {
                            rEndings = "ghost|幻灭|误会,离开|10||你回头时，她已不在原处。"
                        }) { Text("👻 幻灭", fontSize = 12.sp) }
                    }
                    OutlinedTextField(value = rEndings, onValueChange = { rEndings = it }, label = { Text("结局（每行 id|结局名|事件链,逗号|好感≥|隐藏|描述）\n例：good|告白成功|初见,约会,告白|90||她终于说出了那句喜欢") }, minLines = 3)
                    Text("达成条件：按序触发全部事件链(id)即解锁结局；可与好感/隐藏条件叠加。", fontSize = 11.sp, color = theme.muted)
                }
                if (devMode) {
                    IconText("⚙️ 高级设置（开发者模式）", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 10.dp))
                    OutlinedTextField(value = rGameName, onValueChange = { rGameName = it }, label = { Text("内置游戏名") }, singleLine = true)
                    OutlinedTextField(value = rGameRules, onValueChange = { rGameRules = it }, label = { Text("游戏规则（注入系统提示）") }, minLines = 3)
                    OutlinedTextField(value = rGameState, onValueChange = { rGameState = it }, label = { Text("初始状态（注入）") }, minLines = 2)
                    OutlinedTextField(value = rExtraPrompt, onValueChange = { rExtraPrompt = it }, label = { Text("额外系统提示") }, minLines = 2)
                    FoldHead("🎴 卡面（HTML，可选）", foldCardFace, onToggle = { foldCardFace = !foldCardFace })
                    if (foldCardFace) {
                        OutlinedTextField(value = rCardFace, onValueChange = { rCardFace = it },
                            label = { Text("卡面 HTML（导入或自写；聊天顶栏 🎴 查看；非强制）") }, minLines = 4)
                        Row {
                            TextButton(onClick = { cardFaceImpLauncher.launch(arrayOf("text/html", "text/plain", "*/*")) }) { IconText("📥 导入HTML文件", fontSize = 12.sp) }
                            TextButton(onClick = { rCardFacePrev = true }) { IconText("👁 预览", fontSize = 12.sp) }
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = { rCardFace = "" }) { IconText("🧹 清空", fontSize = 12.sp) }
                        }
                    }
                    OutlinedTextField(value = rCardQr, onValueChange = { rCardQr = it }, label = { Text("卡片快捷回复（每行 按钮名|内容）") }, minLines = 3)
                    OutlinedTextField(value = rRegex, onValueChange = { rRegex = it }, label = { Text("🔤 角色专属正则（每行 id|名称|正则|替换|作用域，叠加全局）") }, minLines = 3)
                    OutlinedTextField(value = rDevNotes, onValueChange = { rDevNotes = it }, label = { Text("开发者备注（不注入）") }, minLines = 2)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val nm = rName.trim()
                val fields = mapOf(
                    "appearance" to rAppearance.trim(), "personality" to rPersonality.trim(),
                    "background" to rBackground.trim(), "speech" to rSpeech.trim(),
                    "first_mes" to rFirstMes.trim(), "mes_example" to rMesExample.trim(),
                    "notes" to rNotes.trim(),
                )
                val prompt = assembleRolePrompt(nm, fields, rLegacy.trim())
                if (nm.isNotBlank() && prompt.isNotBlank()) {
                    try {
                        val f = File(AppEnv.savesDir(), nm + ".json")
                        val o = if (f.exists()) (JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj) ?: J.Obj() else J.Obj()
                        o.fields["name"] = J.Str(nm)
                        o.fields["system_prompt"] = J.Str(prompt)
                        o.fields["legacy"] = J.Str(rLegacy.trim())
                        o.fields["unlocked"] = J.Bool(rUnlocked)
                        roleUnlocked[nm] = rUnlocked
                        val advDirty = devMode && (rGameRules.isNotBlank() || rGameName.isNotBlank() ||
                                rExtraPrompt.isNotBlank() || rDevNotes.isNotBlank() || rCardQr.isNotBlank())
                        val mechDirty = rMechAff || rMechSt.isNotBlank() || rMechEv.isNotBlank() || rEndings.isNotBlank()
                        val battleDirty = rBattleEnabled
                        if (advDirty || mechDirty || battleDirty) {
                            val orig = o.fields["advanced"] as? J.Obj
                            val adv = J.Obj()
                            orig?.fields?.forEach { (k, v) -> adv.fields[k] = v }
                            if (devMode) {
                                if (rGameRules.isNotBlank() || rGameName.isNotBlank()) {
                                    val g = J.Obj()
                                    g.fields["name"] = J.Str(rGameName.trim())
                                    g.fields["rules"] = J.Str(rGameRules.trim())
                                    g.fields["state"] = J.Str(rGameState.trim())
                                    adv.fields["game"] = g
                                } else {
                                    adv.fields.remove("game")
                                }
                                adv.fields["extra_prompt"] = J.Str(rExtraPrompt.trim())
                                if (rCardFace.isNotBlank()) adv.fields["card_face"] = J.Str(rCardFace.trim())
                                else adv.fields.remove("card_face")
                                adv.fields["dev_notes"] = J.Str(rDevNotes.trim())
                                val qrs = J.Arr()
                                rCardQr.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val i = t.indexOf('|')
                                    if (i > 0) {
                                        val qo = J.Obj()
                                        qo.fields["label"] = J.Str(t.substring(0, i).trim())
                                        qo.fields["text"] = J.Str(t.substring(i + 1).trim())
                                        qrs.items.add(qo)
                                    }
                                }
                                adv.fields["card_quick_replies"] = qrs
                                val rrArr = J.Arr()
                                rRegex.split("\n").forEach { line ->
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
                                    rrArr.items.add(o)
                                }
                                if (rrArr.items.isNotEmpty()) adv.fields["regex_rules"] = rrArr
                            }
                            if (mechDirty) {
                                val mechObj = J.Obj()
                                if (rMechAff) {
                                    val a = J.Obj()
                                    a.fields["enabled"] = J.Bool(true)
                                    val affInit = (rMechAffInit.toIntOrNull() ?: 50).coerceIn(0, 99999)
                                    val affMax = (rMechAffMax.toIntOrNull() ?: 100).coerceIn(1, 99999)
                                    a.fields["initial"] = J.Num(affInit.coerceAtMost(affMax).toDouble())
                                    a.fields["min"] = J.Num(0.0)
                                    a.fields["max"] = J.Num(affMax.toDouble())
                                    a.fields["crit"] = J.Num((rMechAffCrit.toDoubleOrNull() ?: 0.001).coerceIn(0.0, 1.0))
                                    mechObj.fields["affection"] = a
                                }
                                val stFields = J.Arr()
                                rMechSt.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 3) return@forEach
                                    val fo = J.Obj()
                                    fo.fields["key"] = J.Str(p[0].trim())
                                    fo.fields["name"] = J.Str(p[1].trim().ifEmpty { p[0].trim() })
                                    val type = if (p[2].trim() == "int") "int" else "enum"
                                    fo.fields["type"] = J.Str(type)
                                    val initRaw = p.getOrNull(3)?.trim() ?: ""
                                    if (type == "int") {
                                        val mm = Regex("^(\\d+)\\s*-\\s*(\\d+)$").find(p.getOrNull(4)?.trim() ?: "")
                                        val mn = mm?.groupValues?.get(1)?.toIntOrNull() ?: 0
                                        val mx = mm?.groupValues?.get(2)?.toIntOrNull() ?: 100
                                        fo.fields["min"] = J.Num(mn.toDouble())
                                        fo.fields["max"] = J.Num(mx.toDouble())
                                        fo.fields["initial"] = J.Num((initRaw.toIntOrNull() ?: mn).coerceIn(mn, mx).toDouble())
                                    } else {
                                        val opts = J.Arr()
                                        (p.getOrNull(4) ?: "").split(",").map { it.trim() }
                                            .filter { it.isNotEmpty() }.forEach { opts.items.add(J.Str(it)) }
                                        fo.fields["options"] = opts
                                        fo.fields["initial"] = J.Str(initRaw.ifEmpty { (opts.items.firstOrNull() as? J.Str)?.v ?: "" })
                                    }
                                    stFields.items.add(fo)
                                }
                                if (stFields.items.isNotEmpty()) {
                                    val s = J.Obj()
                                    s.fields["enabled"] = J.Bool(true)
                                    s.fields["fields"] = stFields
                                    mechObj.fields["status"] = s
                                }
                                val evArr = J.Arr()
                                rMechEv.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 5) return@forEach
                                    val eo = J.Obj()
                                    eo.fields["id"] = J.Str(p[0].trim())
                                    eo.fields["name"] = J.Str(p[1].trim())
                                    p[2].trim().toIntOrNull()?.let { eo.fields["aff_ge"] = J.Num(it.toDouble()) }
                                    val kws = J.Arr()
                                    p[3].split(",").map { it.trim() }.filter { it.isNotEmpty() }.forEach { kws.items.add(J.Str(it)) }
                                    if (kws.items.isNotEmpty()) eo.fields["keywords"] = kws
                                    eo.fields["prompt"] = J.Str(p.drop(4).joinToString("|").trim())
                                    eo.fields["once"] = J.Bool(true)
                                    evArr.items.add(eo)
                                }
                                if (evArr.items.isNotEmpty()) mechObj.fields["events"] = evArr
                                val endingsArr = parseEndings(rEndings)
                                if (endingsArr.items.isNotEmpty()) mechObj.fields["endings"] = endingsArr
                                if (mechObj.fields.isNotEmpty()) adv.fields["mechanics"] = mechObj
                            }
                            if (battleDirty) {
                                val battle = J.Obj()
                                battle.fields["enabled"] = J.Bool(true)
                                val battrs = J.Obj()
                                rBattleAttrs.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 2) return@forEach
                                    val key = p[0].trim()
                                    if (key.isEmpty()) return@forEach
                                    val a = J.Obj()
                                    a.fields["label"] = J.Str(p[1].trim().ifEmpty { key })
                                    a.fields["initial"] = J.Num((p.getOrNull(2)?.toIntOrNull() ?: 10).toDouble())
                                    if (key == "hp" || p.getOrNull(3)?.isNotBlank() == true) {
                                        a.fields["max"] = J.Num((p.getOrNull(3)?.toIntOrNull() ?: if (key == "hp") 100 else 999999).toDouble())
                                    }
                                    battrs.fields[key] = a
                                }
                                if (battrs.fields.isNotEmpty()) battle.fields["attrs"] = battrs
                                val bmech = J.Arr()
                                rBattleMech.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 2) return@forEach
                                    val key = p[0].trim()
                                    if (key.isEmpty()) return@forEach
                                    val a = J.Obj()
                                    a.fields["key"] = J.Str(key)
                                    a.fields["label"] = J.Str(p[1].trim().ifEmpty { key })
                                    a.fields["initial"] = J.Num((p.getOrNull(2)?.toIntOrNull() ?: 10).toDouble())
                                    a.fields["max"] = J.Num((p.getOrNull(3)?.toIntOrNull() ?: 999999).toDouble())
                                    bmech.items.add(a)
                                }
                                if (bmech.items.isNotEmpty()) battle.fields["mech_attrs"] = bmech
                                val bform = J.Obj()
                                rBattleFormulas.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val i = t.indexOf('=')
                                    if (i <= 0) return@forEach
                                    val name = t.substring(0, i).trim()
                                    val expr = t.substring(i + 1).trim()
                                    if (name.isNotEmpty() && expr.isNotEmpty()) bform.fields[name] = J.Str(expr)
                                }
                                if (bform.fields.isNotEmpty()) battle.fields["formulas"] = bform
                                val bmoves = J.Arr()
                                rBattleMoves.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 2) return@forEach
                                    val id = p[0].trim()
                                    if (id.isEmpty()) return@forEach
                                    val m = J.Obj()
                                    m.fields["id"] = J.Str(id)
                                    m.fields["name"] = J.Str(p[1].trim().ifEmpty { id })
                                    p.getOrNull(2)?.trim()?.takeIf { it.isNotEmpty() }?.let { m.fields["formula"] = J.Str(it) }
                                    p.getOrNull(3)?.trim()?.takeIf { it.isNotEmpty() }?.let { costStr ->
                                        val cost = J.Obj()
                                        costStr.split(",").forEach { kv ->
                                            val sp = kv.split(":")
                                            if (sp.size == 2 && sp[0].isNotBlank() && sp[1].toIntOrNull() != null) {
                                                cost.fields[sp[0].trim()] = J.Num((sp[1].toIntOrNull() ?: 0).toDouble())
                                            }
                                        }
                                        if (cost.fields.isNotEmpty()) m.fields["cost"] = cost
                                    }
                                    p.getOrNull(4)?.trim()?.takeIf { it.isNotEmpty() }?.let { bfStr ->
                                        val sp = bfStr.split(":")
                                        if (sp.size == 2 && sp[0].isNotBlank()) {
                                            val bf = J.Obj()
                                            bf.fields["id"] = J.Str(sp[0].trim())
                                            bf.fields["turns"] = J.Num((sp[1].toIntOrNull() ?: 3).toDouble())
                                            val arr = J.Arr()
                                            arr.items.add(bf)
                                            m.fields["buffs"] = arr
                                        }
                                    }
                                    p.getOrNull(5)?.trim()?.takeIf { it.isNotEmpty() }?.let { m.fields["desc"] = J.Str(it) }
                                    bmoves.items.add(m)
                                }
                                if (bmoves.items.isNotEmpty()) battle.fields["moves"] = bmoves
                                val bbuffs = J.Arr()
                                rBattleBuffs.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 2) return@forEach
                                    val id = p[0].trim()
                                    if (id.isEmpty()) return@forEach
                                    val b = J.Obj()
                                    b.fields["id"] = J.Str(id)
                                    b.fields["name"] = J.Str(p[1].trim().ifEmpty { id })
                                    b.fields["turns"] = J.Num((p.getOrNull(2)?.toIntOrNull() ?: 3).toDouble())
                                    p.getOrNull(3)?.trim()?.takeIf { it.isNotEmpty() }?.let { atStr ->
                                        val at = J.Obj()
                                        atStr.split(",").forEach { kv ->
                                            val sp = kv.split(":")
                                            if (sp.size == 2 && sp[0].isNotBlank() && sp[1].toIntOrNull() != null) {
                                                at.fields[sp[0].trim()] = J.Num((sp[1].toIntOrNull() ?: 0).toDouble())
                                            }
                                        }
                                        if (at.fields.isNotEmpty()) b.fields["attrs"] = at
                                    }
                                    p.getOrNull(4)?.trim()?.takeIf { it.isNotEmpty() }?.let { b.fields["desc"] = J.Str(it) }
                                    bbuffs.items.add(b)
                                }
                                if (bbuffs.items.isNotEmpty()) battle.fields["buffs"] = bbuffs
                                adv.fields["battle"] = battle
                            }
                            o.fields["advanced"] = adv
                            advancedByRole[nm] = adv
                        }
                        for ((k, v) in fields) {
                            if (v.isNotBlank()) o.fields[k] = J.Str(v)
                        }
                        f.writeText(JsonS.stringify(o, pretty = true), Charsets.UTF_8)
                        val idx = roles.indexOfFirst { it.first == nm }
                        if (idx >= 0) roles[idx] = nm to prompt else roles.add(nm to prompt)
                        if (selectedRoles.contains(nm)) {
                            reloadMech()
                        }
                    } catch (_: Exception) {
                    }
                }
                roleEditName = null
            }) { Text(I18n.t("btn_save", "保存")) }
        },
        dismissButton = { TextButton(onClick = { roleEditName = null }) { Text(I18n.t("btn_cancel", "取消")) } },
    )
    if (rCardFacePrev) {
        AlertDialog(
            onDismissRequest = { rCardFacePrev = false },
            text = { HtmlCard(rCardFace.ifBlank { "<div style='color:#888;padding:20px'>（空卡面，保存后生效）</div>" }, Modifier.fillMaxWidth().height(400.dp)) },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { rCardFacePrev = false }) { Text(I18n.t("btn_cancel", "关闭")) } },
        )
    }
    }
}

/** 玩家角色卡编辑（结构化） */
@Composable
fun PersonaDialog(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val personaFields = deps.personaFields
    val saveConfig = deps.saveConfig
    val userDisplayName = deps.userDisplayName
    val avatarPicker = deps.avatarPicker
    val avatarCache = vm.avatarCache
    var persona by vm.persona
    var avatarTarget by vm.avatarTarget
    var showPersonaEdit by vm.showPersonaEdit
    if (showPersonaEdit) {
    var pf = personaFields()
    var pName by remember { mutableStateOf(pf["name"] ?: "") }
    var pLegacy by remember { mutableStateOf(pf["legacy"] ?: "") }
    var pAppearance by remember { mutableStateOf(pf["appearance"] ?: "") }
    var pPersonality by remember { mutableStateOf(pf["personality"] ?: "") }
    var pBackground by remember { mutableStateOf(pf["background"] ?: "") }
    var pSpeech by remember { mutableStateOf(pf["speech"] ?: "") }
    var pFirstMes by remember { mutableStateOf(pf["first_mes"] ?: "") }
    var pMesExample by remember { mutableStateOf(pf["mes_example"] ?: "") }
    var pNotes by remember { mutableStateOf(pf["notes"] ?: "") }
    val pAdvInit = try {
        (JsonS.parse(persona) as? J.Obj)?.fields?.get("advanced") as? J.Obj
    } catch (_: Exception) {
        null
    }
    val pBattleInit = pAdvInit?.fields?.get("battle") as? J.Obj
    var pBattleEnabled by remember { mutableStateOf(pBattleInit?.fields?.get("enabled")?.bool() == true) }
    var pBattleAttrs by remember {
        mutableStateOf((pBattleInit?.fields?.get("attrs") as? J.Obj)?.fields?.mapNotNull { (k, v) ->
            val a = v as? J.Obj ?: return@mapNotNull null
            listOf(k, a.fields["label"]?.str() ?: k,
                a.fields["initial"]?.int()?.toString() ?: "10",
                a.fields["max"]?.int()?.toString() ?: "").joinToString("|")
        }?.joinToString("\n") ?: "hp|生命|100|100\natk|攻击|10\ndef|防御|5")
    }
    var pBattleMech by remember {
        mutableStateOf((pBattleInit?.fields?.get("mech_attrs") as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { a ->
            val key = a.fields["key"]?.str() ?: return@mapNotNull null
            listOf(key, a.fields["label"]?.str() ?: key,
                a.fields["initial"]?.int()?.toString() ?: "10",
                a.fields["max"]?.int()?.toString() ?: "").joinToString("|")
        }?.joinToString("\n") ?: "")
    }
    var pRegex by remember {
        mutableStateOf((pAdvInit?.fields?.get("regex_rules") as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { x ->
            val id = x.fields["id"]?.str() ?: return@mapNotNull null
            listOf(id, x.fields["name"]?.str() ?: id, x.fields["pattern"]?.str() ?: "",
                x.fields["replace"]?.str() ?: "", x.fields["scope"]?.str() ?: "both").joinToString("|")
        }?.joinToString("\n") ?: "")
    }
    var foldPBattle by remember { mutableStateOf(pBattleEnabled) }
    var foldPRegex by remember { mutableStateOf(pRegex.isNotBlank()) }
    AlertDialog(
        onDismissRequest = { showPersonaEdit = false },
        title = { Text(I18n.t("btn_persona_card", "玩家角色卡")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(value = pName, onValueChange = { pName = it }, label = { Text("名字") }, singleLine = true)
                IconText("📜 完整设定（旧版原文，填了会整体覆盖，可留空）", fontSize = 11.sp, color = theme.muted, modifier = Modifier.padding(top = 6.dp))
                OutlinedTextField(value = pLegacy, onValueChange = { pLegacy = it }, label = { Text("Legacy 原文") }, minLines = 2)
                IconText("🎨 结构化字段（与角色卡同标准）", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 10.dp))
                OutlinedTextField(value = pAppearance, onValueChange = { pAppearance = it }, label = { Text("外貌") }, minLines = 2)
                OutlinedTextField(value = pPersonality, onValueChange = { pPersonality = it }, label = { Text("性格") }, minLines = 2)
                OutlinedTextField(value = pBackground, onValueChange = { pBackground = it }, label = { Text("过去经历") }, minLines = 2)
                OutlinedTextField(value = pSpeech, onValueChange = { pSpeech = it }, label = { Text("说话方式（语气/口癖/句式）") }, minLines = 2)
                OutlinedTextField(value = pFirstMes, onValueChange = { pFirstMes = it }, label = { Text("开场白") }, minLines = 2)
                OutlinedTextField(value = pMesExample, onValueChange = { pMesExample = it }, label = { Text("对话示例") }, minLines = 2)
                OutlinedTextField(value = pNotes, onValueChange = { pNotes = it }, label = { Text("备注") }, minLines = 2)
                FoldHead("⚔️ 玩家战斗属性（可选）", foldPBattle, onToggle = { foldPBattle = !foldPBattle })
                if (foldPBattle) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = pBattleEnabled, onCheckedChange = { pBattleEnabled = it })
                        Text("启用玩家战斗属性（结算用玩家属性；AI 用 [ph:-N] 打你）", fontSize = 12.sp)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedTextField(value = pBattleAttrs, onValueChange = { pBattleAttrs = it }, label = { Text("基础属性（每行 键|名|初值|上限）\n例：hp|生命|100|100") }, minLines = 4, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = pBattleMech, onValueChange = { pBattleMech = it }, label = { Text("机制属性（每行 键|名|初值|上限）\n例：spd|速度|8|100") }, minLines = 4, modifier = Modifier.weight(1f))
                    }
                }
                FoldHead("🔤 玩家专属正则（可选）", foldPRegex, onToggle = { foldPRegex = !foldPRegex })
                if (foldPRegex) {
                    OutlinedTextField(value = pRegex, onValueChange = { pRegex = it }, label = { Text("正则（每行 id|名称|正则|替换|作用域，对玩家输入生效）") }, minLines = 3)
                }
                TextButton(onClick = { avatarTarget = userDisplayName(); avatarPicker.launch("image/*") }) {
                    IconText("🧑 " + I18n.t("btn_avatar_persona", "玩家头像"), fontSize = 12.sp)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val oldName = personaFields()["name"]?.trim() ?: ""
                val newName = pName.trim()
                val o = J.Obj()
                o.fields["name"] = J.Str(newName)
                o.fields["legacy"] = J.Str(pLegacy.trim())
                o.fields["appearance"] = J.Str(pAppearance.trim())
                o.fields["personality"] = J.Str(pPersonality.trim())
                o.fields["background"] = J.Str(pBackground.trim())
                o.fields["speech"] = J.Str(pSpeech.trim())
                o.fields["first_mes"] = J.Str(pFirstMes.trim())
                o.fields["mes_example"] = J.Str(pMesExample.trim())
                o.fields["notes"] = J.Str(pNotes.trim())
                val padv = J.Obj()
                if (pBattleEnabled) {
                    val pb = J.Obj()
                    pb.fields["enabled"] = J.Bool(true)
                    val battrs = J.Obj()
                    pBattleAttrs.split("\n").forEach { line ->
                        val t = line.trim()
                        if (t.isEmpty()) return@forEach
                        val q = t.split("|")
                        if (q.size < 2) return@forEach
                        val key = q[0].trim()
                        if (key.isEmpty()) return@forEach
                        val a = J.Obj()
                        a.fields["label"] = J.Str(q[1].trim().ifEmpty { key })
                        a.fields["initial"] = J.Num((q.getOrNull(2)?.toIntOrNull() ?: 10).toDouble())
                        if (key == "hp" || q.getOrNull(3)?.isNotBlank() == true) {
                            a.fields["max"] = J.Num((q.getOrNull(3)?.toIntOrNull() ?: if (key == "hp") 100 else 999999).toDouble())
                        }
                        battrs.fields[key] = a
                    }
                    if (battrs.fields.isNotEmpty()) pb.fields["attrs"] = battrs
                    val bmech = J.Arr()
                    pBattleMech.split("\n").forEach { line ->
                        val t = line.trim()
                        if (t.isEmpty()) return@forEach
                        val q = t.split("|")
                        if (q.size < 2) return@forEach
                        val key = q[0].trim()
                        if (key.isEmpty()) return@forEach
                        val a = J.Obj()
                        a.fields["key"] = J.Str(key)
                        a.fields["label"] = J.Str(q[1].trim().ifEmpty { key })
                        a.fields["initial"] = J.Num((q.getOrNull(2)?.toIntOrNull() ?: 10).toDouble())
                        a.fields["max"] = J.Num((q.getOrNull(3)?.toIntOrNull() ?: 999999).toDouble())
                        bmech.items.add(a)
                    }
                    if (bmech.items.isNotEmpty()) pb.fields["mech_attrs"] = bmech
                    padv.fields["battle"] = pb
                }
                val prr = J.Arr()
                pRegex.split("\n").forEach { line ->
                    val t = line.trim()
                    if (t.isEmpty()) return@forEach
                    val q = t.split("|")
                    if (q.size < 4) return@forEach
                    val scope = q.getOrNull(4)?.trim()?.takeIf { it in setOf("ai", "user", "both") } ?: "both"
                    val x = J.Obj()
                    x.fields["id"] = J.Str(q[0].trim())
                    x.fields["name"] = J.Str(q[1].trim().ifEmpty { q[0].trim() })
                    x.fields["pattern"] = J.Str(q[2])
                    x.fields["replace"] = J.Str(q.drop(3).joinToString("|"))
                    x.fields["scope"] = J.Str(scope)
                    x.fields["enabled"] = J.Bool(true)
                    prr.items.add(x)
                }
                if (prr.items.isNotEmpty()) padv.fields["regex_rules"] = prr
                if (padv.fields.isNotEmpty()) o.fields["advanced"] = padv
                persona = JsonS.stringify(o, pretty = true)
                saveConfig()
                val effNew = newName.ifBlank { "你" }
                if (oldName != newName && oldName.isNotBlank() && oldName != effNew) {
                    val avDir = File(AppEnv.savesDir(), "avatars")
                    for (from in listOf(oldName, "你")) {
                        for (ext in listOf("png", "jpg", "jpeg", "webp")) {
                            val f = File(avDir, from + "." + ext)
                            if (f.exists()) {
                                val nf = File(avDir, effNew + "." + ext)
                                try {
                                    if (nf.exists()) nf.delete()
                                    f.renameTo(nf)
                                } catch (_: Exception) {
                                }
                                break
                            }
                        }
                    }
                    avatarCache.remove(oldName)
                    avatarCache.remove("你")
                    avatarCache.remove(effNew)
                }
                showPersonaEdit = false
            }) { Text(I18n.t("btn_save", "保存")) }
        },
        dismissButton = { TextButton(onClick = { showPersonaEdit = false }) { Text(I18n.t("btn_cancel", "取消")) } },
    )
    }
}

/** 头像交互式裁剪（Canvas 绘制：显示与裁剪同一套数学） */
@Composable
fun AvatarCropDialog(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val cropBitmap = vm.cropBitmap
    val avatarTarget = vm.avatarTarget
    var cropScale by vm.cropScale
    var cropDx by vm.cropDx
    var cropDy by vm.cropDy
    var cropStagePx by vm.cropStagePx
    if (cropBitmap.value != null && avatarTarget.value != null) {
        val bmp = cropBitmap.value!!
        AlertDialog(
            onDismissRequest = { vm.cropBitmap.value = null; vm.avatarTarget.value = null },
            title = { IconText("✂️ 裁剪头像") },
            text = {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(
                        modifier = Modifier
                            .size(280.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(Color(0xFF111111))
                            .onSizeChanged { cropStagePx = it.width.toFloat() }
                            .pointerInput(bmp) {
                                detectTransformGestures { _, pan, zoom, _ ->
                                    cropScale = (cropScale * zoom).coerceIn(0.4f, 6f)
                                    cropDx += pan.x
                                    cropDy += pan.y
                                }
                            }
                    ) {
                        Canvas(modifier = Modifier.fillMaxSize()) {
                            val s = size.width
                            val baseFit = minOf(s / bmp.width, s / bmp.height)
                            val dispW = bmp.width * baseFit * cropScale
                            val dispH = bmp.height * baseFit * cropScale
                            val imgLeft = (s - bmp.width * baseFit) / 2f + cropDx
                            val imgTop = (s - bmp.height * baseFit) / 2f + cropDy
                            drawImage(
                                image = bmp.asImageBitmap(),
                                dstSize = IntSize(dispW.toInt(), dispH.toInt()),
                                dstOffset = IntOffset(imgLeft.toInt(), imgTop.toInt())
                            )
                            val inset = s * 0.23f
                            drawRect(Color(0x99000000), topLeft = Offset(0f, 0f), size = Size(s, inset))
                            drawRect(Color(0x99000000), topLeft = Offset(0f, s - inset), size = Size(s, inset))
                            drawRect(Color(0x99000000), topLeft = Offset(0f, inset), size = Size(inset, s - inset * 2))
                            drawRect(Color(0x99000000), topLeft = Offset(s - inset, inset), size = Size(inset, s - inset * 2))
                            drawRect(Color.White, topLeft = Offset(inset, inset),
                                size = Size(s - inset * 2, s - inset * 2),
                                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 6f))
                        }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
                        IconText("🔍", fontSize = 12.sp)
                        Slider(
                            value = cropScale,
                            onValueChange = { cropScale = it },
                            valueRange = 0.4f..6f,
                            modifier = Modifier.weight(1f).padding(horizontal = 4.dp)
                        )
                        IconText("🔍", fontSize = 16.sp)
                    }
                    Text("拖动调整位置 · 双指/滑条缩放（0.4x 焦距拉远 ~ 6x 放大）", fontSize = 11.sp, color = theme.muted)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    try {
                        val b = vm.cropBitmap.value ?: return@TextButton
                        val t = vm.avatarTarget.value ?: return@TextButton
                        val s = cropStagePx
                        val out = android.graphics.Bitmap.createBitmap(256, 256, android.graphics.Bitmap.Config.ARGB_8888)
                        val cvs = android.graphics.Canvas(out)
                        var drew = false
                        if (s > 4f && b.width > 0 && b.height > 0) {
                            val baseFit = minOf(s / b.width, s / b.height)
                            val dispW = b.width * baseFit * cropScale
                            val dispH = b.height * baseFit * cropScale
                            val imgLeft = (s - b.width * baseFit) / 2f + cropDx
                            val imgTop = (s - b.height * baseFit) / 2f + cropDy
                            val inset = s * 0.23f
                            val sqSize = s - inset * 2
                            val srcX = (inset - imgLeft) / dispW * b.width
                            val srcY = (inset - imgTop) / dispH * b.height
                            val srcSize = sqSize / dispW * b.width
                            val sx = srcX.coerceIn(0f, b.width.toFloat())
                            val sy = srcY.coerceIn(0f, b.height.toFloat())
                            val ss = srcSize.coerceAtMost(b.width - sx).coerceAtMost(b.height - sy)
                            if (ss > 4f) {
                                val srcRect = android.graphics.Rect(sx.toInt(), sy.toInt(), (sx + ss).toInt(), (sy + ss).toInt())
                                cvs.drawBitmap(b, srcRect, android.graphics.Rect(0, 0, 256, 256), null)
                                drew = true
                            }
                        }
                        if (!drew) {
                            val side = minOf(b.width, b.height)
                            val fx = (b.width - side) / 2
                            val fy = (b.height - side) / 2
                            cvs.drawBitmap(b, android.graphics.Rect(fx, fy, fx + side, fy + side),
                                android.graphics.Rect(0, 0, 256, 256), null)
                        }
                        val bos = java.io.ByteArrayOutputStream()
                        out.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, bos)
                        val dir = File(AppEnv.savesDir(), "avatars").apply { mkdirs() }
                        File(dir, t + ".png").writeBytes(bos.toByteArray())
                        vm.avatarCache.remove(t)
                    } catch (_: Exception) {
                    }
                    vm.cropBitmap.value = null
                    vm.avatarTarget.value = null
                }) { IconText("✅ 确认") }
            },
            dismissButton = { TextButton(onClick = { vm.cropBitmap.value = null; vm.avatarTarget.value = null }) { Text("取消") } },
        )
    }
}

/** 选世界（多选=平行世界） */
@Composable
fun WorldsDialog(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val accent = deps.accent
    val worlds = vm.worlds
    var selectedWorlds by vm.selectedWorlds
    var currentWorld by deps.currentWorld
    var showWorlds by vm.showWorlds
    var showWorldEdit by vm.showWorldEdit
    var pendingDelete by vm.pendingDelete
    if (showWorlds) {
        AlertDialog(
            onDismissRequest = { showWorlds = false },
            title = { Text(I18n.t("dlg_worlds", "选择世界（多选=平行世界）")) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    for ((n, _) in worlds) {
                        Row {
                            Checkbox(checked = n in selectedWorlds, onCheckedChange = { ck ->
                                selectedWorlds = if (ck) selectedWorlds + n else selectedWorlds - n
                                if (currentWorld !in selectedWorlds) currentWorld = selectedWorlds.firstOrNull() ?: ""
                            })
                            Text(n, Modifier.padding(top = 14.dp))
                            if (n == currentWorld) Text("★", Modifier.padding(top = 14.dp), color = accent, fontSize = 12.sp)
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = { currentWorld = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText("🚀", fontSize = 14.sp) }
                            TextButton(onClick = { showWorldEdit = n }, modifier = Modifier.heightIn(min = 44.dp)) { IconText(I18n.t("btn_edit", "✏️"), fontSize = 14.sp) }
                            TextButton(onClick = { pendingDelete = n to "world" }, modifier = Modifier.heightIn(min = 44.dp)) { Text(I18n.t("btn_delete", "删除"), color = theme.danger, fontSize = 12.sp) }
                        }
                    }
                }
            },
            confirmButton = {
                Row {
                    TextButton(onClick = { showWorldEdit = "" }) { Text(I18n.t("btn_new_world", "新建世界"), fontSize = 12.sp) }
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { showWorlds = false }) { Text("完成") }
                }
            },
        )
    }
}

/** 世界卡编辑 */
@Composable
fun WorldEditDialog(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val worlds = vm.worlds
    val worldEntries = vm.worldEntries
    var showWorldEdit by vm.showWorldEdit
    if (showWorldEdit != null) {
        val editing = showWorldEdit!!
        var wName by remember { mutableStateOf(editing) }
        var wDesc by remember { mutableStateOf("") }
        var wRules by remember { mutableStateOf("") }
        val paramsState = remember { mutableStateMapOf<String, String>() }
        val entriesState = remember { mutableStateListOf<WorldEntry>() }
        LaunchedEffect(editing) {
            if (editing.isNotBlank() && wDesc.isEmpty() && entriesState.isEmpty()) {
                try {
                    val wo = JsonS.parse(File(AppEnv.worldsDir(), editing + ".json").readText(Charsets.UTF_8)) as? J.Obj
                    if (wo != null) {
                        wDesc = wo.fields["description"]?.str() ?: ""
                        (wo.fields["params"] as? J.Obj)?.fields?.forEach { (k, v) -> v.str()?.let { paramsState[k] = it } }
                    }
                } catch (_: Exception) {
                }
                worldEntries[editing]?.let { entriesState.addAll(it) }
            }
        }
        AlertDialog(
            onDismissRequest = { showWorldEdit = null },
            title = { Text(I18n.t("dlg_world_edit", "编辑世界卡")) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    OutlinedTextField(value = wName, onValueChange = { wName = it }, label = { Text(I18n.t("lbl_world_name", "名字")) }, singleLine = true)
                    OutlinedTextField(value = wDesc, onValueChange = { wDesc = it }, label = { Text(I18n.t("lbl_world_desc", "背景描述")) }, minLines = 2)
                    OutlinedTextField(value = wRules, onValueChange = { wRules = it }, label = { Text(I18n.t("lbl_world_rules", "规则（每行一条）")) }, minLines = 2)
                    Spacer(Modifier.height(6.dp))
                    Text(I18n.t("wm_params", "世界参数（物理系统等）"), color = theme.muted, fontSize = 13.sp)
                    for ((k, label) in WORLD_PARAM_LABELS) {
                        OutlinedTextField(
                            value = paramsState[k] ?: "",
                            onValueChange = { paramsState[k] = it },
                            label = { Text(label) },
                            singleLine = true,
                        )
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(I18n.t("world_entries", "世界书条目（关键词触发，可空）"), color = theme.muted, fontSize = 13.sp)
                    entriesState.forEachIndexed { idx, e ->
                        Column(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                            Row {
                                Checkbox(checked = e.enabled, onCheckedChange = { entriesState[idx] = e.copy(enabled = it) })
                                Text(I18n.t("entry_enabled", "启用"), Modifier.padding(top = 14.dp), fontSize = 12.sp)
                                Checkbox(checked = e.constant, onCheckedChange = { entriesState[idx] = e.copy(constant = it) })
                                Text(I18n.t("entry_constant", "常驻"), Modifier.padding(top = 14.dp), fontSize = 12.sp)
                                Spacer(Modifier.weight(1f))
                                TextButton(onClick = { entriesState.removeAt(idx) }) {
                                    Text(I18n.t("entry_delete", "✕"), color = theme.danger, fontSize = 12.sp)
                                }
                            }
                            OutlinedTextField(
                                value = e.keywords.joinToString(", "),
                                onValueChange = { v ->
                                    entriesState[idx] = e.copy(keywords = v.split(',').map { it.trim() }.filter { it.isNotEmpty() }.toMutableList())
                                },
                                label = { Text(I18n.t("entry_keywords", "关键词（逗号分隔）")) },
                                singleLine = true,
                            )
                            Row {
                                TextButton(onClick = {
                                    entriesState[idx] = e.copy(match = when (e.match) { "any" -> "all"; "all" -> "regex"; else -> "any" })
                                }) {
                                    Text(
                                        I18n.t("entry_match", "匹配") + "：" + when (e.match) {
                                            "all" -> I18n.t("match_all", "all")
                                            "regex" -> I18n.t("match_regex", "regex")
                                            else -> I18n.t("match_any", "any")
                                        },
                                        fontSize = 12.sp,
                                    )
                                }
                                OutlinedTextField(
                                    value = e.weight.toString(),
                                    onValueChange = { v -> entriesState[idx] = e.copy(weight = v.toIntOrNull() ?: 0) },
                                    label = { Text(I18n.t("entry_weight", "权重")) },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                )
                                OutlinedTextField(
                                    value = e.probability.toString(),
                                    onValueChange = { v -> entriesState[idx] = e.copy(probability = v.toIntOrNull() ?: 100) },
                                    label = { Text(I18n.t("entry_probability", "概率%")) },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                )
                                OutlinedTextField(
                                    value = e.depth.toString(),
                                    onValueChange = { v -> entriesState[idx] = e.copy(depth = (v.toIntOrNull() ?: 1).coerceIn(1, 4)) },
                                    label = { Text(I18n.t("entry_depth", "深度")) },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                )
                            }
                            OutlinedTextField(
                                value = e.content,
                                onValueChange = { v -> entriesState[idx] = e.copy(content = v) },
                                label = { Text(I18n.t("entry_content", "内容")) },
                                minLines = 2,
                            )
                        }
                    }
                    TextButton(onClick = { entriesState.add(WorldEntry()) }) { Text(I18n.t("btn_add_entry", "＋ 添加条目")) }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val nm = wName.trim()
                    if (nm.isNotBlank() && wDesc.isNotBlank()) {
                        val wd = WorldData(
                            name = nm,
                            description = wDesc.trim(),
                            rules = wRules.split('\n').map { it.trim() }.filter { it.isNotEmpty() }.toMutableList(),
                            entries = entriesState.toMutableList(),
                            params = paramsState.toMutableMap(),
                        )
                        File(AppEnv.worldsDir(), nm + ".json").writeText(JsonS.stringify(wd.toJson(), pretty = true), Charsets.UTF_8)
                        worldEntries[nm] = entriesState.toMutableList()
                        val renderedDesc = renderWorldDesc(wDesc.trim(), paramsState.toMap())
                        val idx = worlds.indexOfFirst { it.first == nm }
                        if (idx >= 0) worlds[idx] = nm to renderedDesc else worlds.add(nm to renderedDesc)
                        if (editing.isNotBlank() && editing != nm) {
                            worlds.removeAll { it.first == editing }
                            worldEntries.remove(editing)
                            try { File(AppEnv.worldsDir(), editing + ".json").delete() } catch (_: Exception) {}
                        }
                        showWorldEdit = null
                    }
                }) { Text(I18n.t("btn_save", "保存")) }
            },
            dismissButton = { TextButton(onClick = { showWorldEdit = null }) { Text(I18n.t("btn_cancel", "取消")) } },
        )
    }
}

/** 编辑消息 */
@Composable
fun EditMsgDialog(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val editMessage = deps.editMessage
    var editMsgTarget by vm.editMsgTarget
    var editMsgText by vm.editMsgText
    if (editMsgTarget != null) {
        val target = editMsgTarget!!
        AlertDialog(
            onDismissRequest = { editMsgTarget = null },
            title = { Text(I18n.t("edit_title", "编辑消息")) },
            text = {
                Column {
                    Text(
                        if (target.role == "你") I18n.t("edit_user_hint", "编辑后重新生成回复（保留旧分支）")
                        else I18n.t("edit_ai_hint", "原地修改这条 AI 回复"),
                        fontSize = 11.sp,
                        color = theme.muted,
                    )
                    OutlinedTextField(value = editMsgText, onValueChange = { editMsgText = it }, minLines = 3)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val t = target
                    editMsgTarget = null
                    editMessage(t, editMsgText.trim())
                }) { Text(I18n.t("btn_save", "保存")) }
            },
            dismissButton = { TextButton(onClick = { editMsgTarget = null }) { Text(I18n.t("btn_cancel", "取消")) } },
        )
    }
}

/** 创意工坊 */
@Composable
fun WorkshopDialog(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val scope = deps.scope
    val importCardLauncher = deps.importCardLauncher
    val wsExportLauncher = deps.wsExportLauncher
    val wsRefreshLocal = deps.wsRefreshLocal
    val wsLoadOnline = deps.wsLoadOnline
    val wsLoadPlugins = deps.wsLoadPlugins
    val wsUploadLocal = deps.wsUploadLocal
    val wsSearchOnline = deps.wsSearchOnline
    val wsDownloadSelected = deps.wsDownloadSelected
    val wsLikeSelected = deps.wsLikeSelected
    val wsDeleteSelected = deps.wsDeleteSelected
    val wsInstallPlugin = deps.wsInstallPlugin
    val reloadRolesFromDisk = deps.reloadRolesFromDisk
    val reloadWorldsFromDisk = deps.reloadWorldsFromDisk
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
    if (showWorkshop) {
    AlertDialog(
        onDismissRequest = { showWorkshop = false },
        title = { IconText(I18n.t("btn_workshop", "🧰 创意工坊")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Row {
                    TextButton(onClick = { wsTabOnline = false; wsTabPlugin = false; wsRefreshLocal() }) {
                        IconText(if (!wsTabOnline && !wsTabPlugin) I18n.t("ws_local", "📂 本地 ▾") else I18n.t("ws_local", "📂 本地"), fontSize = 12.sp)
                    }
                    TextButton(onClick = { wsTabOnline = true; wsTabPlugin = false; wsLoadOnline() }) {
                        IconText(if (wsTabOnline) I18n.t("ws_online", "🌐 在线 ▾") else I18n.t("ws_online", "🌐 在线"), fontSize = 12.sp)
                    }
                    TextButton(onClick = { wsTabPlugin = true; wsTabOnline = false; wsLoadPlugins() }) {
                        IconText(if (wsTabPlugin) "🔌 插件 ▾" else "🔌 插件", fontSize = 12.sp)
                    }
                    Spacer(Modifier.weight(1f))
                    Text(wsStatus, fontSize = 11.sp, color = theme.muted)
                }
                if (!wsTabOnline && !wsTabPlugin) {
                    Row {
                        Column(Modifier.weight(1f)) {
                            IconText("📂 角色卡", fontSize = 12.sp, color = theme.muted)
                            wsLocalRoles.forEachIndexed { i, f ->
                                val sel = wsLocalType == "角色卡" && wsLocalIdx == i
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = if (sel) Color(0xFF182636) else Color(0xFF0F1620),
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp).clickable {
                                        wsLocalType = "角色卡"; wsLocalIdx = i
                                        wsPreview = Workshop.preview("角色卡", f)
                                    },
                                ) {
                                    Text(f.removeSuffix(".json"), fontSize = 12.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp), maxLines = 1)
                                }
                            }
                        }
                        Column(Modifier.weight(1f)) {
                            IconText("🌍 世界卡", fontSize = 12.sp, color = theme.muted)
                            wsLocalWorlds.forEachIndexed { i, f ->
                                val sel = wsLocalType == "世界卡" && wsLocalIdx == i
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = if (sel) Color(0xFF182636) else Color(0xFF0F1620),
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp).clickable {
                                        wsLocalType = "世界卡"; wsLocalIdx = i
                                        wsPreview = Workshop.preview("世界卡", f)
                                    },
                                ) {
                                    Text(f.removeSuffix(".json"), fontSize = 12.sp, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp), maxLines = 1)
                                }
                            }
                        }
                    }
                    if (wsPreview.isNotBlank()) {
                        Surface(shape = RoundedCornerShape(10.dp), color = Color(0xFF0B1220), modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                            Text(wsPreview, fontSize = 11.sp, color = Color(0xFFCBD5E1), modifier = Modifier.padding(10.dp), maxLines = 10)
                        }
                    }
                    Row {
                        TextButton(onClick = {
                            importCardLauncher.launch(arrayOf("image/png", "image/webp", "application/json"))
                        }) { IconText(I18n.t("btn_import_card", "📥 导入"), fontSize = 12.sp) }
                        TextButton(onClick = {
                            val fname = if (wsLocalType == "角色卡") wsLocalRoles.getOrNull(wsLocalIdx)
                                else wsLocalWorlds.getOrNull(wsLocalIdx)
                            if (fname != null) { wsExportTarget = fname; wsExportLauncher.launch(fname) }
                        }) { IconText(I18n.t("ws_export", "📤 导出"), fontSize = 12.sp) }
                        TextButton(onClick = {
                            val fname = if (wsLocalType == "角色卡") wsLocalRoles.getOrNull(wsLocalIdx)
                                else wsLocalWorlds.getOrNull(wsLocalIdx)
                            if (fname != null) {
                                if (Workshop.deleteLocal(wsLocalType, fname)) {
                                    wsPreview = ""
                                    wsLocalIdx = -1
                                    wsRefreshLocal()
                                    reloadRolesFromDisk()
                                    reloadWorldsFromDisk()
                                    wsStatus = "✅ 已删除"
                                }
                            }
                        }) { IconText(I18n.t("ws_delete", "🗑️ 删除"), fontSize = 12.sp, color = theme.danger) }
                        TextButton(onClick = { wsUploadLocal() }) { IconText(I18n.t("ws_upload", "📤 上传"), fontSize = 12.sp) }
                    }
                } else if (wsTabOnline) {
                    Text(
                        if (wsServerInput.isNotBlank()) "🛰️ 自动连接：" + wsServerInput else "🛰️ 自动连接中...",
                        fontSize = 12.sp, color = theme.muted,
                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                    )
                    OutlinedTextField(value = wsKeyInput, onValueChange = { wsKeyInput = it },
                        label = { Text(I18n.t("ws_key", "Key（可选）")) }, singleLine = true)
                    Row {
                        TextButton(onClick = {
                            Workshop.saveConfig(Workshop.serverUrl, wsKeyInput)
                            wsStatus = "检测中..."
                            scope.launch(Dispatchers.IO) {
                                val active = try { Workshop.activeServer() } catch (e: Exception) { "" }
                                val h = try { Workshop.health() } catch (e: Exception) { null }
                                val s = try { Workshop.stats() } catch (e: Exception) { null }
                                scope.launch(Dispatchers.Main) {
                                    if (active.isNotBlank()) wsServerInput = active
                                    if (h != null) {
                                        val auth = h.fields["auth"]?.str() ?: "open"
                                        val dl = (s?.fields?.get("downloads") as? J.Num)?.v?.toInt() ?: 0
                                        val lk = (s?.fields?.get("likes") as? J.Num)?.v?.toInt() ?: 0
                                        wsStatus = "✅ 已连接（认证:" + auth + " · ↓" + dl + " ❤" + lk + "）"
                                    } else wsStatus = "❌ 连接失败"
                                }
                            }
                        }) { IconText(I18n.t("ws_test", "🔄 重新检测"), fontSize = 12.sp) }
                        Spacer(Modifier.weight(1f))
                        OutlinedTextField(value = wsSearchInput, onValueChange = { wsSearchInput = it },
                            label = { Text(I18n.t("ws_search", "搜索")) }, singleLine = true, modifier = Modifier.width(110.dp))
                        TextButton(onClick = { wsSearchOnline() }) { IconText("🔍", fontSize = 12.sp) }
                    }
                    TextButton(onClick = { wsLoadOnline() }) { Text("全部作品", fontSize = 12.sp) }
                    wsOnlineList.forEachIndexed { i, r ->
                        val t = r.fields["_type"]?.str() ?: "角色卡"
                        val name = r.fields["name"]?.str() ?: "?"
                        val author = r.fields["author"]?.str() ?: "?"
                        val dl = (r.fields["downloads"] as? J.Num)?.v?.toInt() ?: 0
                        val lk = (r.fields["likes"] as? J.Num)?.v?.toInt() ?: 0
                        val tags = (r.fields["tags"] as? J.Arr)?.items?.mapNotNull { it.str() } ?: emptyList()
                        val desc = r.fields["description"]?.str() ?: ""
                        val sel = i == wsOnlineIdx
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = if (sel) Color(0xFF182636) else Color(0xFF0F1620),
                            modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp).clickable { wsOnlineIdx = i },
                        ) {
                            Column(Modifier.padding(10.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text((if (t == "角色卡") "🎭 " else "🌍 ") + name, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                    Text("↓" + dl + "  ❤" + lk, fontSize = 11.sp, color = theme.muted)
                                }
                                Text(author, fontSize = 11.sp, color = theme.muted)
                                if (tags.isNotEmpty()) Text(tags.joinToString(" · "), fontSize = 10.sp, color = Color(0xFF6B7280))
                                if (desc.isNotBlank()) Text(desc, fontSize = 11.sp, color = Color(0xFFCBD5E1), maxLines = 2)
                            }
                        }
                    }
                    val selR = wsOnlineList.getOrNull(wsOnlineIdx)
                    if (selR != null) {
                        val t = selR.fields["_type"]?.str() ?: "角色卡"
                        val name = selR.fields["name"]?.str() ?: "?"
                        val author = selR.fields["author"]?.str() ?: "?"
                        val dl = (selR.fields["downloads"] as? J.Num)?.v?.toInt() ?: 0
                        val lk = (selR.fields["likes"] as? J.Num)?.v?.toInt() ?: 0
                        val tags = (selR.fields["tags"] as? J.Arr)?.items?.mapNotNull { it.str() } ?: emptyList()
                        val desc = selR.fields["description"]?.str() ?: ""
                        val created = selR.fields["created_at"]?.str() ?: ""
                        val preview = selR.fields["system_prompt_preview"]?.str() ?: ""
                        Surface(shape = RoundedCornerShape(12.dp), color = Color(0xFF0B1220), modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                            Column(Modifier.padding(12.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text((if (t == "角色卡") "🎭 " else "🌍 ") + name, fontSize = 15.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                                    Text("↓" + dl + "  ❤" + lk, fontSize = 12.sp, color = theme.muted)
                                }
                                Text("作者：" + author, fontSize = 12.sp, color = theme.muted)
                                if (created.isNotBlank()) Text("上传：" + created.take(10), fontSize = 10.sp, color = Color(0xFF6B7280))
                                if (tags.isNotEmpty()) Text("标签：" + tags.joinToString(" · "), fontSize = 11.sp, color = theme.muted)
                                if (desc.isNotBlank()) Text(desc, fontSize = 13.sp, color = theme.text)
                                if (preview.isNotBlank()) Text("人设：" + preview.take(120), fontSize = 11.sp, color = Color(0xFF6B7280), maxLines = 4)
                            }
                        }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { wsDownloadSelected() }) { IconText(I18n.t("ws_download", "⬇️ 下载"), fontSize = 12.sp) }
                        TextButton(onClick = { wsLikeSelected() }) { IconText(I18n.t("ws_like", "❤️ 点赞"), fontSize = 12.sp) }
                        TextButton(onClick = { wsDeleteSelected() }) { IconText(I18n.t("ws_delete", "🗑️ 删除"), fontSize = 12.sp, color = theme.danger) }
                    }
                } else {
                    if (wsPlugins.isEmpty()) {
                        Text("🔌 插件市场暂无内容（工坊服务器未启动或未上传插件）", fontSize = 12.sp, color = theme.muted)
                    }
                    wsPlugins.forEach { p ->
                        val id = p.fields["id"]?.str() ?: return@forEach
                        val name = p.fields["name"]?.str() ?: "?"
                        val ver = p.fields["version"]?.str() ?: "1.0"
                        val author = p.fields["author"]?.str() ?: "?"
                        val desc = p.fields["description"]?.str() ?: ""
                        val dl = (p.fields["downloads"] as? J.Num)?.v?.toInt() ?: 0
                        val installed = wsLocalPlugins.any {
                            it == name || it == (p.fields["original_name"]?.str()?.removeSuffix(".py"))
                        }
                        Surface(
                            color = theme.bubble,
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
                        ) {
                            Column(Modifier.padding(8.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text("🔌 $name", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                                    Text("v$ver · $author · ↓$dl", fontSize = 10.sp, color = theme.muted)
                                }
                                if (desc.isNotBlank()) {
                                    Text(desc, fontSize = 11.sp, color = theme.muted, maxLines = 2)
                                }
                                if (installed) {
                                    Text("✅ 已安装", fontSize = 11.sp, color = Color(0xFF4ADE80))
                                } else {
                                    TextButton(
                                        onClick = { wsInstallPlugin(id) },
                                        enabled = wsInstallingId != id,
                                    ) {
                                        IconText(if (wsInstallingId == id) "⏳ 安装中..." else "⬇️ 安装", fontSize = 12.sp)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = { showWorkshop = false }) { Text(I18n.t("btn_cancel", "取消")) } },
    )
    }
}

/** 顶栏 📂 文件夹 = 下拉菜单：人物卡 + 世界卡 都在这里直接勾选（编辑/导入/导出/删除留在抽屉） */
@Composable
fun FolderMenu(vm: ChatViewModel, deps: DialogDeps) {
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
        // 切换到新角色的聊天树
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
        TextButton(onClick = { expanded = true }) { IconText("📂", fontSize = 16.sp) }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier.width(240.dp),
        ) {
            // 内容直接放 DropdownMenu 的 ColumnScope 里（它内部自带滚动），
            // 不要在外层再套 verticalScroll / 宽度高度——会触发测量递归 StackOverflow。
            Text("👥 人物卡（" + selectedRoles.size + "）", fontSize = 12.sp, color = theme.muted, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
            if (roles.isEmpty()) {
                Text("（暂无 · 抽屉 → 角色 新建/导入）", fontSize = 11.sp, color = theme.muted, modifier = Modifier.padding(horizontal = 14.dp, vertical = 2.dp))
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
            Text("🌍 世界卡（" + selectedWorlds.size + "）", fontSize = 12.sp, color = theme.muted, modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
            if (worlds.isEmpty()) {
                Text("（暂无 · 抽屉 → 世界 新建）", fontSize = 11.sp, color = theme.muted, modifier = Modifier.padding(horizontal = 14.dp, vertical = 2.dp))
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
                text = { IconText("⚙ 人物卡管理（编辑/导入/导出/删除）", fontSize = 12.sp) },
                onClick = { expanded = false; vm.showRoles.value = true },
            )
            DropdownMenuItem(
                text = { IconText("⚙ 世界卡管理（编辑/新建/删除）", fontSize = 12.sp) },
                onClick = { expanded = false; vm.showWorlds.value = true },
            )
        }
    }
}
