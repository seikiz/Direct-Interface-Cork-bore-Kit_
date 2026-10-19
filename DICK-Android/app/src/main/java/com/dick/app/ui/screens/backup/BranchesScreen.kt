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
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
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

/* ============================================================
 *  分支图布局常量（**全部是 dp**；坐标只在成图时换算一次 px）
 *
 *  2026-12 修的 bug：原来坐标 `px = n.x * xSpacing * scale + panX`（px，且乘了 scale），
 *  卡片却是 `.size(chipW.dp, chipH.dp)`（dp，**不**乘 scale）。两种单位混着用，密度越高越叠：
 *   · 2.75 密度下卡片高 42dp = 115.5px，而层间距只有 96 × 0.8 = 76.8px
 *   · → 相邻两层重叠 38.7px，下一张卡片的顶部文字从上一张里透出来（用户截图"四行字叠一起"）
 *   · 横向更糟：卡片宽 138dp = 379.5px，列间距 150 × 0.8 = 120px，整排全叠
 *  现在**缩放只由 graphicsLayer 统一施加**（卡片与连线一起缩），间距与卡片都是 dp，
 *  所以"叠不叠"与屏幕密度无关 —— 这正是下面两条不等式能被测试钉住的原因：
 *    横向：X_SPACING_DP ≥ CHIP_W_DP + 16
 *    纵向：Y_SPACING_DP ≥ CHIP_H_DP + 20
 *          且 ≥ CHIP_H_DP + OPTION_GAP_DP + OPTIONS_MAX × OPTION_H_DP + 12（选项小签挂在卡片下面）
 *  验：tests/test_branch_graph_layout.py（改小间距 / 再把 scale 乘回坐标 → 红）
 * ============================================================ */
private const val CHIP_W_DP = 150f
private const val CHIP_H_DP = 52f
private const val X_SPACING_DP = 176f
private const val Y_SPACING_DP = 140f
private const val OPTION_H_DP = 20f
private const val OPTION_GAP_DP = 4f
private const val OPTIONS_MAX = 3
private const val GRAPH_H_DP = 470f
private const val MIN_SCALE = 0.25f
private const val MAX_SCALE = 3f
private const val FIT_MAX_SCALE = 2.2f

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
        DickDialog(
            onDismissRequest = { showBranches = false },
            title = { IconText("回档（二维分支 · 双指缩放/拖动 · 点节点跳到那里）", icon = "account_tree") },
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
        // 不再 take(16)：卡片固定宽 + maxLi<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌nes=2 + 省略号，让"能显示多少"由布局决定，
        // 而不是先砍成 16 个字（砍完的中文常常只剩半句话，反而更难认）。
        // take(60) 只是防御巨型 payload，不是显示口径。
        val gn = GNodeV(id, xPos[id]!!, depthM[id]!!.toFloat(), node.role,
            node.content.replace('\n', ' ').take(60), isOption, id == leafId, id in path, opts)
        out.add(gn)
        node.childrenIds.forEach { child -> edges.add(gn to build(child)) }
        return gn
    }
    build(root)
    return out to edges
}

/**
 * 二维分支树图：叶子居中布局 + 双指缩放/拖动 + 选项点标/描边 + 点击即回档。
 *
 * 坐标只有一个坐标系：**未缩放的 px**（dp 常量 × density 一次算好）。缩放交给外层
 * `graphicsLayer(transformOrigin = 左上角)`，卡片与连线因此永远同步、永不重叠。
 */
