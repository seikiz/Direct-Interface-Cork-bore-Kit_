package com.dick.app

import com.dick.core.J
import com.dick.core.JsonS

/**
 * 卡片**解析层**（角色卡 / 世界卡 JSON → 可直接排版的模型）—— 安卓端。
 *
 * 背景（用户反馈）：「角色卡外显应该是结构化，而不是像现在一样像个代码，穿帮了」。
 * 原来工坊里是一句 `Text(wsPreview)`，把**整份 JSON 原样**画出来：大括号、引号、`\n` 转义。
 *
 * 分工（两端同一套语义）：
 *   · **字段清单 / 分区顺序 / 标签**只认生成物 [CardFields]（唯一真相
 *     `design/card_fields.json`，由 `tools/gen_card_fields.py` 生成；网页端是
 *     `web/card_fields.js`，同一个生成器产出 —— 两端不会长出两张不同的脸）；
 *   · **标签文案**只认 [I18n]（三语，真实文案在 `lang/strings.json`）；
 *   · 本文件只做「解析 → 分区 → 归并去重」，**一个控件都不画**。
 *
 * 为什么解析与排版分家（2026-12）：工坊里那个"嵌在列表下的小预览"换成了**独立详情弹窗**
 * （`ui/screens/workshop/CardDetail.kt`），详情要"全部展开 + 三块补充数据"，和原来折叠版
 * 的排版是两件事。塞进同一个函数只会变成一堆 `if`，两边都不敢改；模型留在这里，
 * 排版各归各的文件，谁坏了一眼能看出是解析还是画错了。
 *
 * 三条硬规矩（`tests/test_card_view.py` + `tests/test_card_detail_android.py` 盯着）：
 *   ① 不把 JSON 字符串化显示（本文件没有 `JsonS.stringify`）；
 *   ② 不是 JSON / 解析失败 → 模型只有一段原文，渲染器按**正文**排版（不是等宽代码块）；
 *   ③ 未知键一律进「其它信息」两列；数组/对象只报「列表 · N 项 / 对象 · N 项」，不打花括号。
 */

/** 三种展示方式（与 `design/card_fields.json` 的 mode 一一对应，没有 json 这一档）。 */
internal const val MODE_BODY = "body"
internal const val MODE_KV = "kv"
internal const val MODE_LIST = "list"

/** 空行分段：一个换行 + 若干空格/制表 + 至少一个换行。 */
private val PARA_SPLIT = Regex("\n[ \t]*\n+")
private val SPACE_RUN = Regex("\\s+")
private val NEWLINE_RUN = Regex("\\s*\\n\\s*")

/** 一个正文块（label 为空 = 没有字段标签，例如原文兜底）。 */
internal class CardBodyBlock(val label: String, val paras: List<String>)

/** 一个列表块（世界卡的 rules[] / narrative_tips[] 这类）。 */
internal class CardListBlock(val label: String, val items: List<String>)

/** 渲染用的一条分区（blocks 与 rows 只会有一边非空）。 */
internal class CardSectionView(
    val id: String,
    val mode: String,
    val blocks: List<Any>,
    val rows: List<Pair<String, String>>,
)

/** 一张卡的渲染模型（纯数据，不碰 Compose）。 */
internal class CardModel(
    val title: String,
    val sections: List<CardSectionView>,
    val other: List<Pair<String, String>>,
)

// ============================================================
//  取值 / 归一（与 web/js/screens/ws.js 的 wsCard* 一一对应）
// ============================================================
/** 去掉字面 `\n` / `\t` 转义（卡片把换行存成两个字符），再掐掉行尾空白。 */
private fun cfNorm(v: String): String = v
    .replace("\\r\\n", "\n")
    .replace("\\n", "\n")
    .replace("\\t", "\t")
    .replace(Regex("[ \t]+\n"), "\n")
    .trimEnd()

/** 正文 → 段落（空行分段；段内单换行保留）。 */
private fun cfParas(text: String): List<String> = cfNorm(text)
    .split(PARA_SPLIT)
    .map { it.trim() }
    .filter { it.isNotEmpty() }

/** 标量 → 文本；容器（数组/对象）返回 null（交给 [cfSummary]，绝不打花括号）。 */
internal fun cfScalar(v: J?): String? = when (v) {
    null, is J.Null -> null
    is J.Str -> cfNorm(v.v)
    is J.Num -> if (v.raw.isNotBlank()) v.raw else {
        val d = v.v
        if (d == Math.floor(d) && !d.isInfinite()) d.toLong().toString() else d.toString()
    }
    is J.Bool -> if (v.v) I18n.t("card_yes", "是") else I18n.t("card_no", "否")
    else -> null
}

