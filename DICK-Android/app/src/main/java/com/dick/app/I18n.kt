package com.dick.app

import java.util.Locale

/**
 * Android 三语界面：中文 / English / 日本語
 *
 * **文案的唯一真相是 `lang/strings.json`**（仓库根目录）：
 *   · 这个文件不再内联 EN / JA 两张 map —— 它们和桌面 i18n.py、web/index.html 的 JS 表
 *     原来是各写一份，三份迟早对不上；
 *   · 三张表由 `tools/gen_i18n.py` 生成到 [I18nStrings]（生成物，别手改），本文件只做：取表、回退、判定语言。
 *
 * 约定（与桌面 i18n.py 一致）：
 *  · `t()` 缺键**回退到调用点传的中文原串**，绝不显示 key 名；中文优先用调用点的串
 *    （老行为不变），调用点没给才用表里的 zh；
 *  · `detect()` 中文系统 → zh、日文系统 → ja、英文系统 → en、**认不出 → zh**；
 *  · 专有名词（DICK / CODEX / GAL / UTAU / DeepSeek / API Key / URL…）保留原文。
 */
object I18n {
    var lang = "zh"

    val LANGS = listOf("zh", "en", "ja")
    val LANG_NAMES = mapOf("zh" to "中文", "en" to "English", "ja" to "日本語")

    /** 当前语言的自称（设置里那个按钮/选择器显示用） */
    fun langName(l: String = lang): String = LANG_NAMES[l] ?: LANG_NAMES["zh"]!!

    /** 三张表的查表口（生成物；键集合三者完全一致，见 tools/gen_i18n.py --check） */
    private val TABLES = mapOf(
        "zh" to I18nStrings.ZH,
        "en" to I18nStrings.EN,
        "ja" to I18nStrings.JA,
    )

    /** 未翻译的键回退到中文原串，绝不显示 key 名 */
    fun t(key: String, zh: String): String {
        if (lang == "zh") {
            // 中文：调用点给的原串优先（老行为<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌不变）；调用点没给才用表里的 zh
            return if (zh.isNotBlank()) zh else (I18nStrings.ZH[key] ?: "")
        }
        return TABLES[lang]?.get(key) ?: zh
    }

    /** 首启判定：中文系统 → zh、日文系统 → ja、英文系统 → en、认不出 → zh（保持老行为） */
    fun detect(): String {
        val code = Locale.getDefault().language.lowercase(Locale.ROOT)
        return when {
            code.startsWith("ja") -> "ja"
            code.startsWith("en") -> "en"
            code.startsWith("zh") -> "zh"
            else -> "zh"
        }
    }

    /** 配置里存的值是否合法（不合法就当 zh，与 set_lang 同规矩） */
    fun normalize(l: String?): String = if (l != null && LANGS.contains(l)) l else "zh"

    fun budgetLabel(tokens: Int): String {
        val num = if (tokens == 0) t("budget_unlimited", "不限") else (tokens / 1024).toString() + "K"
        return t("budget_prefix", "预算：") + num
    }
}
