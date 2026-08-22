package com.dick.plugins

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.dick.core.ChatEngine
import com.dick.core.ChatTree
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.MessageNode

/**
 * Galgame 选项：视觉小说式选择肢。
 * AI 回复后自动生成 N 个剧情选项按钮，点选即以该行动作为玩家输入发言（也可照常自由输入）。
 * 命令：/cyoa 手动生成、/cyoa show 查看当前选项。
 * 设置：count 每轮选项数量（2-4，默认 3）；auto 是否自动生成（默认开）。
 */
class GalgamePlugin : Plugin {
    override val name = "Galgame 选项"
    override val version = "1.1"
    override val description = "视觉小说式选择肢：AI 回复后自动生成剧情选项（支持机制卡好感/状态效果），点选即以该行动发言（/cyoa 手动）"
    override var enabled = false

    /** 选项：文本 + 事件结果提示 + 机制效果（aff=好感度变化，st=状态变化） */
    data class ChoiceItem(val text: String, val result: String?, val aff: Int?, val st: Map<String, String>?)

    /** 由宿主注入 */
    var engine: ChatEngine? = null
    var tree: ChatTree? = null
    var mechConfigProvider: (() -> J.Obj?)? = null
    var mechStateProvider: (() -> J.Obj?)? = null
    var mechEventProvider: (() -> J.Obj?)? = null

    var count: Int by mutableStateOf(3)
    var auto: Boolean by mutableStateOf(true)

    val choices = mutableStateListOf<ChoiceItem>()
    var loading by mutableStateOf(false)
    var error by mutableStateOf("")

    private var genUserNode: String? = null

    fun clearChoices() {
        synchronized(this) {
            choices.clear()
            loading = false
            error = ""
            genUserNode = null
        }
    }

    /** 手动触发（/cyoa 或快捷面板按钮）。返回状态文本。 */
    fun manualGenerate(): String {
        if (loading) return "⏳ 正在生成选项…"
        if (engine == null) return "⚠️ 请先设置 API Key"
        startGenerate()
        return "⏳ 正在生成 $count 个剧情选项…"
    }

    override fun onMessageSend(userInput: String): String? {
        // 玩家发送新消息（打字或点选项）后，旧选项作废
        clearChoices()
        return userInput
    }

    override fun onMessageReceived(userInput: String, aiReply: String) {
        if (!auto || loading) return
        val uid = lastUserNodeId()
        synchronized(this) {
            if (genUserNode == uid && choices.isNotEmpty()) return  // 同一轮不重复生成（滑条等）
        }
        startGenerate()
    }

    override fun onCommand(command: String, args: String): String? {
        if (command != "cyoa") return null
        if (args.trim() in setOf("show", "查看", "list")) {
            synchronized(this) {
                if (choices.isEmpty()) return "🎮 还没有选项，先输入 /cyoa 生成"
                return "🎮 当前选项：\n" + choices.mapIndexed { i, c -> "${i + 1}. ${c.text}" }.joinToString("\n")
            }
        }
        return manualGenerate()
    }

    // ---------- 生成 ----------
    private fun lastUserNodeId(): String? {
        val t = tree ?: return null
        var nid = t.currentLeafId
        var guard = 0
        while (nid != null && guard++ < 500) {
            val node = t.getNode(nid) ?: break
            if (node.role == "user") return nid
            nid = node.parentId
        }
        return null
    }

