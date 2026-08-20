package com.dick.app

import java.util.Locale

/** Android 中英双语（英文系统首次启动自动切英文，设置里可手动切换） */
object I18n {
    var lang = "zh"

    private val EN = mapOf(
        "group_other" to "Other",
        "item_settings" to "Settings",
        "item_roles_worlds" to "Roles & Worlds",
        "item_roles" to "Roles",
        "item_worlds" to "Worlds",
        "item_share" to "Share Chat Log",
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

    fun t(key: String, zh: String): String = if (lang == "en") (EN[key] ?: zh) else zh

    fun detect(): String = if (Locale.getDefault().language == "en") "en" else "zh"

    fun budgetLabel(tokens: Int): String {
        val num = if (tokens == 0) t("budget_unlimited", "不限") else (tokens / 1024).toString() + "K"
        return if (lang == "en") "Budget: " + num else "预算：" + num
    }
}
