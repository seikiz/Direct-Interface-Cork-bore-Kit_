// 生成物：由 tools/gen_card_fields.py 从 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌design/card_fields.json 生成，别手改。
//   改分区/字段/折叠阈值：改 design/card_fields.json，再跑一次生成器。
//   标签文案在 lang/strings.json（本文件里的中文只是 I18n.t 的调用点默认值）。

package com.dick.app

/** 一个卡片分区：id + 展示方式（body/kv/list）+ 这个分区收哪些键（顺序即渲染顺序）。 */
data class CardSection(
    val id: String,
    val mode: String,
    val keys: List<String>,
)

/**
 * 卡片外显字段表（唯一真相 design/card_fields.json 的生成物）。
 * 网页端是 web/card_fields.js —— 分区 / 顺序 / 折叠阈值 / 隐藏槽逐字一致（--check 盯着）。
 */
object CardFields {
    const val VERSION = 1

    /** 正文超过这么多行就折叠（网页端读的是同一个数） */
    const val COLLAPSE_LINES = 8

    /** 两列视图里字符串值的截断长度 */
    const val KV_VALUE_CHARS = 120

    /** 正文分区单段最长字数 */
    const val MAX_TEXT_CHARS = 4000

    /** 标题候选键（按顺序取第一个有非空标量值的） */
    val TITLE_KEYS: List<String> = listOf("name", "char_name", "character_name", "title")

    /** 分区（顺序即渲染顺序） */
    val SECTIONS: List<CardSection> = listOf(
        CardSection("setting", "body", listOf("system_prompt", "prompt", "description", "background", "scenario", "setting", "world_setting", "context")),
        CardSection("persona", "body", listOf("personality", "性格", "个性", "appearance", "外貌", "外表", "speech", "speech_style", "语气")),
        CardSection("greeting", "body", listOf("greeting", "first_mes", "opening", "first_message", "initial_scene", "alternate_greetings")),
        CardSection("profile", "kv", listOf("age", "gender", "occupation", "race", "species", "height", "birthday", "author", "version", "tags", "created_at", "time_period")),
        CardSection("era", "kv", listOf("params.era", "params.era_kind", "params.space", "params.region", "era", "era_kind", "space", "region")),
        CardSection("rules", "list", listOf("rules", "narrative_tips", "factions", "geography", "example_dialogues")),
    )

    /** 兜底分区：没被上面任何分区认领的键都进这里（两列「键: 值」，**不显示 JSON**） */
    val OTHER: CardSection = CardSection("other", "kv", emptyList())

    /** 键 → 字段标签的 i18n 键（文案在 lang/strings.json） */
    val FIELD_LABEL_KEYS: Map<String, String> = mapOf(
        "system_prompt" to "card_f_system_prompt",
        "prompt" to "card_f_system_prompt",
        "description" to "card_f_system_prompt",
        "background" to "card_f_background",
        "scenario" to "card_f_background",
        "notes" to "card_f_notes",
        "mes_example" to "card_f_mes_example",
        "personality" to "card_f_personality",
        "性格" to "card_f_personality",
        "个性" to "card_f_personality",
        "appearance" to "card_f_appearance",
        "外貌" to "card_f_appearance",
        "外表" to "card_f_appearance",
        "speech" to "card_f_speech",
        "speech_style" to "card_f_speech",
        "语气" to "card_f_speech",
        "age" to "card_f_age",
        "gender" to "card_f_gender",
        "occupation" to "card_f_occupation",
        "race" to "card_f_race",
        "species" to "card_f_race",
        "height" to "card_f_height",
        "birthday" to "card_f_birthday",
        "author" to "card_f_author",
        "version" to "card_f_version",
        "tags" to "card_f_tags",
        "created_at" to "card_f_created_at",
        "time_period" to "card_f_time_period",
        "params.era" to "card_f_era",
        "era" to "card_f_era",
        "params.era_kind" to "card_f_era_kind",
        "era_kind" to "card_f_era_kind",
        "params.space" to "card_f_space",
        "space" to "card_f_space",
        "params.region" to "card_f_region",
        "region" to "card_f_region",
    )

    /** 原样数据槽：不显示（整份原始卡 / 对话树 / 世界书元数据） */
    val HIDDEN_KEYS: Set<String> = setOf("card_data", "history_tree", "extensions", "world_entries")

    /** 这些前缀开头的键一律不显示（_meta / _tree_* 等程序槽） */
    val HIDDEN_PREFIXES: List<String> = listOf("_")

    /** 分区标签（三语走 I18n；键在这里展开成字面调用，扫描器才看得见） */
    fun sectionLabel(id: String): String = when (id) {
        "setting" -> I18n.t("card_sec_setting", "角色设定")
        "persona" -> I18n.t("card_sec_persona", "性格 / 外貌")
        "greeting" -> I18n.t("card_sec_greeting", "开场白")
        "profile" -> I18n.t("card_sec_profile", "基本信息")
        "era" -> I18n.t("card_sec_era", "年代 / 空间")
        "rules" -> I18n.t("card_sec_rules", "规则")
        "other" -> I18n.t("card_sec_other", "其它信息")
        else -> ""
    }

    /** 字段标签；没登记的键返回空串（渲染器退回显示键名本身） */
    fun fieldLabel(key: String): String = when (key) {
        "system_prompt" -> I18n.t("card_f_system_prompt", "设定正文")
        "prompt" -> I18n.t("card_f_system_prompt", "设定正文")
        "description" -> I18n.t("card_f_system_prompt", "设定正文")
        "background" -> I18n.t("card_f_background", "背景")
        "scenario" -> I18n.t("card_f_background", "背景")
        "notes" -> I18n.t("card_f_notes", "备注")
        "mes_example" -> I18n.t("card_f_mes_example", "对话示例")
        "personality" -> I18n.t("card_f_personality", "性格")
        "性格" -> I18n.t("card_f_personality", "性格")
        "个性" -> I18n.t("card_f_personality", "性格")
        "appearance" -> I18n.t("card_f_appearance", "外貌")
        "外貌" -> I18n.t("card_f_appearance", "外貌")
        "外表" -> I18n.t("card_f_appearance", "外貌")
        "speech" -> I18n.t("card_f_speech", "说话风格")
        "speech_style" -> I18n.t("card_f_speech", "说话风格")
        "语气" -> I18n.t("card_f_speech", "说话风格")
        "age" -> I18n.t("card_f_age", "年龄")
        "gender" -> I18n.t("card_f_gender", "性别")
        "occupation" -> I18n.t("card_f_occupation", "职业")
        "race" -> I18n.t("card_f_race", "种族")
        "species" -> I18n.t("card_f_race", "种族")
        "height" -> I18n.t("card_f_height", "身高")
        "birthday" -> I18n.t("card_f_birthday", "生日")
        "author" -> I18n.t("card_f_author", "作者")
        "version" -> I18n.t("card_f_version", "版本")
        "tags" -> I18n.t("card_f_tags", "标签")
        "created_at" -> I18n.t("card_f_created_at", "创建时间")
        "time_period" -> I18n.t("card_f_time_period", "时间")
        "params.era" -> I18n.t("card_f_era", "年代")
        "era" -> I18n.t("card_f_era", "年代")
        "params.era_kind" -> I18n.t("card_f_era_kind", "年代类型")
        "era_kind" -> I18n.t("card_f_era_kind", "年代类型")
        "params.space" -> I18n.t("card_f_space", "空间")
        "space" -> I18n.t("card_f_space", "空间")
        "params.region" -> I18n.t("card_f_region", "地区")
        "region" -> I18n.t("card_f_region", "地区")
        else -> ""
    }
}
