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

// ChatState <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌的扩展函数（前半）
// ChatState 的扩展函数（后半）
internal fun ChatState.engineChain(): List<MessageNode> {
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

internal fun ChatState.currentWorldJson(): String? {
        val n = currentWorld.takeIf { it.isNotBlank() }
            ?: selectedWorlds.firstOrNull() ?: return null
        val o = worldCards[n] ?: return null
        return JsonS.stringify(o)
    }

internal fun ChatState.roleJsonOf(name: String?): String? {
        val n = name?.takeIf { it.isNotBlank() }
            ?: lastSpeaker?.takeIf { selectedRoles.size > 1 && it.isNotBlank() }
            ?: selectedRoles.firstOrNull() ?: return null
        val o = J.Obj()
        o.fields["name"] = J.Str(n)
        advancedByRole[n]?.let { o.fields["advanced"] = it }
        return JsonS.stringify(o)
    }

internal fun ChatState.currentRoleJson(): String? = roleJsonOf(null)

internal fun ChatState.currentSpeaker(): String = lastSpeaker?.takeIf { selectedRoles.size > 1 && it.isNotBlank() }
        ?: selectedRoles.firstOrNull() ?: ""

internal fun ChatState.consumeSpaceMoves(text: String, who: String, note: Boolean = true): String {
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

internal fun ChatState.send() {
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
                    if (res == null) "⚠️ 当前角色未启用好感度（机制卡 → 好感度）"
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
                        sysMsgs.add(ChatMsg("系统", I18n.t("vision_fail", "图片没认出来，稍后再试一次")))
                        refreshChain()
                    } else {
                        doSendCb(text, img.bmp, "【图片描述】" + desc)
                    }
                }
            }
            return
        }
        doSendCb(text, null, null)
    }

internal fun ChatState.pickChoice(item: GalgamePlugin.ChoiceItem) {
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
        // 选项是按钮上的短标签；真正发言用 say（生成时补全好的玩家台词）。
        // 没有 say（旧选项、模型没给）就退回标签 —— 行为与以前一致。
        doSendCb(item.say?.takeIf { it.isNotBlank() } ?: item.text, null, null)
    }

internal fun ChatState.battleMove(moveId: String, moveName: String) {
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
        doSendCb("使用 $moveName", null, null)
    }