    private fun startGenerate() {
        synchronized(this) {
            loading = true
            error = ""
        }
        Thread {
            val e = engine
            if (e == null) {
                synchronized(this) { loading = false; error = "引擎未就绪" }
                return@Thread
            }
            val n = maxOf(2, minOf(4, count))
            // 机制卡：若启用好感/状态，选项需附带机制效果（前端小字展示）
            val mech = mechConfigProvider?.invoke()
            val affCfg = mech?.fields?.get("affection") as? J.Obj
            val hasAff = affCfg != null && affCfg.fields["enabled"]?.bool() == true
            val stCfg = mech?.fields?.get("status") as? J.Obj
            val stFields = stCfg?.fields?.get("fields") as? J.Arr
            val hasSt = stCfg != null && stCfg.fields["enabled"]?.bool() == true && stFields?.items?.isNotEmpty() == true
            val effectFmt = mutableListOf<String>()
            if (hasAff) effectFmt.add("\"aff\": 好感度变化整数，必须用 ±N 相对值（如 +2 / -1；无影响则省略）")
            if (hasSt) {
                val keys = stFields!!.items.mapNotNull { (it as? J.Obj)?.fields?.get("key")?.str() }
                val curVals = stFields!!.items.mapNotNull { (it as? J.Obj)?.let { fo ->
                    val k = fo.fields["key"]?.str() ?: return@mapNotNull null
                    val cur = mechStateProvider?.invoke()?.fields?.get("status")?.obj()?.fields?.get(k)
                    val shown = cur?.let { c -> if (c is J.Num) c.v.toInt().toString() else c.str() } ?: (fo.fields["initial"]?.let { i -> if (i is J.Num) i.v.toInt().toString() else i.str() } ?: "")
                    "$k=${shown}"
                } }
                effectFmt.add("\"st\": 状态变化对象，键为 ${keys.joinToString("、")}（当前值：${curVals.joinToString("，")}）。整数型必须用 ±N 相对值（如 \"sex\":+1 表示在当前值上加 1），禁止写绝对值目标值；枚举型给新值（如 \"心情\":\"开心\"）")
            }
            val system = buildString {
                append("你是视觉小说（Galgame）的选项生成器。根据最近剧情，为玩家（用户）生成 $n 个简短、可行、有区分度的下一步行动选项。")
                append("要求：每个选项不超过 18 个字，口语化，贴合当前角色性格与剧情走向；不要剧透后续剧情，不要输出编号或'选项一'这类前缀。")
                append("每个选项必须带 \"result\"：一句事件结果提示（≤12 字，模糊、不剧透具体数值，如 \"她可能会心头一暖\" / \"气氛可能会尴尬\"）。")
                // 结合当前触发事件：选项围绕事件展开
                mechEventProvider?.invoke()?.let { ev ->
                    val evName = ev.fields["name"]?.str() ?: ev.fields["id"]?.str() ?: return@let
                    val evPrompt = ev.fields["prompt"]?.str() ?: ""
                    append("\n【当前剧情事件】刚才触发了「$evName」事件。")
                    if (evPrompt.isNotBlank()) append("事件描述：$evPrompt")
                    append(" 请让这组选项**紧密围绕这个事件展开**——玩家下一步行动应针对该事件的走向，而不是无关的日常动作。")
                }
                if (effectFmt.isNotEmpty()) {
                    append("当前角色卡启用了机制（好感度/状态），每个选项还必须附带机制效果标签：")
                    append("只输出 JSON 数组，每项为 {\"text\": \"选项文本\", \"result\": \"结果提示\", ").append(effectFmt.joinToString(", ")).append("}。")
                    append("text 不超过 18 字；效果要贴合该选项的后果（可能为正、负或无），")
                    append("例如：[{\"text\":\"温柔关心她\",\"result\":\"她可能会心头一暖\",\"aff\":+3},{\"text\":\"冷嘲热讽\",\"result\":\"可能会惹她生气\",\"aff\":-5,\"st\":{\"心情\":\"生气\"}}]")
                } else {
                    append("只输出 JSON 数组，每项为 {\"text\": \"选项文本\", \"result\": \"结果提示\"}，")
                    append("例如：[{\"text\":\"轻轻敲门\",\"result\":\"屋里人可能会回应\"},{\"text\":\"转身离开\",\"result\":\"可能会就此错过\"}]")
                }
            }
            val reply = e.complete(listOf(MessageNode(role = "user", content = buildTranscript())), system)
            val items = parseOptions(reply, n)
            synchronized(this) {
                if (items.isNotEmpty()) {
                    choices.clear()
                    choices.addAll(items)
                    error = ""
                    genUserNode = lastUserNodeId()
                } else {
                    choices.clear()
                    error = "未能解析出选项（模型输出格式异常）"
                }
                loading = false
            }
        }.apply { isDaemon = true }.start()
    }

    private fun buildTranscript(): String {
        val t = tree ?: return "（尚无对话）"
        val chain = t.getCurrentChainNodes().filter { it.role != "system" }
        val lines = chain.takeLast(8).map { n ->
            val content = n.content.take(300)
            if (n.role == "user") "你：$content"
            else {
                val sp = (n.metadata as? J.Obj)?.fields?.get("speaker")?.str() ?: "AI"
                "$sp：$content"
            }
        }
        val parts = mutableListOf<String>()
        parts.add("【最近对话】\n" + (if (lines.isEmpty()) "（尚无对话）" else lines.joinToString("\n")))
        // 当前状态摘要（泛用）
        try {
            mechStateProvider?.invoke()?.let { st ->
                val status = st.fields["status"] as? J.Obj
                val sts = mutableListOf<String>()
                st.fields["affection"]?.let { aff -> sts.add("好感度=${(aff as? J.Num)?.v?.toInt() ?: aff.int()}") }
                status?.fields?.forEach { (k, v) ->
                    if (k == "buffs") return@forEach
                    sts.add(if (v is J.Num) "$k=${v.v.toInt()}" else "$k=${v.str() ?: v.int()}")
                }
                if (sts.isNotEmpty()) parts.add("【当前状态】" + sts.joinToString("，"))
            }
        } catch (_: Exception) {
        }
        // 当前事件
        try {
            mechEventProvider?.invoke()?.let { ev ->
                val evName = ev.fields["name"]?.str() ?: ev.fields["id"]?.str() ?: return@let
                val evPrompt = ev.fields["prompt"]?.str() ?: ""
                parts.add("【当前剧情事件】触发「$evName」$evPrompt")
            }
        } catch (_: Exception) {
        }
        return parts.joinToString("\n\n")
    }

    // ---------- 解析 ----------
    /** 宽容解析 JSON 数组：原文 / 提取 [..] 子串 / 容忍尾随逗号。失败返回 null */
    private fun tryJsonArray(s: String): J.Arr? {
        val candidates = mutableListOf(s)
        val i = s.indexOf('[')
        val j = s.lastIndexOf(']')
        if (i >= 0 && j > i) candidates.add(s.substring(i, j + 1))
        val cleaned = s.replace(Regex(",\\s*([}\\]])"), "$1")   // 容忍尾随逗号（,} / ,]）
        if (cleaned != s) {
            candidates.add(cleaned)
            val i2 = cleaned.indexOf('[')
            val j2 = cleaned.lastIndexOf(']')
            if (i2 >= 0 && j2 > i2) candidates.add(cleaned.substring(i2, j2 + 1))
        }
        for (c in candidates) {
            try {
                val arr = JsonS.parse(c) as? J.Arr
                if (arr != null) return arr
            } catch (_: Exception) {
            }
        }
        return null
    }

    private fun parseOptions(text: String?, count: Int): List<ChoiceItem> {
        if (text.isNullOrBlank()) return emptyList()
        var trimmed = text.trim()
        // 模型常输出 +N（JSON 数字不允许 + 前缀），先宽容化
        trimmed = trimmed.replace(Regex("(?<=[:：])\\s*\\+"), " ")
        // 1) JSON 数组（字符串或 {text, result, aff, st} 对象，宽容解析）
        tryJsonArray(trimmed)?.let { return clean(it.items, count) }
        // 2) ```json ``` 代码块
        val fence = Regex("```(?:json)?\\s*([\\s\\S]*?)```").find(trimmed)
        if (fence != null) {
            tryJsonArray(fence.groupValues[1].trim())?.let { return clean(it.items, count) }
        }
        // 3) 编号/项目符号逐行；跳过 JSON 残留行（{/[ 开头，避免把 JSON 原文当选项文本显示）
        val lines = trimmed.split(Regex("[\\n\\r]+")).map { it.trim() }
            .filter { it.isNotEmpty() && !it.startsWith("{") && !it.startsWith("[") }
        if (lines.size == 1 && !Regex("^\\s*(?:[\\[\\(]?\\d+[\\]\\)\\.、:：)\\s]+|[-*•·]\\s+)").containsMatchIn(lines[0])) {
            return emptyList()
        }
        return clean(lines.map { J.Str(it) }, count)
    }

    private fun clean(raw: List<J>, count: Int): List<ChoiceItem> {
        val out = mutableListOf<ChoiceItem>()
        val seen = mutableSetOf<String>()
        for (x in raw) {
            var s: String
            var result: String? = null
            var aff: Int? = null
            var st: Map<String, String>? = null
            val obj = x as? J.Obj
            if (obj != null) {
                s = obj.fields["text"]?.str() ?: ""
                result = obj.fields["result"]?.str()?.takeIf { it.isNotBlank() }?.take(20)
                aff = (obj.fields["aff"] as? J.Num)?.v?.toInt()
                val stObj = obj.fields["st"] as? J.Obj
                if (stObj != null) {
                    st = stObj.fields.mapNotNull { (k, v) ->
                        val vs = v.str() ?: v.int().toString()
                        k.takeIf { it.isNotBlank() }?.let { it to vs }
                    }.toMap()
                }
            } else {
                s = x.str() ?: ""
            }
            s = s.trim()
            s = Regex("^[\\[\\(]?\\d+[\\]\\)\\.、:：)\\s]+").replaceFirst(s, "")
            s = Regex("^[-*•·]\\s*").replaceFirst(s, "")
            s = Regex("[（(][^（）()]*[）)]\\s*$").replaceFirst(s, "")   // 末尾括号说明（模型常附加）
            s = s.trim().trim('"').trim('\'')
            if (s.isEmpty() || s.length > 50 || s in seen) continue
            seen.add(s)
            out.add(ChoiceItem(s, result, aff, st))
            if (out.size >= count) break
        }
        return out
    }
}
