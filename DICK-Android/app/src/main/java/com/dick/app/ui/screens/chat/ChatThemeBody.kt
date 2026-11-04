package com.dick.app

// 从 ChatScreen 抽出的主界面<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（状态与逻辑都在 ChatState）

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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
internal fun ChatThemeBody(
    st: ChatState,
    theme: ThemeSpec,
    accent: Color,
    drawerState: androidx.compose.material3.DrawerState,
    onOpenDrawer: () -> Unit,
    showApiSetup: androidx.compose.runtime.MutableState<Boolean>,
    showTrpg: androidx.compose.runtime.MutableState<Boolean>,
    showCardFace: androidx.compose.runtime.MutableState<Boolean>,
    deps: DialogDeps,
    imagePicker: androidx.activity.result.ActivityResultLauncher<String>,
    insertCmd: (String) -> Unit,
) {
DickTheme(mode = theme.mode, accentIdx = st.accentIdx) {
    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    st.appIcon?.let {
                        Image(bitmap = it, contentDescription = null,
                            modifier = Modifier.size(24.dp).clip(RoundedCornerShape(6.dp)))
                        Spacer(Modifier.width(8.dp))
                    }
                    Text("DICK", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
                Text(I18n.t("group_other", "其它项目"), Modifier.padding(horizontal = 16.dp, vertical = 4.dp), color = theme.muted, fontSize = 13.sp)
                DrawerItem(I18n.t("item_settings", "设置")) { st.showSettings = true; st.scope.launch { drawerState.close() } }
                DrawerItem(I18n.t("item_api", "API 配置"), icon = "key") { showApiSetup.value = true; st.scope.launch { drawerState.close() } }
                DrawerItem("跑团（局域网）", icon = "theater_comedy") { showTrpg.value = true; st.scope.launch { drawerState.close() } }
                DrawerItem(I18n.t("item_share", "分享聊天记录")) { st.share(); st.scope.launch { drawerState.close() } }
                DrawerItem("彻底清空历史", color = theme.danger, icon = "delete") { st.showClearHistory = true; st.scope.launch { drawerState.close() } }
                DrawerItem(I18n.t("btn_workshop", "创意工坊"), icon = "home_repair_service") { st.showWorkshop = true; st.scope.launch { drawerState.close() } }
            }
        },
    ) {
        Column(
            Modifier.fillMaxSize()
                .drawBehind {
                    val wp = st.wallpaper
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
                TextButton(onClick = { st.scope.launch { drawerState.open() } }) { IconText("", fontSize = 20.sp, iconSize = 20.dp, icon = "menu") }
                Spacer(Modifier.width(6.dp))
                Text(PRESETS[st.presetIdx].name, Modifier.padding(top = 10.dp), color = theme.muted)
                Spacer(Modifier.weight(1f))
                FolderMenu(st.vm, deps)
                TextButton(onClick = { showCardFace.value = true }) { IconText("", fontSize = 16.sp, icon = "style") }
                TextButton(onClick = { st.showBranches = true }) { IconText(I18n.t("btn_branch", "回档"), fontSize = 13.sp, icon = "account_tree") }
            }
            Spacer(Modifier.height(6.dp))
            // 机制卡三栏（好感度栏 / 人物状态栏 / 战斗数值栏）
            st.mechTick
            val mechCfg = st.mech.config
            val mechSt = st.mech.state
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
                            IconText("好感", fontSize = 11.sp, color = theme.muted, iconSize = 12.dp, icon = "favorite")
                            Box(Modifier.weight(1f).height(5.dp).clip(RoundedCornerShape(3.dp)).background(theme.bubble)) {
                                Box(
                                    Modifier
                                        .fillMaxWidth((((cur - lo).toFloat()) / (hi - lo).coerceAtLeast(1)).coerceIn(0f, 1f))
                                        .height(5.dp).clip(RoundedCornerShape(3.dp)).background(accent),
                                )
                            }
                            Text("$cur/$hi", fontSize = 11.sp, color = theme.muted)
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
                                IconText("$name：$curI", fontSize = 11.sp, color = theme.muted, iconSize = 12.dp, icon = "swords")
                            } else {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    IconText("$name", fontSize = 11.sp, color = theme.muted, iconSize = 12.dp, icon = "swords")
                                    Box(Modifier.weight(1f).height(5.dp).clip(RoundedCornerShape(3.dp)).background(theme.bubble)) {
                                        Box(
                                            Modifier
                                                .fillMaxWidth((((curI - mn).toFloat()) / (mx - mn).coerceAtLeast(1)).coerceIn(0f, 1f))
                                                .height(5.dp).clip(RoundedCornerShape(3.dp)).background(theme.danger),
                                        )
                                    }
                                    Text("$curI/$mx", fontSize = 11.sp, color = theme.muted)
                                }
                            }
                        } else {
                            Text("$name：${v.str() ?: v.int()}", fontSize = 11.sp, color = theme.muted)
                        }
                    }
                    // ④ 事件进度：玩家看不到进度就会觉得事件坏了。
                    // 数据由 MechanicsEngine.eventProgress() 提供（纯读，不改状态）。
                    // 不用额外的 state —— 上面已经读了 st.mechTick，重组时这里会重算。
                    val evItems = st.mech.eventProgress()
                    if (evItems.isNotEmpty()) {
                        IconText(
                            "事件 " + evItems.count { it["fired"] == true } + "/" + evItems.size,
                            fontSize = 11.sp, color = theme.muted, iconSize = 12.dp, icon = "movie"
                        )
                        evItems.forEach { e ->
                            val stt = e["state"] as? String ?: ""
                            val nm = e["name"] as? String ?: (e["id"] as? String ?: "")
                            val why = e["why"] as? String ?: ""
                            // 图标名（不是 emoji）：画成 Material 图标，见下面 IconText 的 icon
                            val mark = when (stt) {
                                "fired" -> "check_circle"
                                "cooling" -> "hourglass_empty"
                                "blocked" -> "lock"
                                else -> "play_arrow"
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
                                IconText(nm, fontSize = 11.sp,
                                     color = theme.text.copy(alpha = if (stt == "blocked" || stt == "cooling") 0.45f else 0.6f),
                                     iconSize = 12.dp, modifier = Modifier.weight(1f), icon = mark)
                                Text(shown, fontSize = 11.sp,
                                     color = theme.text.copy(alpha = if (stt == "blocked" || stt == "cooling") 0.45f else 0.6f))
                            }
                        }
                    }
                }
            }
            // 战斗面板（属性 / 招式按钮 / buff）
            val bCfg = st.mech.battleConfig()
            val bUi = st.mech.battleUiState()
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
                        IconText("玩家 $plHp HP", fontSize = 11.sp, color = theme.muted, iconSize = 12.dp, icon = "person")
                    }
                    // ① 生命/灵力等 → 进度条（hp 红 / 其他蓝）
                    bars.forEach { ao ->
                        val key = ao.fields["key"]?.str() ?: return@forEach
                        val label = ao.fields["label"]?.str() ?: key
                        val value = ao.fields["value"]?.int() ?: 0
                        val mx = ao.fields["max"]?.int() ?: 1
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            IconText("$label", fontSize = 11.sp, color = theme.muted, iconSize = 12.dp, icon = "swords")
                            Box(Modifier.weight(1f).height(5.dp).clip(RoundedCornerShape(3.dp)).background(theme.bubble)) {
                                Box(
                                    Modifier.fillMaxWidth((value.toFloat() / mx).coerceIn(0f, 1f)).height(5.dp)
                                        .clip(RoundedCornerShape(3.dp))
                                        .background(if (key == "hp") theme.danger else accent),
                                )
                            }
                            Text("$value/$mx", fontSize = 11.sp, color = theme.muted)
                        }
                    }
                    // ② 无上限属性 → 数值（合并一行）
                    if (nums.isNotEmpty()) {
                        IconText(
                            nums.mapNotNull { a ->
                                val key = a.fields["key"]?.str() ?: return@mapNotNull null
                                val label = a.fields["label"]?.str() ?: key
                                val value = a.fields["value"]?.int() ?: 0
                                "$label:$value"
                            }.joinToString(" · "),
                            fontSize = 11.sp, color = theme.muted, iconSize = 12.dp, icon = "swords"
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
                                    onClick = { st.battleMove(id, name) },
                                    modifier = Modifier.border(1.dp, accent, RoundedCornerShape(14.dp)),
                                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
                                ) {
                                    IconText("$name", fontSize = 12.sp, color = theme.text, iconSize = 13.dp, maxLines = 1, icon = "swords")
                                }
                            }
                        }
                    }
                    // ④ buff 徽章
                    val buffs = (st.mech.state?.fields?.get("buffs") as? J.Arr)
                    if (buffs?.items?.isNotEmpty() == true) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            buffs.items.forEach { bf ->
                                val bo = bf as? J.Obj ?: return@forEach
                                val bid = bo.fields["id"]?.str() ?: ""
                                val turns = bo.fields["turns"]?.int() ?: 0
                                IconText("$bid ×$turns", fontSize = 10.sp, color = theme.palette.accent, iconSize = 11.dp, icon = "auto_awesome")
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
            // 加载气泡：普通流式回复靠 st.streaming 非空；开局时流式文本还是空的，
            // 靠 st.openingLoading 单独撑住，否则开局那段等待期界面一片空白。
            fun showLoadingBubble(): Boolean =
                st.busy && (st.streaming.isNotEmpty() || st.openingLoading)
            fun chatItemCount(): Int =
                st.messages.size + (if (showLoadingBubble()) 1 else 0)
            // 在底部时新消息自动吸底；滚上去则不打扰
            LaunchedEffect(st.messages.size, st.busy, st.streaming, st.openingLoading) {
                if (!showJump && chatItemCount() > 0) {
                    listState.scrollToItem(chatItemCount() - 1)
                }
            }
            Box(Modifier.weight(1f).fillMaxWidth()) {
                LazyColumn(Modifier.fillMaxSize(), state = listState) {
                    items(st.messages) { m ->
                        Bubble(
                            m, theme.bubble, theme.text, accent, st.avatarCache,
                            onEdit = { st.editMsgTarget = it; st.editMsgText = it.content },
                            onRegen = { st.regenerate(it) },
                            onSwipe = { msg, delta -> st.switchSwipe(msg, delta) },
                        )
                    }
                    if (showLoadingBubble()) {
                        item {
                            // 开场还没吐字时显示「…」（角色像在酝酿第一句），
                            // 一旦有流式文本就换成实时内容
                            val shown = if (st.streaming.isEmpty()) "…" else st.streaming + "…"
                            Bubble(
                                ChatMsg(if (st.selectedRoles.size == 1) st.selectedRoles.first() else "AI", shown),
                                theme.bubble, theme.text, accent, st.avatarCache,
                                onEdit = {}, onRegen = {}, onSwipe = { _, _ -> },
                            )
                        }
                    }
                }
                if (showJump) {
                    Surface(
                        onClick = {
                            st.scope.launch { listState.animateScrollToItem(maxOf(0, chatItemCount() - 1)) }
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
                            MsIcon("download", 20.sp, accent, contentDescription = "到底部")
                        }
                    }
                }
            }
            if (st.pendingImage != null) {
                Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                    Image(st.pendingImage!!.bmp, contentDescription = null, modifier = Modifier.width(64.dp).height(64.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(I18n.t("img_selected", "已选图片"), Modifier.padding(top = 22.dp), fontSize = 12.sp, color = theme.muted)
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = { st.pendingImage = null }) { IconText(I18n.t("btn_remove", "移除"), fontSize = 12.sp, iconSize = 13.dp, icon = "close") }
                }
            }
            ChatQuickPanel(
                visible = st.showQuickPanel, theme = theme, accent = accent,
                finFolded = st.finFolded, onToggleFin = { st.finFolded = !st.finFolded },
                financialEnabled = st.financial.enabled,
                cardQuickReplies = (st.selectedRoles.firstOrNull()?.let { st.advancedByRole[it] }
                    ?.fields?.get("card_quick_replies") as? J.Arr)?.items?.mapNotNull { q ->
                    val qo = q as? J.Obj ?: return@mapNotNull null
                    val l = qo.fields["label"]?.str() ?: return@mapNotNull null
                    l to (qo.fields["text"]?.str() ?: "")
                } ?: emptyList(),
                quickReplies = st.quickReplies,
                onImage = { st.showQuickPanel = false; imagePicker.launch("image/*") },
                onManualGal = { st.showQuickPanel = false; st.gal.manualGenerate() },
                insertCmd = insertCmd,
                onPick = { t -> st.showQuickPanel = false; st.input = t },
            )
            // Galgame 选项行（选择肢按钮）
            if (st.gal.enabled && (st.gal.choices.isNotEmpty() || st.gal.loading)) {
                Column(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                    if (st.gal.loading) {
                        IconText("正在生成选项…", fontSize = 12.sp, color = theme.muted, iconSize = 13.dp, modifier = Modifier.padding(start = 4.dp), icon = "hourglass_empty")
                    }
                    st.gal.choices.chunked(2).forEach { rowItems ->
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(vertical = 1.dp)) {
                            rowItems.forEach { c ->
                                TextButton(
                                    onClick = { st.pickChoice(c) },
                                    modifier = Modifier
                                        .weight(1f)
                                        .border(1.dp, accent, RoundedCornerShape(16.dp)),
                                ) {
                                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                        Text(c.text, fontSize = 13.sp, color = theme.text, maxLines = 2)
                                        val eff = buildString {
                                            c.result?.let { append(it) }
                                            c.aff?.let { if (isNotEmpty()) append(" · "); append("好感").append(if (it > 0) "+" else "").append(it).append("%") }
                                            c.st?.forEach { (k, v) ->
                                                if (isNotEmpty()) append(" · ")
                                                append(k).append(":").append(v)
                                            }
                                        }
                                        if (eff.isNotEmpty()) {
                                            IconText(eff, fontSize = 10.sp, color = theme.muted, iconSize = 11.dp, maxLines = 1)
                                        }
                                    }
                                }
                            }
                        }
                    }
                    if (st.gal.choices.isNotEmpty()) {
                        TextButton(onClick = { st.gal.manualGenerate() }, modifier = Modifier.align(Alignment.End)) {
                            IconText("重新生成", fontSize = 12.sp, icon = "refresh")
                        }
                    }
                }
            }
            Spacer(Modifier.height(6.dp))
            // 输入栏上方的一行状态：忙/生成中。贴着输入框，不进对话（与桌面同一套语义）。
            BusyStatusLine(busy = st.busy, theme = theme, accent = accent)
            ChatComposer(
                input = st.input,
                onInput = { st.input = it },
                busy = st.busy,
                showQuickPanel = st.showQuickPanel,
                onToggleQuick = { st.showQuickPanel = !st.showQuickPanel },
                onSend = { st.send() },
            )
        }
    }
}
}