internal fun ChatState.landAssistantReply(raw: String, parentId: String?, userText: String) {
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
        val regexed = applyRegex(despaced, "ai", selectedRoles, advancedByRole, persona)
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

internal fun ChatState.fallbackOpening(role: String, firstMes: String) {
        if (!tree.nodes.isEmpty()) return   // 已经有内容了就别补刀
        val meta = J.Obj()
        meta.fields["speaker"] = J.Str(role)
        meta.fields["greeting"] = J.Bool(true)
        tree.addNode("assistant", firstMes, parentId = null, metadata = meta)
        saveTree()
        refreshChain()
    }

internal fun ChatState.regenerate(msg: ChatMsg) {
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

internal fun ChatState.switchSwipe(msg: ChatMsg, delta: Int) {
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

internal fun ChatState.editMessage(msg: ChatMsg, newText: String) {
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

internal fun ChatState.reloadRolesFromDisk() {
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

internal fun ChatState.reloadWorldsFromDisk() {
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

internal fun ChatState.wsLoadOnline() {
        wsSetStatus("加载中...")
        scope.launch(Dispatchers.IO) {
            try {
                val (cards, worldsL) = Workshop.listResources()
                scope.launch(Dispatchers.Main) {
                    wsOnlineList.clear()
                    cards.forEach { it.fields["_type"] = J.Str("角色卡"); wsOnlineList.add(it) }
                    worldsL.forEach { it.fields["_type"] = J.Str("世界卡"); wsOnlineList.add(it) }
                    wsOnlineIdx = -1
                    wsSetStatus("共 " + wsOnlineList.size + " 个作品")
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) { wsSetStatus(e.message ?: "网络错误", "error") }
            }
        }
    }

internal fun ChatState.wsSearchOnline() {
        val q = wsSearchInput.trim()
        wsSetStatus("搜索中...")
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
                    wsSetStatus("找到 " + rs.size + " 个")
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) { wsSetStatus(e.message ?: "网络错误", "error") }
            }
        }
    }

internal fun ChatState.wsOnlineDisplay(r: J.Obj): String {
        val t = r.fields["_type"]?.str() ?: "角色卡"
        val name = r.fields["name"]?.str() ?: "?"
        val author = r.fields["author"]?.str() ?: "?"
        val dl = (r.fields["downloads"] as? J.Num)?.v?.toInt() ?: 0
        val lk = (r.fields["likes"] as? J.Num)?.v?.toInt() ?: 0
        val tags = (r.fields["tags"] as? J.Arr)?.items?.mapNotNull { it.str() }?.joinToString(",") ?: ""
        // 纯文本（图标位已去掉）：类型改成写在串里，别再用 emoji 当类型前缀
        return (if (t == "角色卡") "角色卡 " else "世界卡 ") + name + " | " + author +
            " | ↓" + dl + " 赞" + lk + (if (tags.isBlank()) "" else " | " + tags)
    }

internal fun ChatState.wsLoadPlugins() {
        wsSetStatus("加载中...")
        scope.launch(Dispatchers.IO) {
            try {
                val (plugins, local) = Workshop.listPlugins()
                scope.launch(Dispatchers.Main) {
                    wsPlugins = plugins
                    wsLocalPlugins = local
                    wsSetStatus("共 " + plugins.size + " 个插件")
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) { wsSetStatus(e.message ?: "网络错误", "error") }
            }
        }
    }

internal fun ChatState.wsInstallPlugin(id: String) {
        wsInstallingId = id
        wsSetStatus("安装中...")
        scope.launch(Dispatchers.IO) {
            try {
                val fname = Workshop.installPlugin(id)
                val local = (AppEnv.dir("plugins").listFiles()
                    ?.filter { it.name.endsWith(".py") && !it.name.startsWith("_") }
                    ?.map { it.name.removeSuffix(".py") } ?: emptyList())
                scope.launch(Dispatchers.Main) {
                    wsLocalPlugins = local
                    wsInstallingId = ""
                    wsSetStatus("安装成功：" + fname, "check_circle")
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) {
                    wsInstallingId = ""
                    wsSetStatus(e.message ?: "安装失败", "error")
                }
            }
        }
    }

internal fun ChatState.wsDownloadSelected() {
        val r = wsOnlineList.getOrNull(wsOnlineIdx) ?: return
        val id = r.fields["id"]?.str() ?: return
        val type = r.fields["_type"]?.str() ?: "角色卡"
        val fname = r.fields["original_name"]?.str() ?: ((r.fields["name"]?.str() ?: "card") + ".json")
        wsSetStatus("下载中...")
        scope.launch(Dispatchers.IO) {
            try {
                val f = Workshop.download(id, type, fname)
                scope.launch(Dispatchers.Main) {
                    wsSetStatus("已下载：" + f.name, "check_circle")
                    wsRefresh()
                    reloadRolesFromDisk()
                    reloadWorldsFromDisk()
                }
            } catch (e: Exception) {
                scope.launch(Dispatchers.Main) { wsSetStatus(e.message ?: "下载失败", "error") }
            }
        }
    }

internal fun ChatState.wsLikeSelected() {
        val r = wsOnlineList.getOrNull(wsOnlineIdx) ?: return
        val id = r.fields["id"]?.str() ?: return
        val type = r.fields["_type"]?.str() ?: "角色卡"
        scope.launch(Dispatchers.IO) {
            val ok = try { Workshop.like(id, type) } catch (e: Exception) { false }
            scope.launch(Dispatchers.Main) { wsSetStatus(if (ok) "已点赞" else "点赞失败", if (ok) "check_circle" else "error") }
        }
    }

internal fun ChatState.wsDeleteSelected() {
        val r = wsOnlineList.getOrNull(wsOnlineIdx) ?: return
        val id = r.fields["id"]?.str() ?: return
        val type = r.fields["_type"]?.str() ?: "角色卡"
        scope.launch(Dispatchers.IO) {
            val ok = try { Workshop.deleteRemote(id, type) } catch (e: Exception) { false }
            scope.launch(Dispatchers.Main) {
                wsSetStatus(if (ok) "已删除" else "删除失败", if (ok) "check_circle" else "error")
                if (ok) wsLoadOnline()
            }
        }
    }

internal fun ChatState.wsUploadLocal() {
        if (wsLocalIdx < 0) return
        val fname = if (wsLocalType == "角色卡") wsLocalRoles.getOrNull(wsLocalIdx) ?: return
            else wsLocalWorlds.getOrNull(wsLocalIdx) ?: return
        val name = fname.removeSuffix(".json")
        wsSetStatus("上传中...")
        scope.launch(Dispatchers.IO) {
            // uploadEx 会把原因带回来（本地文件不存在 / 401 要 Key / 404 线上是旧版 / HTTP 码+响应）
            val why = try { Workshop.uploadEx(wsLocalType, name) } catch (e: Exception) {
                "异常：" + (e.message ?: e.javaClass.simpleName).take(80)
            }
            scope.launch(Dispatchers.Main) {
                wsSetStatus(if (why == null) "上传成功" else "上传失败：" + why, if (why == null) "check_circle" else "error")
                if (why == null) wsLoadOnline()
            }
        }
    }

internal fun ChatState.share() {
        val text = messages.joinToString(10.toChar().toString() + 10.toChar().toString()) { m -> m.role + "：" + m.content }
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
        }
        context.startActivity(Intent.createChooser(intent, "分享聊天记录"))
    }

internal fun ChatState.toggleRoleUnlock(name: String) {
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

internal fun ChatState.deleteRole(name: String) {
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

internal fun ChatState.deleteWorld(name: String) {
        worlds.removeAll { it.first == name }
        selectedWorlds = selectedWorlds - name
        try {
            File(AppEnv.worldsDir(), name + ".json").delete()
        } catch (_: Exception) {
        }
    }

internal fun ChatState.clearHistory(alsoClearMemory: Boolean) {
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
            if (!busy) ensureOpening()
        } catch (_: Exception) {
        }
        if (alsoClearMemory) {
            try { memory.clear() } catch (_: Exception) {}
        }
    }

internal fun ChatState.currentCardLabel(): String {
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
