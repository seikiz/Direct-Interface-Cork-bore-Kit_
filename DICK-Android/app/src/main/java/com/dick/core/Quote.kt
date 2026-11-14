package com.dick.core

/**
 * 引用对话（Android 端）—— 与桌面 msg_quote.py 同一套口径：
 *
 *   · 引用是**用户消息的附件**，不是新消息：树里仍只有一条 user 节点，metadata["quote"] 存引用；
 *   · 发给模型的是「〔引用 谁：摘要〕\n正文」，界面上正文照旧显示（引用块单独画）；
 *   · 摘要截 200 字 —— 引用不能把上下文翻倍。
 */
data class QuoteRef(
    val id: String,
    val role: String,
    val speaker: String? = null,
    val excerpt: String,
) {
    fun who(): String = speaker?.takeIf { it.isNotBlank() } ?: if (role == "user") "你" else "对方"
}

object Quote {
    const val MAX = 200

    fun make(id: String, role: String, speaker: String?, text: String): QuoteRef? {
        val body = (text ?: "").replace(Regex("\\s+"), " ").trim()
        if (id.isBlank() || body.isBlank()) return null
        val cut = if (body.length > MAX) body.take(MAX).trimEnd() + "…" else body
        return QuoteRef(id = id, role = role.ifBlank { "assistant" },
            speaker = speaker?.takeIf { it.isNotBlank() }, excerpt = cut)
    }

    /** 提示词里的引用块（单行<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌，模型不会把它当成新消息） */
    fun block(q: QuoteRef?): String =
        if (q == null || q.excerpt.isBlank()) "" else "〔引用 ${q.who()}：${q.excerpt}〕"

    /** 接到正文前面；没有引用就原样返回（零成本） */
    fun apply(content: String, q: QuoteRef?): String {
        val b = block(q)
        return if (b.isEmpty()) content else b + "\n" + content
    }

    fun toJson(q: QuoteRef): J.Obj {
        val o = J.Obj()
        o.fields["id"] = J.Str(q.id)
        o.fields["role"] = J.Str(q.role)
        o.fields["speaker"] = if (q.speaker == null) J.Null else J.Str(q.speaker)
        o.fields["excerpt"] = J.Str(q.excerpt)
        return o
    }

    /** 从树节点 metadata 里读引用（老数据没有这个键 → null） */
    fun fromNode(node: MessageNode?): QuoteRef? {
        val o = node?.metadata as? J.Obj ?: return null
        val q = o.fields["quote"] as? J.Obj ?: return null
        val id = q.fields["id"]?.str() ?: return null
        val excerpt = q.fields["excerpt"]?.str() ?: return null
        if (excerpt.isBlank()) return null
        return QuoteRef(id = id, role = q.fields["role"]?.str() ?: "assistant",
            speaker = q.fields["speaker"]?.str(), excerpt = excerpt)
    }
}
