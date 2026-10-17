package com.dick.app

import android.widget.Toast
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.ChatTree
import com.dick.core.J
import com.dick.core.MechanicsEngine

/**
 * 回档（树状回溯：主线平铺 + 分支收纳 + 点击跳回）+ 二维分支树图。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `BranchesDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[BranchesDialog]（在 Dialogs.kt 末尾），转调 [BranchesScreen]。
 */
/** 回档（树状回溯：主线平铺 + 分支收纳 + 点击跳回） */
@Composable
fun BranchesScreen(
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
    // 分支树原来是一块写死的「灰白 MC 成就风」浅色面板（30 多个 hex），压在深色画布上像贴纸。
    // 改成令牌语义：灰阶层次用 surface/surface_2 + border/border_strong 表达，正文走 text/textSub，
    // 「当前节点」用 accent 描一圈 —— 强调色只留给"当前进度"这一件事。
    val pal = LocalDickPalette.current
    var branchMode by remember { mutableStateOf(false) }
    Column {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { branchMode = false }) { IconText("🔀 回档", fontSize = 12.sp, iconSize = 13.dp, fontWeight = if (!branchMode) FontWeight.Bold else null, color = if (!branchMode) accent else Color.Unspecified) }
            TextButton(onClick = { branchMode = true }) { IconText("✏️ 建分支", fontSize = 12.sp, iconSize = 13.dp, fontWeight = if (branchMode) FontWeight.Bold else null, color = if (branchMode) accent else Color.Unspecified) }
            Spacer(Modifier.weight(1f))
            Text(if (branchMode) "点节点=从这点继续 · 下一条会分出新分支" else "点节点=跳回那里", fontSize = 10.sp, color = pal.textSub)
        }
    Box(
        Modifier.fillMaxWidth().height(470.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(pal.bg)
            .onSizeChanged { viewW = it.width; viewH = it.height }
            .pointerInput(Unit) {
                detectTransformGestures { _, pan, zoom, _ ->
                    scale = (scale * zoom).coerceIn(0.25f, 3f)
                    panX += pan.x; panY += pan.y
                }
            }
    ) {
        // Canvas 的 draw lambda 不是 composable，颜色必须先在外面取好
        val edgeOn = pal.borderStrong
        val edgeOff = pal.border
        Canvas(Modifier.fillMaxSize()) {
            fun s(wx: Float, wy: Float): Offset = Offset(wx * xSpacing * scale + panX, wy * ySpacing * scale + panY)
            edges.forEach { (a, b) ->
                val c = if (b.onPath) edgeOn else edgeOff
                drawLine(c, s(a.x, a.y), s(b.x, b.y), strokeWidth = 2f)
            }
        }
        nodes.forEach { n ->
            val px = n.x * xSpacing * scale + panX
            val py = n.y * ySpacing * scale + panY
            val chipW = 138f; val chipH = 42f
            // 灰白成就（MC pr<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ogress 风）配色
            // 节点配色：层次靠 surface / surface_2 与 border / border_strong 的对比，不靠六种灰
            val bg = when {
                n.isCurrent -> pal.surface2
                n.isOption -> pal.surface
                n.onPath -> pal.surface2
                else -> pal.surface
            }
            val border = when {
                n.isCurrent -> pal.borderStrong   // 当前：最强描边
                n.isOption -> pal.borderStrong
                n.onPath -> pal.border
                else -> pal.border
            }
            val tc = when {
                n.isCurrent -> pal.text
                n.onPath -> pal.text
                else -> pal.textSub
            }
            Box(
                Modifier
                    .offset { IntOffset((px - chipW / 2).toInt(), (py - chipH / 2).toInt()) }
                    .size(chipW.dp, chipH.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(bg)
                    .border(2.dp, border, RoundedCornerShape(8.dp))
                    .then(if (n.isCurrent) Modifier.border(1.dp, pal.accent, RoundedCornerShape(8.dp)) else Modifier)
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
                            .background(pal.surface2)
                            .border(1.dp, pal.border, RoundedCornerShape(5.dp)),
                        contentAlignment = Alignment.Center,
                    ) { IconText(ic, fontSize = 8.sp, color = tc, iconSize = 9.dp) }
                    Spacer(Modifier.width(5.dp))
                    Column {
                        Text((if (n.isOption) "▣ " else "") + n.content.ifBlank { "（空）" },
                            fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, color = tc)
                        Text(if (n.isCurrent) "当前进度" else if (n.isOption) "选项节点" else (if (n.onPath) "当前剧情线" else "分支剧情"),
                            fontSize = 8.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, color = pal.textDim)
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
                        .background(pal.surface2)
                        .border(1.dp, pal.border, RoundedCornerShape(4.dp))
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
                        color = pal.textSub, modifier = Modifier.padding(horizontal = 4.dp))
                }
            }
        }
    }
    }
}
