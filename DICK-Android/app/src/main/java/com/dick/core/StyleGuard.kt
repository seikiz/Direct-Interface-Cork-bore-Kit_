package com.dick.core

import kotlin.math.roundToInt

/**
 * StyleGuard —— 确定性"风格闸"（工业化驱魔产线的一层，移植自桌面版）。
 *
 * 不跟注意力权重较劲：把"怎么说"从模型手里抽出来，用确定性规则兜住。
 * 只洗文学腔表达、词汇偏生活、把言情/本子比喻翻成事实，保留 10% 放任度；
 * 绝不删内容、绝不压缩；倒装/省略/语气词/叹词 永不触碰。
 *
 * 定位：模型输出定稿后、写入树之前调用。
 */
object StyleGuard {
    const val GRAMMAR_OFFSET = 0.10
    const val ENABLED = true

    // 文学词 → 生活词（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌含言情/本子重灾区）
    private val LIT_TO_LIFE = listOf(
        "眼眸" to "眼睛", "双眸" to "眼睛", "眸子" to "眼睛", "眼瞳" to "眼睛",
        "朱唇" to "嘴唇", "唇瓣" to "嘴唇", "双唇" to "嘴唇",
        "面庞" to "脸", "脸颊" to "脸", "俏脸" to "脸",
        "掌心" to "手心", "纤手" to "手", "玉手" to "手",
        "倩影" to "身影",
        "凝视" to "看", "注视" to "看",
        "轻叹" to "叹", "叹息" to "叹气",
        "呢喃" to "小声说", "低语" to "小声说", "低喃" to "小声念",
        "顿时" to "一下子", "霎时" to "一下子",
        "缓缓" to "慢慢", "徐徐" to "慢慢", "渐渐" to "慢慢",
        "仿佛" to "好像", "宛如" to "好像", "如同" to "好像", "犹如" to "好像",
        "好似" to "好像", "恍若" to "好像",
        // 言情/本子
        "娇躯" to "身子", "玉体" to "身体", "酮体" to "身体",
        "酥胸" to "胸口", "玉峰" to "胸口",
        "香肩" to "肩膀", "玉肩" to "肩膀",
        "玉腿" to "腿", "纤腿" to "腿", "修长的腿" to "腿",
        "香颈" to "脖子", "玉颈" to "脖子",
        "腰肢" to "腰", "纤腰" to "腰",
        "脊背" to "后背", "背脊" to "后背",
        "轻颤" to "抖", "战栗" to "发抖", "酥麻" to "麻",
        "潮红" to "脸红", "泛潮" to "红了", "泛红" to "红了",
        "娇喘" to "喘", "低吟" to "哼", "娇吟" to "哼", "婉转" to "哼",
        "耳鬓厮磨" to "贴着耳朵蹭", "缠绵" to "缠在一起", "缱绻" to "纠缠",
    )

    // 语境化比喻 → 事实
    private val METAPHOR_TO_FACT = listOf(
        "像电流穿过四肢" to "发麻", "电流窜过四肢" to "发麻", "像电流穿过" to "发麻",
        "电流一般" to "发麻", "酥麻的电流" to "麻意",
        "软成了一滩水" to "浑身发软", "软成一滩水" to "浑身发软",
        "融成一滩水" to "浑身发软", "化成一滩水" to "浑身发软", "化为春水" to "浑身发软",
        "眼神拉丝地看着" to "直勾勾地看着", "眼神拉丝" to "直勾勾地", "空气变得粘稠" to "空气安静",
        "浑身像被抽空了力气" to "浑身没力气", "像被抽空了力气" to "没力气",
        "脑子一片空白" to "脑子空白", "意乱情迷" to "脑子发懵",
        "呼吸变得沉重" to "呼吸变重",
        "脸颊绯红" to "脸红了", "双颊绯红" to "脸红了", "酥软" to "发软",
    )

