package com.dick.core

/**
 * TextGuard —— 不可见字符防线（安卓版，逻辑对位桌面版 text_guard.py）
 *
 * 为什么必须拦（不是洁癖，是真危害）：
 *  ① 白烧 token：几千个零宽字符就是几千 token，用户界面上什么都看不见，钱却花了；
 *  ② 卡死界面：手机渲染更弱，一长串不可见字符就能把列表拖住；
 *  ③ 藏提示词注入：正文里夹一段看不见的指令，人眼审不出来；
 *  ④ 绕过过滤：把敏感词中间插零宽字符，关键词匹配立刻失效。
 *
 * 策略（关键是别误伤正常内容）：
 *  · 双向控制符 / 标签字符 / 软连字符这些没有正当用途的 → 一律删；
 *  · ZWJ(U+200D)/ZWNJ(U+200C) 在 emoji 组合(👨‍👩‍👧)和部分文字里是合法的 →
 *    少量保留，一旦数量超标（典型的字符炸弹）就判为攻击，全删。
 *
 * 注意：U+E0000–U+E007F 标签字符区在 BMP 之外，是代理对，
 * 所以必须按【码点】而不是按 Char 遍历，否则扫不到。
 */
object TextGuard {

    /** 一律删除：这些字符在聊天里没有正当用途 */
    private val ALWAYS_STRIP: Set<Char> = setOf(
        '\u200B', // 零宽空格
        '\u2060', // 词连接符
        '\uFEFF', // 零宽不换行空格 / BOM
        '\u00AD', // 软连字符
        '\u034F', // 组合字形连接符
        '\u180E', // 蒙古文元音分隔符
        '\u061C', // 阿拉伯字母标记
        '\u200E', '\u200F',                           // LRM / RLM
        '\u202A', '\u202B', '\u202C', '\u202D', '\u202E', // 双向嵌入 / 覆盖
        '\u2066', '\u2067', '\u2068', '\u2069',      // 双向隔离
        '\u2061', '\u2062', '\u2063', '\u2064',      // 不可见运算符
    )

    /** 有条件保留：少量是合法的（emoji / 文字连写），超标就判为炸弹 */
    private val CONDITIONAL: Set<Char> = setOf('\u200C', '\u200D')

    private const val BOMB_TOTAL = 24           // 数量超过这个数 → 炸弹
    private const val BOMB_RATIO = 0.12         // 或占比超过这个数（配绝对下限）
    private const val BOMB_RATIO_MIN = 8        // 占比规则的绝对下限，避免短句误报

    private const val TAG_START = 0xE0000
    private const val TAG_END = 0xE007F

    /** 体检报告 */
    data class Report(
        val removed: Int = 0,
        val bomb: Boolean = false,
        val before: Int = 0,
        val after: Int = 0,
        val kinds: List<String> = emptyList(),
    ) {
        val changed: Boolean get() = removed > 0
    }

    private fun isTagCodePoint(cp: Int) = cp in TAG_START..TAG_END

    private fun isOtherFormat(cp: Int): Boolean =
        Character.getType(cp) == Character.FORMAT.toInt()

    private data class Tally(var always: Int = 0, var cond: Int = 0,
                             var tags: Int = 0, var other: Int = 0) {
        val total: Int get() = always + cond + tags + other
    }

    private fun tally(text: String): Tally {
        val t = Tally()
        var i = 0
        while (i < text.length) {
            val cp = Character.codePointAt(text, i)
            val cc = Character.charCount(cp)
            when {
                cc == 1 && text[i] in ALWAYS_STRIP -> t.always++
                cc == 1 && text[i] in CONDITIONAL -> t.cond++
                isTagCodePoint(cp) -> t.tags++
                isOtherFormat(cp) -> t.other++
            }
            i += cc
        }
        return t
    }

    /** 是不是炸弹（不改动文本，只判定） */
    fun isBomb(text: String): Boolean {
        val t = tally(text)
        if (t.total == 0) return false
        val ratio = t.total.toDouble() / maxOf(text.length, 1)
        var bomb = t.total > BOMB_TOTAL ||
                (t.total >= BOMB_RATIO_MIN && ratio > BOMB_RATIO)
        // 少量 ZWJ 属于正常（e<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌moji 组合），不算炸弹
        if (t.total <= 6 && t.always == 0 && t.tags == 0 && t.other == 0 && t.cond == t.total) {
            bomb = false
        }
        return bomb
    }

    /** 只看不可见字符有多少个 */
    fun invisibleCount(text: String): Int = tally(text).total

    /**
     * 清洗文本。返回 (干净文本, 报告)。
     * 永远不抛异常；空串原样返回。
     */
    fun sanitize(text: String, keepLegitZwj: Boolean = true): Pair<String, Report> {
        if (text.isEmpty()) return text to Report()
        // NBSP 先规整成普通空格：它的类别是 Zs（分隔符）不是 Cf，不先处理后面扫不到
        val src = if (text.contains('\u00A0')) text.replace('\u00A0', ' ') else text

        val t = tally(src)
        if (t.total == 0) return src to Report()

        val ratio = t.total.toDouble() / maxOf(src.length, 1)
        var bomb = t.total > BOMB_TOTAL ||
                (t.total >= BOMB_RATIO_MIN && ratio > BOMB_RATIO)
        if (t.total <= 6 && t.always == 0 && t.tags == 0 && t.other == 0 && t.cond == t.total) {
            bomb = false
        }
        val stripCond = bomb || !keepLegitZwj

        val sb = StringBuilder(src.length)
        var removed = 0
        var i = 0
        while (i < src.length) {
            val cp = Character.codePointAt(src, i)
            val cc = Character.charCount(cp)
            val drop = when {
                cc == 1 && src[i] in ALWAYS_STRIP -> true
                isTagCodePoint(cp) -> true
                cc == 1 && src[i] in CONDITIONAL -> stripCond
                isOtherFormat(cp) -> true
                else -> false
            }
            if (drop) removed++ else sb.appendRange(src, i, i + cc)
            i += cc
        }

        val clean = sb.toString()
        val kinds = ArrayList<String>(4)
        if (t.always > 0) kinds.add("零宽/方向控制符 ${t.always} 个")
        if (t.cond > 0) kinds.add("零宽连接符 ${t.cond} 个")
        if (t.tags > 0) kinds.add("隐藏标签字符 ${t.tags} 个")
        if (t.other > 0) kinds.add("其他不可见格式符 ${t.other} 个")

        return clean to Report(
            removed = removed, bomb = bomb,
            before = src.length, after = clean.length, kinds = kinds,
        )
    }

    /** 把报告转成给用户看的一句话；没删东西返回空串（不打扰用户） */
    fun summary(r: Report?): String {
        if (r == null || !r.changed) return ""
        return if (r.bomb) {
            "⚠ 检测到零宽字符炸弹：已剔除 ${r.removed} 个不可见字符" +
                    "（原文 ${r.before} 字 → ${r.after} 字）。这类字符看不见，却会白烧 token 并可能卡住界面。"
        } else {
            "（已顺带清理 ${r.removed} 个不可见字符：${r.kinds.joinToString("、").ifEmpty { "不可见字符" }}）"
        }
    }
}
