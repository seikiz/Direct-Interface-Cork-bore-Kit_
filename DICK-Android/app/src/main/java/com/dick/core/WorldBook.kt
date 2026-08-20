package com.dick.core

import kotlin.random.Random

/**
 * 世界书触发注入 —— 与桌面版语义对齐：
 *   keywords 命中（any/all/regex，忽略大小写）；depth 控制递归链最大长度
 *   （1=仅扫用户输入，2=命中内容可再触发一层，上限 4）；constant 且 enabled 直接注入；
 *   probability<100 随机；按 weight 降序取前 world_max_entries（默认 3）。
 */
object WorldBook {
    const val MAX_ENTRIES = 3

    /** 单条是否命中给定文本（空关键词不命中） */
    fun matches(entry: WorldEntry, text: String): Boolean {
        if (entry.keywords.isEmpty()) return false
        return when (entry.match) {
            "all" -> entry.keywords.all { kw -> text.contains(kw, ignoreCase = true) }
            "regex" -> entry.keywords.any { kw ->
                try { Regex(kw).containsMatchIn(text) } catch (_: Exception) { false }
            }
            else -> entry.keywords.any { kw -> text.contains(kw, ignoreCase = true) }
        }
    }

    /** 返回按发现顺序排列的命中条目下标（去重；递归 depth-1 轮，无新命中即停） */
    fun matchedIndices(userInput: String, entries: List<WorldEntry>): List<Int> {
        val maxDepth = (entries.filter { it.enabled }.maxOfOrNull { it.depth } ?: 1).coerceIn(1, 4)
        val seen = mutableSetOf<Int>()
        val order = mutableListOf<Int>()
        var scanText = userInput
        for (round in 1..maxDepth) {
            val newly = mutableListOf<Int>()
            for ((idx, e) in entries.withIndex()) {
                if (!e.enabled || seen.contains(idx)) continue
                if (!e.constant && e.depth < round) continue
                val hit = if (e.constant) round == 1 else matches(e, scanText)
                if (!hit) continue
                if (e.probability < 100 && Random.nextInt(100) >= e.probability) continue
                seen.add(idx)
                newly.add(idx)
            }
            if (newly.isEmpty()) break
            order.addAll(newly)
            scanText = newly.joinToString(10.toChar().toString()) { entries[it].content }
        }
        return order
    }

    /** 按命中下标组装注入文本：常驻条目全部注入（不受上限约束），
     *  关键词命中按 weight 降序取前 maxEntries（与桌面版一致） */
    fun injectFrom(userInput: String, entries: List<WorldEntry>, idxs: List<Int>, maxEntries: Int = MAX_ENTRIES): String {
        val hits = idxs.map { entries[it] }
        val consts = hits.filter { it.constant }
        val matched = hits.filter { !it.constant }.sortedByDescending { it.weight }.take(maxEntries)
        return (consts + matched)
            .joinToString(10.toChar().toString() + 10.toChar().toString()) { it.content }
            .trim()
    }

    /** 便捷方法：直接注入 */
    fun inject(userInput: String, entries: List<WorldEntry>, maxEntries: Int = MAX_ENTRIES): String =
        injectFrom(userInput, entries, matchedIndices(userInput, entries), maxEntries)
}
