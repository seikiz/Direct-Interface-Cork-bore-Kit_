package com.dick.plugins

import com.dick.core.ChatEngine
import com.dick.core.MessageNode

/** 多候选回复：/swipe 用非流式调用生成备选回答 */
class SwipePlugin : Plugin {
    override val name = "多候选回复"
    override val version = "1.0"
    override val description = "/swipe 生成备选回复"
    override var enabled = true

    var engine: ChatEngine? = null
    var chain: List<MessageNode> = emptyList()
    var systemPrompt: String? = null
    val candidates = mutableListOf<String>()

    override fun onCommand(command: String, args: String): String? {
        if (command != "swipe") return null
        if (chain.isEmpty()) return "⚠️ 暂无对话可生成候选"
        val e = engine ?: return "⚠️ 引擎未就绪"
        val target = if (chain.last().role == "assistant") chain.dropLast(1) else chain
        val cand = e.complete(target, systemPrompt)
        if (cand.isNullOrBlank()) return "⚠️ 候选生成失败（检查 Key/网络）"
        candidates.add(cand)
        return "🔄 候选 " + candidates.size + "：" + 10.toChar() + cand
    }
}
