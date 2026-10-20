package com.dick.app

import android.util.Base64
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.AppEnv
import com.dick.core.J
import com.dick.core.Workshop
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * 角色卡详情（工坊「本地」点一张卡 → 独立详情弹窗）。用户原话：「给创意工坊加一个详细功能吧，
 * 点角色卡会有详细的东西。」旧版是嵌在工坊弹窗里的小预览（空间小、正文还要点"展开"）；
 * 这一版只做三件不同的事：① **不折叠**（CardFields 每个分区整段铺开，单段上限走 MAX_TEXT_CHARS）；
 * ② **补三块数据**（世界书 / 机制 / 文件信息）；③ 抬头头像 + 作者·版本·类型 + 标签，
 * 底部就是工坊那一组动作（不新增后端接口）。
 *
 * 硬边界（`tests/test_card_detail_android.py` 盯着）：字段清单 / 分区顺序 / 标签**只认 [CardFields]**
 * （生成物，唯一真相 `design/card_fields.json`）—— 本文件没有分区 id 字面量，也没有第二张字段表；
 * 三块补充数据按**数据结构**通用渲染（对象→键值行、数组→逐条行，键名就是数据里的键名，不翻译）；
 * 弹窗只走 [DickDialog]，颜色只走令牌（一处 `Color(0x…)` 都没有），界面上不出现 JSON 原文；
 * 状态只从 [ChatViewModel] 读（打开的是哪一张卡 = `wsDetail`），不跨屏直接调用。
 */

/** 「打开的详情」的唯一形状（`ChatViewModel.wsDetail`）：哪一类卡 + 文件名 + 原文（`Workshop.preview`）。 */
data class WsCardDetail(val type: String, val fileName: String, val raw: String)

/** 世界书最多渲染多少条（再多没人翻，而且会把弹窗拖慢）；超出的只报「还有 N 条」。 */
private const val CD_WORLD_CAP = 200

private val CD_MTIME: DateTimeFormatter = DateTimeFormatter.ofPattern("MM-dd HH:mm")

/** 已经单独渲染成「三块补充数据」的顶层键：「其它信息」里不再列一遍（`advanced` 是下钻过的，标签形如 advanced.mechanics）。 */
private val CD_EXTRA_ROWS = listOf("world_entries", "entries", "advanced")

/** 世界书有两种落法（不同来源的卡存得不一样），取第一个非空的：顶层 `world_entries`（DICK 卡）→
 *  顶层 `entries`（世界卡自己）；都没有就当这张卡没带世界书。 */
private fun cdWorldEntries(r: J.Obj?): List<J> {
    val a = r?.fields?.get("world_entries") as? J.Arr
    val b = r?.fields?.get("entries") as? J.Arr
    return (a ?: b)?.items.orEmpty()
}

// ---------- 文件信息（不是卡里的字段，是本机文件的事实） ----------
/** 文件大小：B / KB / MB（一位小数）。 */
private fun cdSize(bytes: Long): String = when {
    bytes < 1024 -> bytes.toString() + " B"
    bytes < 1024 * 1024 -> "%.1f KB".format(bytes / 1024.0)
    else -> "%.1f MB".format(bytes / 1024.0 / 1024.0)
}

