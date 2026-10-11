package com.dick.app

import java.util.Locale

/**
 * Android 三语界面：中文 / English / 日本語
 *
 * （原来只有中/英两档；日文只存在于 TTS 与 /jp 翻译里，界面没有日文。）
 *
 * 约定：
 *  · `EN` 与 `JA` 的**键集合完全一致**（tests/test_i18n_langs.py 会比对）；
 *  · `t()` 未翻译的键**回退到中文原串**，绝不显示 key 名；
 *  · `detect()` 中文系统 → zh、日文系统 → ja、英文系统 → en、**认不出 → zh**（保持老行为）；
 *  · 专有名词（DICK / CODEX / GAL / UTAU / DeepSeek / API Key / URL…）保留原文。
 */
object I18n {
    var lang = "zh"

    val LANGS = listOf("zh", "en", "ja")
    val LANG_NAMES = mapOf("zh" to "中文", "en" to "English", "ja" to "日本語")

    /** 当前语言的自称（设置里那个按钮/选择器显示用） */
    fun langName(l: String = lang): String = LANG_NAMES[l] ?: LANG_NAMES["zh"]!!

    private val EN = mapOf(
        "group_other" to "Other",
        "item_settings" to "Settings",
        "item_roles_worlds" to "Roles & Worlds",
        "item_roles" to "Roles",
        "item_worlds" to "Worlds",
        "item_share" to "Share Chat Log",
        "item_api" to "🔑 API Settings",
        "input_label" to "Message (start with / for commands)",
        "btn_send" to "Send",
        "btn_remove" to "✕ Remove",
        "img_selected" to "Image attached",
        "you" to "You",
        "system" to "System",
        "unknown_cmd" to "Unknown command. Try /dice for help.",
        "vision_fail" to "⚠️ Image recognition failed (rate limit or network). Try again later.",
        "dlg_settings" to "DICK · Settings",
        "lbl_model" to "Model",
        "lbl_baseurl" to "Provider Base URL",
        "lbl_preset" to "Preset: ",
        "budget_unlimited" to "Unlimited",
        "lbl_persona" to "Player Persona (name/background, optional)",
        "chk_auto" to "Auto follow-up in group chat",
        "chk_tts" to "Read AI replies aloud (system TTS)",
        "lbl_plugins" to "Plugins",
        "lbl_theme" to "Theme: ",
        "lbl_accent" to "Accent: ",
        "btn_save" to "Save",
        "btn_cancel" to "Cancel",
        "btn_buy" to "🔑 Official site (sign up / top up)",
        "lbl_provider" to "Provider",
        "lbl_key_free" to "API Key (free, can be blank)",
        "btn_workshop" to "🧰 Workshop",
        "ws_local" to "📂 Local",
        "ws_online" to "🌐 Online",
        "ws_server" to "Server URL",
        "ws_key" to "Key (optional)",
        "ws_save_conn" to "💾 Save",
        "ws_test" to "🔌 Test",
        "ws_search" to "Search",
        "ws_download" to "⬇️ Download",
        "ws_like" to "❤️ Like",
        "ws_upload" to "📤 Upload",
        "ws_delete" to "🗑️ Delete",
        "ws_export" to "📤 Export",
        "dlg_roles" to "Select Roles (multi-select = group chat)",
        "btn_new_role" to "New Role",
        "btn_done" to "Done",
        "lbl_name" to "Name",
        "lbl_prompt" to "Personality / background",
        "dlg_worlds" to "Select Worlds (multi-select = parallel worlds)",
        "btn_delete" to "Delete",
        "lang_title" to "Language",
        "qc_image" to "Image",
        // 玩家角色卡 / 世界参数（原来只在调<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌用点有中文兜底，英文模式下会显示中文）
        "btn_persona_card" to "Player Card",
        "btn_avatar_persona" to "Player Avatar",
        "wm_params" to "World parameters (physics system etc.)",
        // 角色卡导入导出
        "btn_import_card" to "📥 Import",
        "btn_export_json" to "⬇️ JSON",
        "btn_export_png" to "🖼️ PNG",
        "card_import_fail" to "⚠️ Unrecognized character card format",
        "card_import_ok" to "Imported character: ",
        "card_export_fail" to "⚠️ Export failed",
        // 世界书条目
        "btn_new_world" to "New World",
        "btn_edit" to "✏️",
        "dlg_world_edit" to "Edit World Card",
        "lbl_world_name" to "Name",
        "lbl_world_desc" to "Description",
        "lbl_world_rules" to "Rules (one per line)",
        "world_entries" to "World Book Entries",
        "entry_keywords" to "Keywords (comma separated)",
        "entry_content" to "Content",
        "entry_match" to "Match",
        "entry_weight" to "Weight",
        "entry_probability" to "Prob %",
        "entry_depth" to "Depth",
        "entry_enabled" to "Enabled",
        "entry_constant" to "Constant",
        "btn_add_entry" to "＋ Add Entry",
        "entry_delete" to "✕",
        "match_any" to "any",
        "match_all" to "all",
        "match_regex" to "regex",
        // 滑条 / 编辑 / 分支
        "btn_edit_msg" to "✏️",
        "btn_regenerate" to "↻",
        "btn_branch" to "🌿",
        "branch_title" to "Switch Branch",
        "branch_none" to "No other branches",
        "edit_title" to "Edit Message",
        "edit_ai_hint" to "Edit this AI reply in place.",
        "edit_user_hint" to "Edit this message and regenerate a reply (old branch is kept).",
    )