@Composable
fun TreeGraph(vm: ChatViewModel, tree: ChatTree, mech: MechanicsEngine, accent: Color, saveTree: () -> Unit, refreshChain: () -> Unit, restoreOptions: (String?) -> Unit) {
    val (nodes, edges) = remember(tree) { computeTreeLayout(tree, tree.currentLeafId) }
    val density = LocalDensity.current
    // dp → px 只在这里算一次；坐标、卡片、间距此后全是 px，不存在"一半 dp 一半 px"。
    val xSpacingPx = with(density) { X_SPACING_DP.dp.toPx() }
    val ySpacingPx = with(density) { Y_SPACING_DP.dp.toPx() }
    val chipWpx = with(density) { CHIP_W_DP.dp.toPx() }
    val chipHpx = with(density) { CHIP_H_DP.dp.toPx() }
    val optionGapPx = with(density) { OPTION_GAP_DP.dp.toPx() }
    val optionHPx = with(density) { OPTION_H_DP.dp.toPx() }
    val optionBlockPx = with(density) { (OPTION_GAP_DP + OPTIONS_MAX * OPTION_H_DP).dp.toPx() }
    val marginPx = with(density) { 24.dp.toPx() }
    val maxX = nodes.maxOfOrNull { it.x } ?: 0f
    val maxY = nodes.maxOfOrNull { it.y } ?: 0f
    // 世界尺寸也是 px：左边距 + 卡片 + 列数×列距 + 右边距（以前 worldW 用的是 px，
    // 但卡片宽度用的是 dp，居中公式等于把两把尺子混着用）。
    val worldW = marginPx * 2f + chipWpx + maxX * xSpacingPx
    val worldH = marginPx * 2f + chipHpx + optionBlockPx + maxY * ySpacingPx
    // 节点中心（未缩放 px）。连线与卡片都调它，保证"线从卡片中心出发、落在卡片中心"。
    val cxOf: (Float) -> Float = { x -> marginPx + chipWpx / 2f + x * xSpacingPx }
    val cyOf: (Float) -> Float = { y -> marginPx + chipHpx / 2f + y * ySpacingPx }
    var scale by remember { mutableStateOf(0.8f) }
    var panX by remember { mutableStateOf(0f) }
    var panY by remember { mutableStateOf(0f) }
    var viewW by remember { mutableStateOf(1) }
    var viewH by remember { mutableStateOf(1) }
    // 首帧把整棵树铺满并居中：worldW/worldH 已是 px，fitScale 同样是"屏幕像素 / 世界像素"。
    LaunchedEffect(viewW, viewH, worldW, worldH) {
        val fitScale = minOf(viewW / worldW, viewH / worldH).coerceIn(MIN_SCALE, FIT_MAX_SCALE)
        scale = fitScale
        panX = (viewW - worldW * fitScale) / 2f
        panY = (viewH - worldH * fitScale) / 2f
    }
    val ctx = LocalContext.current
    // 分支树原来是一块写死的「灰白 MC 成就风」浅色面板（30 多个 hex），压在深色画布上像贴纸。
    // 改成令牌语义：灰阶层次用 surface/surface_2 + border/border_strong 表达，正文走 text/textSub，
    // 「当前节点」用 accent 描一圈 —— 强调色只留给"当前进度"这一件事。
    val pal = LocalDickPalette.current
    var branchMode by remember { mutableStateOf(false) }
    Column {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { branchMode = false }) { IconText("回档", fontSize = 12.sp, iconSize = 13.dp, fontWeight = if (!branchMode) FontWeight.Bold else null, color = if (!branchMode) accent else Color.Unspecified, icon = "shuffle") }
            TextButton(onClick = { branchMode = true }) { IconText("建分支", fontSize = 12.sp, iconSize = 13.dp, fontWeight = if (branchMode) FontWeight.Bold else null, color = if (branchMode) accent else Color.Unspecified, icon = "edit") }
            Spacer(Modifier.weight(1f))
            Text(if (branchMode) "点节点=从这点继续 · 下一条会分出新分支" else "点节点=跳回那里", fontSize = 10.sp, color = pal.textSub)
        }
        Box(
            Modifier.fillMaxWidth().height(GRAPH_H_DP.dp)
                .clip(RoundedCornerShape(12.dp))
                .background(pal.bg)
                // 节点/连线一律不许画到框外（缩放后最容易越界的就是最外圈的叶子）
                .clipToBounds()
                .onSizeChanged { viewW = it.width; viewH = it.height }
                .pointerInput(Unit) {
                    detectTransformGestures { _, pan, zoom, _ ->
                        scale = (scale * zoom).coerceIn(MIN_SCALE, MAX_SCALE)
                        panX += pan.x; panY += pan.y
                    }
                }
        ) {
            // 唯一被变换的容器：缩放/平移都作用在这一层，
            // 卡片（dp→px 后的绝对位置）和连线（同一套 px）一起缩，所以永远不会互相错位。
            Box(
                Modifier.fillMaxSize().graphicsLayer {
                    scaleX = scale
                    scaleY = scale
                    translationX = panX
                    translationY = panY
                    // 以左上角为原点：缩放与平移才在同一个坐标系里（以中心为原点会让 pan 变成"缩放后的偏移"）
                    transformOrigin = TransformOrigin(0f, 0f)
                }
            ) {
                // Canvas 的 draw lambda 不是 composable，颜色必须先在外面取好
                val edgeOn = pal.borderStrong
                val edgeOff = pal.border
                Canvas(Modifier.fillMaxSize()) {
                    edges.forEach { (a, b) ->
                        val c = if (b.onPath) edgeOn else edgeOff
                        drawLine(c, Offset(cxOf(a.x), cyOf(a.y)), Offset(cxOf(b.x), cyOf(b.y)), strokeWidth = 2f)
                    }
                }
                nodes.forEach { n ->
                    val cx = cxOf(n.x)
                    val cy = cyOf(n.y)
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
                    // 角色签：固定 24dp 方框 + 短签（你/系/AI/▣），**不参与**抢宽度，
                    // 长文案因此不会被图标框挤出卡片（以前 26dp 框 + 单行 16 字，长句直接糊成一条）。
                    val roleTag = when {
                        n.role == "user" -> "你"
                        n.role == "system" -> "系"
                        n.isOption -> "▣"
                        else -> "AI"
                    }
                    val statusText = if (n.isCurrent) "当前进度" else if (n.isOption) "选项节点"
                    else (if (n.onPath) "当前剧情线" else "分支剧情")
                    Box(
                        Modifier
                            .offset { IntOffset((cx - chipWpx / 2f).toInt(), (cy - chipHpx / 2f).toInt()) }
                            .size(CHIP_W_DP.dp, CHIP_H_DP.dp)
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
                        Row(
                            Modifier.padding(horizontal = 6.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Box(
                                Modifier.size(24.dp)
                                    .clip(RoundedCornerShape(5.dp))
                                    .background(pal.surface2)
                                    .border(1.dp, pal.border, RoundedCornerShape(5.dp)),
                                contentAlignment = Alignment.Center,
                            ) { Text(roleTag, fontSize = 9.sp, maxLines = 1, color = tc) }
                            Spacer(Modifier.width(5.dp))
                            // weight(1f)：文字永远拿"剩下的全部宽度"，图标框再宽也挤不掉它
                            Column(Modifier.weight(1f)) {
                                Text(
                                    n.content.ifBlank { "（空）" },
                                    fontSize = 10.sp, lineHeight = 12.sp,
                                    maxLines = 2, overflow = TextOverflow.Ellipsis, color = tc,
                                )
                                Text(
                                    statusText,
                                    fontSize = 8.sp, lineHeight = 9.sp,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis, color = pal.textDim,
                                )
                            }
                        }
                    }
                    // 选项点：把存过的选项作为可点小签显示（点=从该选项新建分支）
                    n.options.take(OPTIONS_MAX).forEachIndexed { i, opt ->
                        val ox = cx - chipWpx / 2f
                        val oy = cy + chipHpx / 2f + optionGapPx + i * optionHPx
                        Box(
                            Modifier
                                .offset { IntOffset(ox.toInt(), oy.toInt()) }
                                .width(CHIP_W_DP.dp).height(OPTION_H_DP.dp)
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
}
