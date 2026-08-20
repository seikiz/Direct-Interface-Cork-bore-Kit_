# -*- coding: utf-8 -*-
"""i18n.py - 中英双语界面（英文系统首次启动自动切英文，字体设置里可手动切换）"""

_LANG = "zh"

_EN = {
    "btn_collapse": "◀ Collapse Sidebar",
    "btn_expand": "▶ Expand Sidebar",
    "lbl_archives": "📂 Archives",
    "btn_new_role": "➕ New Role",
    "btn_del_role": "🗑️ Delete Role",
    "btn_exp_role": "📤 Export Role",
    "btn_imp_role": "📥 Import Role",
    "btn_open_saves": "📂 Open Saves Folder",
    "lbl_worlds": "🌍 Worlds (multi-select = parallel worlds)",
    "btn_new_world": "➕ New World",
    "btn_del_world": "🗑️ Delete World",
    "btn_exp_world": "📤 Export World",
    "btn_imp_world": "📥 Import World",
    "btn_open_worlds": "📂 Open Worlds Folder",
    "lbl_persona": "🧑 Player Persona",
    "btn_new": "➕ New",
    "btn_del": "🗑️ Delete",
    "btn_enable": "✅ Enable",
    "btn_disable": "❌ Disable",
    "lbl_apikey": "Enter your API Key:",
    "lbl_provider": "Provider:",
    "lbl_model": "Model:",
    "lbl_preset": "Preset:",
    "btn_manage_preset": "✏️ Manage",
    "lbl_budget": "🧮 Budget:",
    "chk_rolling": "📜 Rolling Summary",
    "btn_start": "✅ Start Chat",
    "menu_tools": "🛠️ Tools",
    "btn_buy_api": "💰 Buy API",
    "input_placeholder": "Type a message... (use @name to target a speaker)",
    "btn_send": "Send",
    "btn_retry": "🔄 Retry",
    "btn_edit_last": "✏️ Edit Last",
    "hint_enter": "💡 Press Enter to send; use @name to target a speaker in group chat",
    "chk_auto": "🤖 Auto Reply (other roles follow up in group chat)",
    "loading": "⏳ Typing...",
    "welcome1": "👋 Welcome to Direct-Interface Cork-bore Kit v2.0!",
    "welcome2": "Group chat: type @name message to target a speaker.",
    "welcome3": "Hold Ctrl and click role cards to activate multiple roles.",
    "lbl_font": "Font:",
    "lbl_size": "Size:",
    "dlg_welcome_title": "Welcome",
    "dlg_subtitle": "Unlimited AI Interaction Studio",
    "feat1": "🎭 Create any character (personality, background, speech style)",
    "feat2": "🌍 Build any world (rules, keywords, scenes)",
    "feat3": "🔄 Switch freely among 17 AI providers",
    "feat4": "🧩 Extend infinitely with plugins",
    "lbl_quickstart": "🚀 Quick Start",
    "qs1": "① Click Buy API to get a DeepSeek API Key",
    "qs2": "② Paste the Key → click Start Chat",
    "qs3": "③ Pick a role on the left → start talking",
    "btn_get_started": "Get Started",
    "lang_title": "Language",
    "lang_changed": "Language switched. Restart the app for the change to take full effect.",
    "status_roles_prefix": "Active roles: ",
    "roles_none": "none",
    "chat_empty": "(No conversation yet)",
    "sec_cards": "Roles & Worlds",
    "btn_settings": "⚙️ Settings",
    "dlg_settings_title": "Settings",
    "lbl_language": "Language",
    "btn_lang_switch": "Switch language",
    "lbl_theme_row": "Theme",
    "btn_theme": "Open Theme Center",
    "hint_font": "Font and size are at the bottom of the right panel",
    "btn_close": "Close",
    "theme_unavailable": "Theme center is unavailable (Modern UI plugin not loaded)",
    "btn_avatar": "🖼️ Avatar",
    "btn_avatar_persona": "🧑 Player Avatar",
    "pick_avatar_title": "Select avatar image",
    "pick_avatar_ft": "Image files",
    "pick_role_first": "Select a role in the archive list first",
    "success": "Success",
    "hint": "Info",
    "auto_speaking": " is typing...",
}


def set_lang(lang):
    global _LANG
    _LANG = lang if lang in ("zh", "en") else "zh"


def lang():
    return _LANG


def t(key, zh):
    if _LANG != "en":
        return zh
    return _EN.get(key, zh)


def tokens_label(n):
    if _LANG == "en":
        return "Total tokens: " + str(n)
    return "总消耗: " + str(n) + " tokens"


def roles_label(zh_text, count):
    """count=0 时显示无角色；否则英文前缀 + 中文角色名列表"""
    if _LANG != "en":
        return zh_text
    if count == 0:
        return _EN["status_roles_prefix"] + _EN["roles_none"]
    return _EN["status_roles_prefix"] + zh_text.replace("当前角色：", "")


def detect_english_system():
    """英文 Windows（UI 语言 0x09xx）返回 True"""
    try:
        import ctypes
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return (lid & 0x3FF) == 0x09
    except Exception:
        return False