/** 容器 → 「列表 · N 项」/「对象 · N 项」（**不是** JSON 片段）。 */
internal fun cfSummary(v: J?): String = when (v) {
    is J.Arr -> I18n.t("card_count_list", "列表 · %d 项").replace("%d", v.items.size.toString())
    is J.Obj -> I18n.t("card_count_obj", "对象 · %d 项").replace("%d", v.fields.size.toString())
    else -> ""
}

/** 压成一行（两列视图与列表项用）。max=0 表示不截断。 */
internal fun cfOneLine(s: String, max: Int): String {
    val t = s.replace(NEWLINE_RUN, " ").replace(SPACE_RUN, " ")
    return if (max > 0 && t.length > max) t.take(max) + "…" else t
}

/** 字符串里包着 JSON 的情况（世界卡包的 params.space 就是这么存的）→ 解出容器。
 *  不这么做就得把 {"places":[…]} 原样画在界面上 —— 那正是用户说的「像个代码，穿帮了」。 */
private fun cfJsonOf(text: String): J? {
    val t = text.trim()
    if (t.isEmpty() || (t[0] != '{' && t[0] != '[')) return null
    val v = try {
        JsonS.parse(t)
    } catch (e: Exception) {
        return null
    }
    return if (v is J.Obj || v is J.Arr) v else null
}

/** 界面值：标量照抄（压成一行）；容器报计数；字符串里包的 JSON 也按容器报计数。 */
internal fun cfValueText(v: J?, max: Int): String {
    val sc = cfScalar(v) ?: return cfSummary(v)
    val inner = cfJsonOf(sc)
    if (inner != null) return cfSummary(inner)
    return cfOneLine(sc, max)
}

/** 点号路径取值：`params.era` → root.params.era（世界卡的年代/空间住在 params 里）。 */
private fun cfGet(root: J.Obj, path: String): J? {
    var cur: J = root
    for (part in path.split(".")) {
        val o = cur as? J.Obj ?: return null
        cur = o.fields[part] ?: return null
    }
    return cur
}

/** 这个键是不是「原样数据槽」（整份原始卡 / 对话树 / 世界书元数据）：不进分区也不进其它信息。 */
internal fun cfHidden(key: String): Boolean {
    if (CardFields.HIDDEN_KEYS.contains(key)) return true
    return CardFields.HIDDEN_PREFIXES.any { key.startsWith(it) }
}

// ============================================================
//  模型：卡 JSON → 分区
// ============================================================
private class Collected(val blocks: List<Any>, val rows: List<Pair<String, String>>)

/** 空白压平（只用来判重：同一段话在别的分区已经显示过，就不要再显示一遍）。 */
private fun cfFlat(s: String): String = s.replace(SPACE_RUN, "")

/** 这段是不是已经显示过的某段正文的子串（DICK 卡把同一段话既存进 system_prompt 又存进单独字段）。 */
private fun cfSeen(seen: List<String>, text: String): Boolean {
    val flat = cfFlat(text)
    return seen.any { it.contains(flat) }
}

/** 一个分区：把同义键收进同一个块（body 按段、kv 两列、list 逐条）。 */
private fun cfCollect(root: J.Obj, sec: CardSection, seenBody: MutableList<String>): Collected? {
    val blocks = mutableListOf<Any>()
    val rows = mutableListOf<Pair<String, String>>()
    val seenLabels = mutableSetOf<String>()
    val seenText = mutableSetOf<String>()
    for (path in sec.keys) {
        val v = cfGet(root, path) ?: continue
        when (sec.mode) {
            MODE_BODY -> {
                val text = cfScalar(v) ?: continue
                if (text.isBlank()) continue
                // system_prompt 与 description 同文时只留一份（导入卡常把简介抄进人设）
                if (!seenText.add(text)) continue
                if (cfFlat(text).length >= 12 && cfSeen(seenBody, text)) continue
                seenBody.add(cfFlat(text))
                blocks.add(CardBodyBlock(CardFields.fieldLabel(path), cfParas(text)))
            }
            MODE_LIST -> {
                val arr = (v as? J.Arr)?.items ?: listOf(v)
                val items = arr.map { cfValueText(it, 0) }.filter { it.isNotBlank() }
                if (items.isNotEmpty()) blocks.add(CardListBlock(CardFields.fieldLabel(path), items))
            }
            else -> {
                val value = cfValueText(v, CardFields.KV_VALUE_CHARS)
                if (value.isBlank()) continue
                val label = CardFields.fieldLabel(path).ifBlank { path }
                if (!seenLabels.add(label)) continue   // params.era 与 era 同时存在时不留两行
                rows.add(label to value)
            }
        }
    }
    return if (blocks.isEmpty() && rows.isEmpty()) null else Collected(blocks, rows)
}