    // 界面日语：简短体，专有名词保留原文
    private val JA = mapOf(
        "group_other" to "その他",
        "item_settings" to "設定",
        "item_roles_worlds" to "キャラとワールド",
        "item_roles" to "キャラ",
        "item_worlds" to "ワールド",
        "item_share" to "チャット履歴を共有",
        "item_api" to "🔑 API 設定",
        "input_label" to "メッセージ（/ で始めるとコマンド）",
        "btn_send" to "送信",
        "btn_remove" to "✕ 削除",
        "img_selected" to "画像を選択済み",
        "you" to "あなた",
        "system" to "システム",
        "unknown_cmd" to "不明なコマンド。/dice でヘルプ。",
        "vision_fail" to "⚠️ 画像の認識に失敗しました（制限またはネットワーク）。後でもう一度。",
        "dlg_settings" to "DICK · 設定",
        "lbl_model" to "モデル",
        "lbl_baseurl" to "プロバイダ Base URL",
        "lbl_preset" to "プリセット：",
        "budget_unlimited" to "無制限",
        "lbl_persona" to "プレイヤー設定（名前・背景、任意）",
        "chk_auto" to "グループチャットで自動応答",
        "chk_tts" to "AI の返答を読み上げ（システム TTS）",
        "lbl_plugins" to "プラグイン",
        "lbl_theme" to "テーマ： ",
        "lbl_accent" to "アクセント： ",
        "btn_save" to "保存",
        "btn_cancel" to "キャンセル",
        "btn_buy" to "🔑 公式サイト（登録 / チャージ）",
        "lbl_provider" to "プロバイダ",
        "lbl_key_free" to "API Key（無料・空欄可）",
        "btn_workshop" to "🧰 ワークショップ",
        "ws_local" to "📂 ローカル",
        "ws_online" to "🌐 オンライン",
        "ws_server" to "サーバー URL",
        "ws_key" to "Key（任意）",
        "ws_save_conn" to "💾 保存",
        "ws_test" to "🔌 テスト",
        "ws_search" to "検索",
        "ws_download" to "⬇️ ダウンロード",
        "ws_like" to "❤️ いいね",
        "ws_upload" to "📤 送信",
        "ws_delete" to "🗑️ 削除",
        "ws_export" to "📤 書き出し",
        "dlg_roles" to "キャラを選択（複数選択 = グループチャット）",
        "btn_new_role" to "新規キャラ",
        "btn_done" to "完了",
        "lbl_name" to "名前",
        "lbl_prompt" to "性格・背景",
        "dlg_worlds" to "ワールドを選択（複数選択 = 並行世界）",
        "btn_delete" to "削除",
        "lang_title" to "言語",
        "qc_image" to "画像",
        // プレイヤーカード / ワールドパラメータ
        "btn_persona_card" to "プレイヤーカード",
        "btn_avatar_persona" to "プレイヤーアイコン",
        "wm_params" to "ワールドパラメータ（物理法則など）",
        // キャラカードの読み込み / 書き出し
        "btn_import_card" to "📥 読み込み",
        "btn_export_json" to "⬇️ JSON",
        "btn_export_png" to "🖼️ PNG",
        "card_import_fail" to "⚠️ 認識できないキャラカード形式",
        "card_import_ok" to "キャラを読み込みました：",
        "card_export_fail" to "⚠️ 書き出しに失敗",
        // ワールドブック項目
        "btn_new_world" to "新規ワールド",
        "btn_edit" to "✏️",
        "dlg_world_edit" to "ワールドカードを編集",
        "lbl_world_name" to "名前",
        "lbl_world_desc" to "説明",
        "lbl_world_rules" to "ルール（1 行に 1 つ）",
        "world_entries" to "ワールドブック項目",
        "entry_keywords" to "キーワード（カンマ区切り）",
        "entry_content" to "内容",
        "entry_match" to "一致",
        "entry_weight" to "重み",
        "entry_probability" to "確率 %",
        "entry_depth" to "深度",
        "entry_enabled" to "有効",
        "entry_constant" to "常時",
        "btn_add_entry" to "＋ 項目を追加",
        "entry_delete" to "✕",
        "match_any" to "いずれか",
        "match_all" to "すべて",
        "match_regex" to "正規表現",
        // スワイプ / 編集 / ブランチ
        "btn_edit_msg" to "✏️",
        "btn_regenerate" to "↻",
        "btn_branch" to "🌿",
        "branch_title" to "ブランチ切替",
        "branch_none" to "他のブランチはありません",
        "edit_title" to "メッセージを編集",
        "edit_ai_hint" to "この AI の返答をその場で編集します。",
        "edit_user_hint" to "メッセージを編集して返答を再生成します（元のブランチは保持）。",
    )

    private val TABLES = mapOf("en" to EN, "ja" to JA)

    /** 未翻译的键回退到中文原串，绝不显示 key 名 */
    fun t(key: String, zh: String): String {
        if (lang == "zh") return zh
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
        return when (lang) {
            "en" -> "Budget: " + num
            "ja" -> "予算： " + num
            else -> "预算：" + num
        }
    }
}
