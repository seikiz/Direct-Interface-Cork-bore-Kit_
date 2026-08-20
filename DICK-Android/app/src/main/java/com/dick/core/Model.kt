package com.dick.core

import java.time.LocalDateTime
import java.util.UUID

/** 对话节点 —— 与 Python 版 MessageNode 字段逐一对应 */
class MessageNode(
    val id: String = UUID.randomUUID().toString(),
    val role: String,
    var content: String,
    val parentId: String? = null,
    val childrenIds: MutableList<String> = mutableListOf(),
    val timestamp: String = LocalDateTime.now().toString(),
    var metadata: J = J.Null,
) {
    fun toJson(): J.Obj {
        val o = J.Obj()
        o.fields["id"] = J.Str(id)
        o.fields["role"] = J.Str(role)
        o.fields["content"] = J.Str(content)
        o.fields["parent_id"] = J.strOr(parentId)
        o.fields["children_ids"] = J.Arr(childrenIds.map { J.Str(it) }.toMutableList())
        o.fields["timestamp"] = J.Str(timestamp)
        o.fields["metadata"] = metadata
        return o
    }

    companion object {
        fun fromJson(o: J.Obj): MessageNode {
            val node = MessageNode(
                id = o.fields["id"]?.str() ?: UUID.randomUUID().toString(),
                role = o.fields["role"]?.str() ?: "user",
                content = o.fields["content"]?.str() ?: "",
                parentId = (o.fields["parent_id"] as? J.Str)?.v,
                timestamp = o.fields["timestamp"]?.str() ?: LocalDateTime.now().toString(),
                metadata = o.fields["metadata"] ?: J.Null,
            )
            (o.fields["children_ids"] as? J.Arr)?.items?.forEach {
                it.str()?.let { s -> node.childrenIds.add(s) }
            }
            return node
        }
    }
}

/** 存档中的 history_tree 结构（与 Python get_all_nodes_data 一致） */
class TreeData(
    val nodes: MutableMap<String, MessageNode> = mutableMapOf(),
    var rootId: String? = null,
    var currentLeafId: String? = null,
) {
    fun toJson(): J.Obj {
        val o = J.Obj()
        val ns = J.Obj()
        for ((k, v) in nodes) ns.fields[k] = v.toJson()
        o.fields["nodes"] = ns
        o.fields["root_id"] = J.strOr(rootId)
        o.fields["current_leaf_id"] = J.strOr(currentLeafId)
        return o
    }

    companion object {
        fun fromJson(o: J.Obj): TreeData {
            val t = TreeData()
            (o.fields["nodes"] as? J.Obj)?.fields?.forEach { (k, v) ->
                (v as? J.Obj)?.let { t.nodes[k] = MessageNode.fromJson(it) }
            }
            t.rootId = (o.fields["root_id"] as? J.Str)?.v
            t.currentLeafId = (o.fields["current_leaf_id"] as? J.Str)?.v
            return t
        }
    }
}

/** saves 目录下的 .json 顶层结构 */
class SaveFile(
    val name: String? = null,
    val systemPrompt: String? = null,
    val historyTree: TreeData = TreeData(),
    val cardData: J.Obj? = null,
) {
    fun toJson(): J.Obj {
        val o = J.Obj()
        o.fields["name"] = J.strOr(name)
        o.fields["system_prompt"] = J.strOr(systemPrompt)
        o.fields["history_tree"] = historyTree.toJson()
        if (cardData != null) o.fields["card_data"] = cardData
        return o
    }

    companion object {
        fun fromJson(o: J.Obj): SaveFile = SaveFile(
            name = (o.fields["name"] as? J.Str)?.v,
            systemPrompt = (o.fields["system_prompt"] as? J.Str)?.v,
            historyTree = (o.fields["history_tree"] as? J.Obj)?.let { TreeData.fromJson(it) } ?: TreeData(),
            cardData = o.fields["card_data"] as? J.Obj,
        )
    }
}

/** worlds 目录下的 .json 世界书条目（与桌面版语义对齐） */
data class WorldEntry(
    val keywords: MutableList<String> = mutableListOf(),
    val content: String = "",
    val weight: Int = 0,
    val match: String = "any",
    val probability: Int = 100,
    val depth: Int = 1,
    val enabled: Boolean = true,
    val constant: Boolean = false,
) {
    fun toJson(): J.Obj {
        val o = J.Obj()
        o.fields["keywords"] = J.Arr(keywords.map { J.Str(it) }.toMutableList())
        o.fields["content"] = J.Str(content)
        o.fields["weight"] = J.Num(weight.toDouble(), weight.toString())
        o.fields["match"] = J.Str(match)
        o.fields["probability"] = J.Num(probability.toDouble(), probability.toString())
        o.fields["depth"] = J.Num(depth.toDouble(), depth.toString())
        o.fields["enabled"] = J.Bool(enabled)
        o.fields["constant"] = J.Bool(constant)
        return o
    }

    companion object {
        fun fromJson(o: J.Obj): WorldEntry = WorldEntry(
            keywords = (o.fields["keywords"] as? J.Arr)?.items?.mapNotNull { it.str() }?.toMutableList() ?: mutableListOf(),
            content = o.fields["content"]?.str() ?: "",
            weight = (o.fields["weight"] as? J.Num)?.v?.toInt() ?: 0,
            match = o.fields["match"]?.str() ?: "any",
            probability = (o.fields["probability"] as? J.Num)?.v?.toInt() ?: 100,
            depth = ((o.fields["depth"] as? J.Num)?.v?.toInt() ?: 1).coerceIn(1, 4),
            enabled = (o.fields["enabled"] as? J.Bool)?.v ?: true,
            constant = (o.fields["constant"] as? J.Bool)?.v ?: false,
        )
    }
}

/** worlds 目录下的 .json 世界卡 */
class WorldData(
    val name: String = "",
    val description: String = "",
    val rules: MutableList<String> = mutableListOf(),
    val entries: MutableList<WorldEntry> = mutableListOf(),
    val params: MutableMap<String, String> = mutableMapOf(),
) {
    fun toJson(): J.Obj {
        val o = J.Obj()
        o.fields["name"] = J.Str(name)
        o.fields["description"] = J.Str(description)
        o.fields["rules"] = J.Arr(rules.map { J.Str(it) }.toMutableList())
        o.fields["entries"] = J.Arr(entries.map { it.toJson() }.toMutableList())
        if (params.isNotEmpty()) {
            val p = J.Obj()
            for ((k, v) in params) p.fields[k] = J.Str(v)
            o.fields["params"] = p
        }
        return o
    }

    companion object {
        fun fromJson(o: J.Obj): WorldData {
            val params = mutableMapOf<String, String>()
            (o.fields["params"] as? J.Obj)?.fields?.forEach { (k, v) -> v.str()?.let { params[k] = it } }
            return WorldData(
                name = o.fields["name"]?.str() ?: "",
                description = o.fields["description"]?.str() ?: "",
                rules = (o.fields["rules"] as? J.Arr)?.items?.mapNotNull { it.str() }?.toMutableList() ?: mutableListOf(),
                entries = (o.fields["entries"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.map { WorldEntry.fromJson(it) }?.toMutableList() ?: mutableListOf(),
                params = params,
            )
        }
    }
}

/** personas 目录下的 .json 玩家角色卡 */
class PersonaData(
    val name: String = "",
    val appearance: String = "",
    val background: String = "",
    val personality: MutableList<String> = mutableListOf(),
    val speechStyle: String = "",
    val notes: String = "",
) {
    fun toJson(): J.Obj {
        val o = J.Obj()
        o.fields["name"] = J.Str(name)
        o.fields["appearance"] = J.Str(appearance)
        o.fields["background"] = J.Str(background)
        o.fields["personality"] = J.Arr(personality.map { J.Str(it) }.toMutableList())
        o.fields["speech_style"] = J.Str(speechStyle)
        o.fields["notes"] = J.Str(notes)
        return o
    }

    companion object {
        fun fromJson(o: J.Obj): PersonaData = PersonaData(
            name = o.fields["name"]?.str() ?: "",
            appearance = o.fields["appearance"]?.str() ?: "",
            background = o.fields["background"]?.str() ?: "",
            personality = (o.fields["personality"] as? J.Arr)?.items?.mapNotNull { it.str() }?.toMutableList() ?: mutableListOf(),
            speechStyle = o.fields["speech_style"]?.str() ?: "",
            notes = o.fields["notes"]?.str() ?: "",
        )
    }
}

/** prompt_presets 目录下的 .json 提示词预设 */
class PromptPreset(
    val name: String = "",
    val systemPrefix: String = "",
    val rules: String = "",
    val systemSuffix: String = "",
) {
    fun toJson(): J.Obj {
        val o = J.Obj()
        o.fields["name"] = J.Str(name)
        o.fields["system_prefix"] = J.Str(systemPrefix)
        o.fields["rules"] = J.Str(rules)
        o.fields["system_suffix"] = J.Str(systemSuffix)
        return o
    }

    companion object {
        fun fromJson(o: J.Obj): PromptPreset = PromptPreset(
            name = o.fields["name"]?.str() ?: "",
            systemPrefix = o.fields["system_prefix"]?.str() ?: "",
            rules = o.fields["rules"]?.str() ?: "",
            systemSuffix = o.fields["system_suffix"]?.str() ?: "",
        )
    }
}

/** config.json 全局配置（字段与 Python _save_config 一致） */
class AppConfig(
    val apiKey: String = "",
    val baseUrl: String = "https://api.deepseek.com",
    val provider: String = "DeepSeek 官方",
    val model: String = "deepseek-v4-flash",
    val fontSize: Int = 12,
    val fontName: String = "",
    val welcomeShown: Boolean = false,
    val lastRole: String = "",
    val persona: String = "",
    val promptPreset: String = "",
    val contextBudget: Int = 0,
    val rollingSummary: Boolean = true,
    val sidebarCollapsed: Boolean = false,
) {
    fun toJson(): J.Obj {
        val o = J.Obj()
        o.fields["api_key"] = J.Str(apiKey)
        o.fields["base_url"] = J.Str(baseUrl)
        o.fields["provider"] = J.Str(provider)
        o.fields["model"] = J.Str(model)
        o.fields["font_size"] = J.Num(fontSize.toDouble(), fontSize.toString())
        o.fields["font_name"] = J.Str(fontName)
        o.fields["welcome_shown"] = J.Bool(welcomeShown)
        o.fields["last_role"] = J.Str(lastRole)
        o.fields["persona"] = J.Str(persona)
        o.fields["prompt_preset"] = J.Str(promptPreset)
        o.fields["context_budget"] = J.Num(contextBudget.toDouble(), contextBudget.toString())
        o.fields["rolling_summary"] = J.Bool(rollingSummary)
        o.fields["sidebar_collapsed"] = J.Bool(sidebarCollapsed)
        return o
    }

    companion object {
        private fun s(o: J.Obj, key: String, dft: String): String = o.fields[key]?.str() ?: dft
        private fun i(o: J.Obj, key: String, dft: Int): Int = (o.fields[key] as? J.Num)?.v?.toInt() ?: dft
        private fun b(o: J.Obj, key: String, dft: Boolean): Boolean = (o.fields[key] as? J.Bool)?.v ?: dft

        fun fromJson(o: J.Obj): AppConfig = AppConfig(
            apiKey = s(o, "api_key", ""),
            baseUrl = s(o, "base_url", "https://api.deepseek.com"),
            provider = s(o, "provider", "DeepSeek 官方"),
            model = s(o, "model", "deepseek-v4-flash"),
            fontSize = i(o, "font_size", 12),
            fontName = s(o, "font_name", ""),
            welcomeShown = b(o, "welcome_shown", false),
            lastRole = s(o, "last_role", ""),
            persona = s(o, "persona", ""),
            promptPreset = s(o, "prompt_preset", ""),
            contextBudget = i(o, "context_budget", 0),
            rollingSummary = b(o, "rolling_summary", true),
            sidebarCollapsed = b(o, "sidebar_collapsed", false),
        )
    }
}