/** 把一份卡 JSON 变成模型。 */
private fun cfModel(root: J.Obj, fileName: String): CardModel {
    var title = ""
    for (k in CardFields.TITLE_KEYS) {
        val tv = cfScalar(cfGet(root, k))
        if (!tv.isNullOrBlank()) {
            title = cfOneLine(tv, 80)
            break
        }
    }
    if (title.isBlank()) title = fileName.removeSuffix(".json")

    // 标题候选键算「已认领」：标题已经画在最上面了，再在「其它信息」里列一遍「name: xxx」是噪声
    val claimed = mutableSetOf<String>()
    claimed.addAll(CardFields.TITLE_KEYS)
    val sections = mutableListOf<CardSectionView>()
    val seenBody = mutableListOf<String>()      // 已显示的正文（空白压平），用来挡重复内容
    for (sec in CardFields.SECTIONS) {
        val got = cfCollect(root, sec, seenBody) ?: continue
        claimed.addAll(sec.keys)
        sections.add(CardSectionView(sec.id, sec.mode, got.blocks, got.rows))
    }

    // 长值重复正文时不再列一遍（旧版卡把旧的 system_prompt 存在 legacy 里，跟前文一模一样）
    fun repeatedInBody(value: String): Boolean {
        val flat = cfFlat(value)
        if (flat.length < 20) return false
        return seenBody.any { it.contains(flat) }
    }

    val other = mutableListOf<Pair<String, String>>()
    for ((k, v) in root.fields) {
        if (cfHidden(k) || claimed.contains(k)) continue
        if (v is J.Obj) {
            // 对象下钻一层：世界卡的 params.tech_level 这类要看得见，不能压成「对象 · 8 项」。
            // 子项全被上面的分区认领了（或全是隐藏槽）→ 这一行整个不要，别留一行纯计数。
            for ((k2, v2) in v.fields) {
                val path = "$k.$k2"
                if (cfHidden(k2) || claimed.contains(path)) continue
                val val2 = cfValueText(v2, CardFields.KV_VALUE_CHARS)
                if (val2.isBlank() || repeatedInBody(val2)) continue
                other.add(CardFields.fieldLabel(path).ifBlank { path } to val2)
            }
            continue
        }
        val value = cfValueText(v, CardFields.KV_VALUE_CHARS)
        if (value.isBlank() || repeatedInBody(value)) continue
        other.add(CardFields.fieldLabel(k).ifBlank { k } to value)
    }
    return CardModel(title, sections, other)
}

/** 兜底模型：不是 JSON / 解析失败 → 原文按正文排版（不是等宽代码块）。 */
private fun cfRawModel(text: String, fileName: String): CardModel {
    val body = if (text.length > CardFields.MAX_TEXT_CHARS) {
        text.take(CardFields.MAX_TEXT_CHARS) + "…"
    } else text
    return CardModel(
        fileName.removeSuffix(".json"),
        listOf(CardSectionView("raw", MODE_BODY, listOf(CardBodyBlock("", cfParas(body))), emptyList())),
        emptyList(),
    )
}

/** 原文 → 根对象；空串 / 解析失败 / 顶层不是对象 → null（渲染器据此走原文兜底）。 */
internal fun cfRoot(text: String): J.Obj? {
    val src = text.trim()
    if (src.isEmpty() || (src[0] != '{' && src[0] != '[')) return null
    return try {
        JsonS.parse(src) as? J.Obj
    } catch (e: Exception) {
        null
    }
}

/** 入口：原文 + 文件名 → 模型（解析失败就按原文显示）。 */
internal fun cfParse(text: String, fileName: String): CardModel {
    val src = text.trim()
    if (src.isEmpty()) return cfRawModel("", fileName)
    val obj = cfRoot(src)
    return if (obj != null) cfModel(obj, fileName) else cfRawModel(src, fileName)
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌
