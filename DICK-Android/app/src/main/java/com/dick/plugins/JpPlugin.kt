package com.dick.plugins

import com.dick.core.ChatEngine

/** 日文翻译：/jp 中→日、/zh 日→中（通过引擎单次调用，仅输出译文） */
class JpPlugin : Plugin {
    override val name = "日文翻译"
    override val version = "1.0"
    override val description = "/jp 文本 中译日；/zh 文本 日译中"
    override var enabled = true

    var engine: ChatEngine? = null

    override fun onCommand(command: String, args: String): String? {
        val text = (args ?: "").trim()
        if (text.isEmpty()) return "🌏 用法：/jp 文本（中→日）或 /zh 文本（日→中）"
        val e = engine ?: return "⚠️ 引擎未就绪"
        val prompt = if (command == "jp") {
            "把下面内容翻译成日语，只输出译文，不要任何解释：" + 10.toChar() + text
        } else if (command == "zh") {
            "把下面内容翻译成中文，只输出译文，不要任何解释：" + 10.toChar() + text
        } else return null
        val result = e.complete(emptyList(), prompt)
        return if (result.isNullOrBlank()) "⚠️ 翻译失败（检查 Key/网络）"
        else (if (command == "jp") "🌏 日译：" else "🌏 中译：") + 10.toChar() + result
    }
}