/** 文件名之外那半行：大小 · 修改时间。文件读不到就按拿到的原文长度兜底（宁可少一行，不许崩）。 */
private fun cdFileNote(d: WsCardDetail): String {
    val f = try {
        File(if (d.type == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir(), File(d.fileName).name)
    } catch (e: Exception) {
        null
    }
    val (bytes, stamp) = if (f != null && f.isFile) {
        f.length() to (if (f.lastModified() > 0) {
            CD_MTIME.format(Instant.ofEpochMilli(f.lastModified()).atZone(ZoneId.systemDefault()))
        } else "")
    } else {
        d.raw.toByteArray(Charsets.UTF_8).size.toLong() to ""
    }
    return listOf(cdSize(bytes), stamp).filter { it.isNotBlank() }.joinToString(" · ")
}

// ---------- 头像（卡里有 avatar 就用卡里的，没有就退回身份色首字） ----------
/** 卡里那个 `avatar` 值 → 位图：支持 `data:` 内嵌 / http(s) 地址 / 本地路径（绝对或相对 saves/）。
 *  读不到（没网、路径没了、不是图）就返回 null —— 界面退回"身份色首字"，绝不因为头像把详情顶掉。 */
private fun cdLoadAvatar(src: String): ImageBitmap? {
    val s = src.trim()
    if (s.isEmpty()) return null
    return try {
        when {
            s.startsWith("data:") ->
                decodeSampled(Base64.decode(s.substringAfter(','), Base64.DEFAULT), 256)?.asImageBitmap()
            // 头像不是本地资产时才走网络：4 秒超时，超了就当没有（详情页不许卡在头像上）
            s.startsWith("http://") || s.startsWith("https://") ->
                (URL(s).openConnection() as HttpURLConnection)
                    .apply { connectTimeout = 4000; readTimeout = 4000 }
                    .inputStream.use { decodeSampled(it.readBytes(), 256)?.asImageBitmap() }
            else -> {
                val direct = File(s)
                val hit = if (direct.isFile) direct else File(AppEnv.savesDir(), s)
                if (hit.isFile) decodeSampledFile(hit.absolutePath, 256)?.asImageBitmap() else null
            }
        }
    } catch (e: Exception) {
        null
    }
}

/** 52dp 圆头像：卡内 avatar → 角色自己的头像文件 → 身份色首字（[speakerColor] 不随主题变，墨走 on_identity）。 */
@Composable
private fun CdAvatar(name: String, avatar: String) {
    val pal = LocalDickPalette.current
    var bmp by remember(name, avatar) { mutableStateOf<ImageBitmap?>(null) }
    LaunchedEffect(name, avatar) {
        bmp = withContext(Dispatchers.IO) {
            (if (avatar.isBlank()) null else cdLoadAvatar(avatar)) ?: loadCustomAvatar(name)
        }
    }
    val img = bmp
    if (img != null) {
        Image(img, contentDescription = null, modifier = Modifier.size(52.dp).clip(CircleShape))
        return
    }
    Box(
        Modifier.size(52.dp).clip(CircleShape).background(speakerColor(name)),
        contentAlignment = Alignment.Center,
    ) {
        Text(name.ifBlank { "A" }.first().toString(), color = pal.onIdentity,
            fontSize = 20.sp, fontWeight = FontWeight.Bold)
    }
}

/** 标签：数组逐项、或逗号 / 空格分隔的字符串，统一加 `#`（`#` 只是界面记号，卡里存的是数据）。 */
private fun cdTags(v: J?): String {
    val items = when (v) {
        is J.Arr -> v.items.mapNotNull { it.str() }
        is J.Str -> v.v.split(",", "，", "|", " ")
        else -> emptyList()
    }
    return items.map { it.trim() }.filter { it.isNotEmpty() }.take(12).joinToString(" ") { "#$it" }
}

/** 抬头：头像 + 名字 + 「作者 xx · v版本 · 类型」+ 标签。作者 / 版本的标签走 CardFields（不硬编码文案）。 */
@Composable
private fun CdHeader(d: WsCardDetail, root: J.Obj?) {
    val pal = LocalDickPalette.current
    val name = cfScalar(root?.fields?.get("name"))?.takeIf { it.isNotBlank() }
        ?: d.fileName.removeSuffix(".json")
    val author = cfScalar(root?.fields?.get("author"))?.takeIf { it.isNotBlank() }
    val version = cfScalar(root?.fields?.get("version"))?.takeIf { it.isNotBlank() }
    val tags = cdTags(root?.fields?.get("tags"))
    Row(Modifier.fillMaxWidth()) {
        CdAvatar(name, cfScalar(root?.fields?.get("avatar")) ?: "")
        Column(Modifier.padding(start = 10.dp)) {
            Text(name, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = pal.text, maxLines = 2)
            val line = buildList {
                if (author != null) add(CardFields.fieldLabel("author") + " " + author)
                if (version != null) add("v" + version)
                add(d.type)
            }.joinToString(" · ")
            Text(line, fontSize = 11.sp, color = pal.textSub, modifier = Modifier.padding(top = 2.dp))
            if (tags.isNotBlank()) {
                Text(tags, fontSize = 11.sp, color = pal.accent, modifier = Modifier.padding(top = 2.dp))
            }
        }
    }
}

// ---------- 排版零件 ----------
/** 两列「键: 值」（键窄、值宽，都按令牌取色）—— 分区与三块补充数据共用这一个排版。 */
@Composable
private fun CdKeyValues(rows: List<Pair<String, String>>) {
    val pal = LocalDickPalette.current
    Column {
        rows.forEach { (k, v) ->
            Row(Modifier.padding(vertical = 1.dp)) {
                if (k.isNotBlank()) {
                    Text(k, fontSize = 11.sp, color = pal.textSub, modifier = Modifier.weight(0.34f))
                }
                Text(v, fontSize = 11.sp, color = pal.text,
                    modifier = Modifier.weight(if (k.isBlank()) 1f else 0.66f))
            }
        }
    }
}

/** 正文块：**不折叠**，只按 [CardFields.MAX_TEXT_CHARS] 截断（一份 130KB 的卡不能把弹窗拖死）。 */
@Composable
private fun CdBody(blk: CardBodyBlock) {
    val pal = LocalDickPalette.current
    if (blk.label.isNotBlank()) {
        Text(blk.label, fontSize = 11.sp, color = pal.textSub, modifier = Modifier.padding(top = 4.dp))
    }
    var left = CardFields.MAX_TEXT_CHARS
    for (p in blk.paras) {
        if (left <= 0) break
        val shown = if (p.length > left) p.take(left) + "…" else p
        left -= p.length
        Text(shown, fontSize = 12.sp, color = pal.text, modifier = Modifier.padding(bottom = 4.dp))
    }
}

/** 列表块（rules[] 这类）：逐条一行。 */
@Composable
private fun CdList(blk: CardListBlock) {
    val pal = LocalDickPalette.current
    if (blk.label.isNotBlank()) {
        Text(blk.label, fontSize = 11.sp, color = pal.textSub, modifier = Modifier.padding(top = 4.dp))
    }
    blk.items.forEach { item ->
        Text("· " + item, fontSize = 12.sp, color = pal.text, modifier = Modifier.padding(bottom = 2.dp))
    }
}

/** CardFields 的每个分区整段铺开（**详情页不折叠**，这正是与列表预览的区别）；mode 只有 body/kv/list 三档。 */
@Composable
private fun CdSections(model: CardModel) {
    val pal = LocalDickPalette.current
    model.sections.forEach { sec ->
        val label = CardFields.sectionLabel(sec.id)      // 分区标题只认生成物
        if (label.isNotBlank()) {
            Text(label, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = pal.textSub,
                modifier = Modifier.padding(top = 10.dp))
        }
        when (sec.mode) {
            MODE_KV -> CdKeyValues(sec.rows)
            MODE_LIST -> sec.blocks.forEach { blk -> if (blk is CardListBlock) CdList(blk) }
            else -> sec.blocks.forEach { blk -> if (blk is CardBodyBlock) CdBody(blk) }
        }
    }
    val other = model.other.filter { (k, _) -> !CD_EXTRA_ROWS.any { x -> k == x || k.startsWith("$x.") } }
    if (other.isNotEmpty()) {
        Text(CardFields.sectionLabel(CardFields.OTHER.id), fontSize = 12.sp,
            fontWeight = FontWeight.SemiBold, color = pal.textSub, modifier = Modifier.padding(top = 10.dp))
        CdKeyValues(other)
    }
}

// ---------- 三块补充数据：通用结构渲染（对象 → 键值行、数组 → 逐条行） ----------
/** 一个结构化节点的通用排版。键名直接用数据里的键名（不翻译），所以这里没有第二张标签表。
 *  `depth` 只往下展开一层：再深的嵌套一律报「对象 · N 项」，否则世界书里那层 dict 会把弹窗撑成一片。 */
@Composable
private fun CdTree(v: J?, depth: Int) {
    val pal = LocalDickPalette.current
    when (v) {
        null, is J.Null -> Unit
        is J.Obj -> v.fields.forEach { (k, sub) ->
            if ((sub is J.Obj || sub is J.Arr) && depth < 1) {
                Text(k, fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = pal.textSub,
                    modifier = Modifier.padding(top = 4.dp))
                CdTree(sub, depth + 1)
            } else {
                CdKeyValues(listOf(k to cfValueText(sub, CardFields.KV_VALUE_CHARS)))
            }
        }
        is J.Arr -> v.items.forEachIndexed { i, item ->
            if ((item is J.Obj || item is J.Arr) && depth < 1) {
                Text("#" + (i + 1), fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                    color = pal.textSub, modifier = Modifier.padding(top = 4.dp))
                CdTree(item, depth + 1)
            } else {
                CdKeyValues(listOf("#" + (i + 1) to cfValueText(item, CardFields.KV_VALUE_CHARS)))
            }
        }
        else -> CdKeyValues(listOf("" to cfValueText(v, 0)))
    }
}

/** 一条记录的一行摘要：对象取它第一个非空标量字段，数组 / 标量原样压行。 */
private fun cdHeadLine(v: J?): String {
    if (v is J.Obj) {
        for ((_k, sub) in v.fields) {
            val s = cfScalar(sub)
            if (!s.isNullOrBlank()) return cfOneLine(s, 60)
        }
        return cfSummary(v)
    }
    if (v is J.Arr) return cfSummary(v)
    return cfOneLine(cfScalar(v) ?: "", 60)
}

/** 世界书：默认**收起**，点标题展开；超过 [CD_WORLD_CAP] 条只渲染前 200 + 「还有 N 条」；展开后每条一行摘要，点某条才铺开。 */
@Composable
private fun CdWorldBook(entries: List<J>) {
    val pal = LocalDickPalette.current
    var open by remember(entries) { mutableStateOf(false) }
    var openIdx by remember(entries) { mutableStateOf(-1) }
    FoldHead("世界书 · " + entries.size + " 条", folded = !open, onToggle = { open = !open }, icon = "menu_book")
    if (!open) return
    entries.take(CD_WORLD_CAP).forEachIndexed { i, e ->
        val alone = openIdx == i
        Row(
            Modifier.fillMaxWidth().clickable { openIdx = if (alone) -1 else i }.padding(vertical = 2.dp),
        ) {
            Text((i + 1).toString() + ".", fontSize = 11.sp, color = pal.textDim, modifier = Modifier.width(26.dp))
            Text(cdHeadLine(e), fontSize = 11.sp, color = pal.textSub,
                maxLines = if (alone) 4 else 1, modifier = Modifier.weight(1f))
        }
        if (alone) CdTree(e, 0)
    }
    if (entries.size > CD_WORLD_CAP) {
        Text("还有 " + (entries.size - CD_WORLD_CAP) + " 条", fontSize = 11.sp, color = pal.textDim,
            modifier = Modifier.padding(top = 2.dp))
    }
}

/** 机制（`advanced.mechanics`）：默认收起；展开后按结构铺开（好感 / 状态都是数据里的键，不是界面标签）。 */
@Composable
private fun CdMechanics(mech: J.Obj) {
    var open by remember(mech) { mutableStateOf(false) }
    FoldHead("机制 · " + mech.fields.size + " 项", folded = !open, onToggle = { open = !open }, icon = "tune")
    if (open) CdTree(mech, 0)
}

/** 文件信息：文件名 + 大小 · 修改时间（不是卡里的字段，是本机文件的事实）。 */
@Composable
private fun CdFileInfo(d: WsCardDetail) {
    val note = remember(d.type, d.fileName) { cdFileNote(d) }
    Text("文件", fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
        color = LocalDickPalette.current.textSub, modifier = Modifier.padding(top = 10.dp))
    CdKeyValues(listOf(d.fileName to note))
}

// ---------- 弹窗 ----------
/**
 * 卡片详情弹窗。底部四个动作**就是工坊那一组**（[WorkshopActions] 的导入 / 导出 / 删除 / 上传），
 * 不新增后端接口；关掉只会把 `wsDetail` 置空，工坊列表还在底下（选中高亮不变）。
 */
@Composable
fun CardDetailDialog(d: WsCardDetail, vm: ChatViewModel, acts: WorkshopActions) {
    val pal = LocalDickPalette.current
    // 解析两遍（模型 + 根对象）：一张卡最大百来 KB，开弹窗时各一次，不值得再搭一层缓存
    val model = remember(d.fileName, d.raw) { cfParse(d.raw, d.fileName) }
    val root = remember(d.fileName, d.raw) { cfRoot(d.raw) }
    val world = remember(root) { cdWorldEntries(root) }
    val mech = remember(root) {
        (root?.fields?.get("advanced") as? J.Obj)?.fields?.get("mechanics") as? J.Obj
    }
    val close = { vm.wsDetail.value = null }
    DickDialog(
        onDismissRequest = close,
        title = { IconText("卡片详情", icon = "description") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                CdHeader(d, root)
                CdSections(model)
                if (world.isNotEmpty()) CdWorldBook(world)
                if (mech != null) CdMechanics(mech)
                CdFileInfo(d)
            }
        },
        confirmButton = {
            Row {
                DickTextButton(I18n.t("btn_import_card", "导入"), onClick = {
                    acts.importCardLauncher.launch(arrayOf("image/png", "image/webp", "application/json"))
                }, fontSize = 12.sp, icon = "inbox")
                DickTextButton(I18n.t("ws_export", "导出"), onClick = {
                    vm.wsExportTarget.value = d.fileName
                    acts.wsExportLauncher.launch(d.fileName)
                }, fontSize = 12.sp, icon = "upload")
                DickTextButton(I18n.t("ws_delete", "删除"), onClick = {
                    if (Workshop.deleteLocal(d.type, d.fileName)) {
                        close()
                        vm.wsLocalIdx.value = -1
                        acts.refreshLocal()
                        acts.reloadRolesFromDisk()
                        acts.reloadWorldsFromDisk()
                        vm.wsStatus.value = "已删除"
                        vm.wsStatusIcon.value = "check_circle"
                    }
                }, fontSize = 12.sp, color = pal.danger, icon = "delete")
                DickTextButton(I18n.t("ws_upload", "上传"), onClick = { acts.uploadLocal() },
                    fontSize = 12.sp, icon = "upload")
            }
        },
        dismissButton = { DickTextButton(I18n.t("btn_cancel", "取消"), onClick = close) },
    )
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌
