package com.dick.app

// ChatState 的扩展函数（从 ChatScree<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌n 搬来的逻辑，状态仍是 ChatState 的成员）
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


internal fun ChatState.wsSetStatus(text: String, icon: String? = null) {
        wsStatus = text
        wsStatusIcon = icon
    }

internal fun ChatState.clearWallpaper() {
        wallpaper = null
        try { File(AppEnv.dataRoot, "wallpaper.png").delete() } catch (_: Exception) {}
    }

internal fun ChatState.treeFileFor(): File = treeFileForRole(if (selectedRoles.size == 1) selectedRoles.first()
            else if (selectedRoles.size > 1) "group" else "default")

internal fun ChatState.stateFileFor(): File = stateFileForRole(if (selectedRoles.size == 1) selectedRoles.first()
            else if (selectedRoles.size > 1) "group" else "default")

internal fun ChatState.personaFields(): Map<String, String> {
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

internal fun ChatState.personaDisplayName(): String {
        val f = personaFields()
        val n = f["name"]?.trim()
        return if (!n.isNullOrBlank()) n else if (persona.isBlank()) "" else "玩家"
    }

internal fun ChatState.userDisplayName(): String = personaFields()["name"]?.trim()?.takeIf { it.isNotBlank() } ?: "你"


internal fun ChatState.personaPrompt(): String {
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

internal fun ChatState.saveTree() {
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
                val cardId = syncCardId(selectedRoles)
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

internal fun ChatState.persistMechAsync() {
        val pending = try { mech.pendingStateWrite() } catch (_: Exception) { null } ?: return
        Lanes.on(Lanes.io, "机制状态落盘") {
            try { mech.flushState(pending.first, pending.second) } catch (_: Exception) {}
        }
    }

internal fun ChatState.refreshChain() {
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

internal fun ChatState.mechConfig(): J.Obj? {
        val first = selectedRoles.firstOrNull() ?: return null
        return advancedByRole[first]?.fields?.get("mechanics") as? J.Obj
    }

internal fun ChatState.checkEnding() {
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

internal fun ChatState.mechBattleConfig(): J.Obj? {
        val first = selectedRoles.firstOrNull() ?: return null
        return advancedByRole[first]?.fields?.get("battle") as? J.Obj
    }

internal fun ChatState.playerBattleConfig(): J.Obj? {
        return try {
            ((JsonS.parse(persona) as? J.Obj)?.fields?.get("advanced") as? J.Obj)?.fields?.get("battle") as? J.Obj
        } catch (_: Exception) {
            null
        }
    }

internal fun ChatState.saveGlobalRegex(lines: String) {
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

internal fun ChatState.roleSaveTree(role: String): TreeData {
        if (role == syncCardId(selectedRoles) && selectedRoles.size == 1) return tree.toData()
        val tf = treeFileForRole(role)
        return if (tf.exists()) try { TreeStore.load(tf).historyTree } catch (_: Exception) { ChatTree().toData() }
        else ChatTree().toData()
    }

internal fun ChatState.roleSaveMech(role: String): J.Obj? {
        if (role == syncCardId(selectedRoles) && selectedRoles.size == 1) return mech.snapshot()
        val f = stateFileForRole(role)
        return try { if (f.exists()) JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj else null } catch (_: Exception) { null }
    }

internal fun ChatState.listRoleSaves(role: String): List<J.Obj> = RoleSaves.load(role).map { RoleSaves.summary(it) }


internal fun ChatState.createRoleSave(role: String, label: String) {
        val slots = RoleSaves.load(role)
        val now = utcNowIso()
        slots.add(SaveSlot(label = label.ifBlank { "存档 " + (slots.size + 1) },
            createdAt = now, updatedAt = now, tree = roleSaveTree(role), mechState = roleSaveMech(role)))
        RoleSaves.save(role, slots)
    }

internal fun ChatState.saveToRoleSlot(role: String, slotId: String) {
        val slots = RoleSaves.load(role)
        val slot = slots.firstOrNull { it.id == slotId } ?: return
        slot.tree = roleSaveTree(role)
        slot.mechState = roleSaveMech(role)
        slot.updatedAt = utcNowIso()
        RoleSaves.save(role, slots)
    }

internal fun ChatState.loadRoleSlot(role: String, slotId: String) {
        val slots = RoleSaves.load(role)
        val slot = slots.firstOrNull { it.id == slotId } ?: return
        // 写回该角色的磁盘树/机制文件；若该角色当前正被加载，则载入内存并刷新界面
        try { TreeStore.save(treeFileForRole(role), SaveFile(role, "", slot.tree, treeTs = slot.updatedAt)) } catch (_: Exception) {}
        val ms = slot.mechState
        if (ms != null) {
            try { stateFileForRole(role).parentFile?.mkdirs(); stateFileForRole(role).writeText(JsonS.stringify(ms, pretty = true), Charsets.UTF_8) } catch (_: Exception) {}
        }
        if (role == syncCardId(selectedRoles) && selectedRoles.size == 1) {
            tree.loadData(slot.tree)
            tree.fixLeaf()
            mech.stateFile = stateFileForRole(role)
            mech.resetConfigTracking()
            mech.reload(mechConfig(), tree, reset = true)
            refreshChain()
        }
    }

internal fun ChatState.deleteRoleSlot(role: String, slotId: String) {
        RoleSaves.save(role, RoleSaves.load(role).filter { it.id != slotId })
    }

internal fun ChatState.renameRoleSlot(role: String, slotId: String, label: String) {
        val slots = RoleSaves.load(role)
        slots.firstOrNull { it.id == slotId }?.label = label.ifBlank { "未命名存档" }
        RoleSaves.save(role, slots)
    }

internal fun ChatState.reloadMech() {
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

internal fun ChatState.activeCardFace(): String {
        val n = selectedRoles.firstOrNull() ?: return ""
        return advancedByRole[n]?.fields?.get("card_face")?.str() ?: ""
    }

internal fun ChatState.pickGroupSpeaker(roster: List<String>, userText: String): String {
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

internal fun ChatState.resolveSpeaker(parsed: String?): String? {
        val p = parsed?.trim()
        if (!p.isNullOrBlank()) return p
        return if (selectedRoles.size > 1) lastSpeaker?.takeIf { it.isNotBlank() } else null
    }

internal fun ChatState.buildSystemPrompt(targetRole: String? = null, userText: String = ""): String {
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

internal fun ChatState.sysPrompt(userText: String): String {
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

internal fun ChatState.saveConfig() {
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