    private val LIT_ADV_ATOMS = listOf(
        "缓缓地", "轻轻地", "悄悄地", "默默地", "静静地", "淡淡地", "微微地", "柔柔地",
        "渐渐地", "慢慢地", "幽幽地", "悄然地", "恍然地", "怯怯地",
        "若有所思地", "似有若无地", "不经意地", "无意识地", "下意识地",
        "不动声色地", "若无其事地",
    )
    private val LIT_ADV = Regex("(" + LIT_ADV_ATOMS.joinToString("|") + ")")
    private val STACK_ADV_RE = Regex(
        "((?:" + LIT_ADV_ATOMS.joinToString("|") + ")(?:、\\s*(?:" + LIT_ADV_ATOMS.joinToString("|") + "))+)"
    )

    private val LIT_OPENERS = listOf(
        "仿佛身处于", "仿佛置身于", "仿佛置身", "仿佛看到", "仿佛听到", "仿佛感觉",
        "宛如置身", "宛如一个", "宛如一场", "宛如被", "如同置身", "如同一个",
        "似有若无地", "恍若", "好像置身", "好像看到",
        "像是被", "像是身处于", "似乎置身于",
    )

    const val WEAK_PUNC = "，、；：——…"

    fun guard(text: String, enabled: Boolean = ENABLED, longSentence: Boolean = false): String {
        // 先过不可见字符防线：模型也可能吐零宽字符（尤其被用户诱导时）。
        // 这里本来就是「模型输出定稿后、写入树之前」的唯一漏斗，
        // 放在这一处就覆盖了所有 AI 输出，清不干净的会一直躺在记录里白烧 token。
        val cleaned = TextGuard.sanitize(text).first
        if (!enabled || cleaned.isBlank()) return cleaned
        var t = collapseEllipsis(cleaned)
        t = metaphorToFact(t)
        t = colloquialize(t)
        t = stripLiteraryOpeners(t)
        t = collapseStackedAdverbs(t)
        t = splitLongSentences(t, if (longSentence) 5000 else (70 + GRAMMAR_OFFSET * 300).roundToInt())
        return collapseWs(t)
    }

    private fun collapseEllipsis(t: String): String = t
        .replace(Regex("(?:。){4,}"), "……")
        .replace(Regex("(?:\\.){4,}"), "……")
        .replace(Regex("(?:…){3,}"), "……")

    private fun metaphorToFact(t: String): String {
        var s = t
        for ((src, dst) in METAPHOR_TO_FACT) if (src in s) s = s.replace(src, dst)
        return s
    }

    private fun colloquialize(t: String): String {
        var s = t
        for ((src, dst) in LIT_TO_LIFE) if (src in s) s = s.replace(src, dst)
        return s
    }

    private fun stripLiteraryOpeners(t: String): String {
        val opener = LIT_OPENERS.joinToString("|") { Regex.escape(it) }
        var s = t
        s = Regex("([。！？!?，,；]\\s*)(" + opener + ")").replace(s) { m -> m.groupValues[1] }
        s = Regex("^(" + opener + ")").replace(s) { "" }
        return s
    }

    private fun collapseStackedAdverbs(t: String): String {
        return STACK_ADV_RE.replace(t) { m ->
            LIT_ADV.find(m.groupValues[1])?.value ?: m.groupValues[1]
        }
    }

    private fun splitLongSentences(t: String, maxLen: Int): String {
        return t.split("\n").joinToString("\n") { line ->
            var rebuilt = ""
            for (sent in line.split(Regex("(?<=[。！？!?])"))) {
                if (sent.isBlank()) continue
                rebuilt += splitOverlong(sent.trim(), maxLen)
            }
            rebuilt
        }
    }

    private fun splitOverlong(sentence: String, maxLen: Int): String {
        if (sentence.length <= maxLen) return sentence
        val parts = mutableListOf<String>()
        var s = sentence
        while (s.length > maxLen) {
            var sp = -1
            for (i in s.indices) {
                if (i <= maxLen && s[i] in WEAK_PUNC) sp = i
            }
            if (sp <= 0) break
            parts.add(s.substring(0, sp + 1).trim())
            s = s.substring(sp + 1).trim()
        }
        parts.add(s)
        return parts.filter { it.isNotBlank() }.joinToString(" ")
    }

    private fun collapseWs(t: String): String = t.replace(Regex("\n{3,}"), "\n\n").trim()
}
