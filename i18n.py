# -*- coding: utf-8 -*-
"""i18n.py - 三语界面：中文 / English / 日本語

（原来只有中/英两档；日文只存在于"日文补丁"（对话翻译 /jp /zh）与 TTS 里，界面没有日文。）

约定：
  · `_EN` 与 `_JA` 的**键集合必须完全一致**（tests/test_i18n_langs.py 盯着，缺键会红）；
  · `set_lang()` 只认 zh / en / ja，**认不出就退回中文**（保持老行为：不炸、不乱切）；
  · 版号不在这里写死：措辞归 i18n（`welcome(ver)`），版号串由调用方给
    （`i18n.welcome(app_version.full())`）—— 否则英文一套号、中文另一套号，正是要消灭的那种漂。
  · 专有名词（DICK / CODEX / GAL / UTAU / DeepSeek / API Key / URL…）保留原文；
    日文用界面日语（简短体，不写敬语长句），标点用「」！？。
"""

LANGS = ("zh", "en", "ja")
LANG_NAMES = {"zh": "中文", "en": "English", "ja": "日本語"}

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

# 界面日语：简短体（按钮/标签那种<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌），不写敬语长句；专有名词保留原文
_JA = {
    "btn_collapse": "◀ サイドバーを畳む",
    "btn_expand": "▶ サイドバーを開く",
    "lbl_archives": "📂 アーカイブ",
    "btn_new_role": "➕ 新規キャラ",
    "btn_del_role": "🗑️ キャラを削除",
    "btn_exp_role": "📤 キャラを書き出し",
    "btn_imp_role": "📥 キャラを読み込み",
    "btn_open_saves": "📂 セーブフォルダを開く",
    "lbl_worlds": "🌍 ワールド（複数選択 = 並行世界）",
    "btn_new_world": "➕ 新規ワールド",
    "btn_del_world": "🗑️ ワールドを削除",
    "btn_exp_world": "📤 ワールドを書き出し",
    "btn_imp_world": "📥 ワールドを読み込み",
    "btn_open_worlds": "📂 ワールドフォルダを開く",
    "lbl_persona": "🧑 プレイヤー設定",
    "btn_new": "➕ 新規",
    "btn_del": "🗑️ 削除",
    "btn_enable": "✅ 有効",
    "btn_disable": "❌ 無効",
    "lbl_apikey": "API Key を入力：",
    "lbl_provider": "プロバイダ：",
    "lbl_model": "モデル：",
    "lbl_preset": "プリセット：",
    "btn_manage_preset": "✏️ 管理",
    "lbl_budget": "🧮 予算：",
    "chk_rolling": "📜 ローリング要約",
    "btn_start": "✅ チャット開始",
    "menu_tools": "🛠️ ツール",
    "btn_buy_api": "💰 API を購入",
    "input_placeholder": "メッセージを入力...（@名前 で発言者を指定）",
    "btn_send": "送信",
    "btn_retry": "🔄 再生成",
    "btn_edit_last": "✏️ 最後を編集",
    "hint_enter": "💡 Enter で送信。グループチャットでは @名前 で発言者を指定",
    "chk_auto": "🤖 自動応答（グループチャットで他のキャラが続ける）",
    "loading": "⏳ 入力中...",
    "welcome2": "グループチャット：@名前 メッセージ で発言者を指定。",
    "welcome3": "Ctrl を押しながらキャラをクリックすると複数選択できます。",
    "lbl_font": "フォント：",
    "lbl_size": "サイズ：",
    "dlg_welcome_title": "ようこそ",
    "dlg_subtitle": "無制限 AI インタラクションスタジオ",
    "feat1": "🎭 どんなキャラでも作成（性格・背景・話し方）",
    "feat2": "🌍 どんな世界でも構築（ルール・キーワード・シーン）",
    "feat3": "🔄 17 の AI プロバイダを切り替え",
    "feat4": "🧩 プラグインで無限に拡張",
    "lbl_quickstart": "🚀 クイックスタート",
    "qs1": "①「API を購入」から DeepSeek の API Key を取得",
    "qs2": "② Key を貼り付けて「チャット開始」",
    "qs3": "③ 左のキャラを選んで話しかける",
    "btn_get_started": "はじめる",
    "lang_title": "言語",
    "lang_changed": "言語を切り替えました。完全に反映するには再起動してください。",
    "status_roles_prefix": "選択中のキャラ：",
    "roles_none": "なし",
    "chat_empty": "（まだ会話がありません）",
    "sec_cards": "キャラとワールド",
    "btn_settings": "⚙️ 設定",
    "dlg_settings_title": "設定",
    "lbl_language": "言語",
    "btn_lang_switch": "言語を切り替え",
    "lbl_theme_row": "テーマ",
    "btn_theme": "テーマセンターを開く",
    "hint_font": "フォントとサイズは右パネルの一番下",
    "btn_close": "閉じる",
    "theme_unavailable": "テーマセンターは利用できません（Modern UI プラグイン未読み込み）",
    "btn_avatar": "🖼️ アイコン",
    "btn_avatar_persona": "🧑 プレイヤーアイコン",
    "pick_avatar_title": "アイコン画像を選択",
    "pick_avatar_ft": "画像ファイル",
    "pick_role_first": "先にアーカイブ一覧でキャラを選んでください",
    "success": "成功",
    "hint": "情報",
    "auto_speaking": " が入力中...",
}

_TABLE = {"en": _EN, "ja": _JA}


def set_lang(lang):
    """只认 zh / en / ja；认不出退回中文（老行为：不炸、不乱切）"""
    global _LANG
    _LANG = lang if lang in LANGS else "zh"


def lang():
    return _LANG


def t(key, zh):
    if _LANG == "zh":
        return zh
    return _TABLE.get(_LANG, {}).get(key, zh)


def welcome(ver):
    """欢迎语（**版号由调用方给**，这里只负责措辞 —— 版号只有 version.json 一个来源）。"""
    if _LANG == "en":
        return "👋 Welcome to " + str(ver) + "!"
    if _LANG == "ja":
        return "👋 " + str(ver) + " へようこそ！"
    return "👋 欢迎使用 " + str(ver) + "！"


def tokens_label(n):
    if _LANG == "en":
        return "Total tokens: " + str(n)
    if _LANG == "ja":
        return "合計トークン: " + str(n)
    return "总消耗: " + str(n) + " tokens"


def roles_label(zh_text, count):
    """count=0 时显示无角色；否则前缀 + 中文角色名列表（角色名是数据，不翻译）"""
    if _LANG == "zh":
        return zh_text
    if count == 0:
        return t("status_roles_prefix", "") + t("roles_none", "")
    return t("status_roles_prefix", "") + zh_text.replace("当前角色：", "")


def detect_system_lang():
    """首启判定：中文系统 → zh；日文系统 → ja；英文系统 → en；**认不出 → zh**（保持老行为）"""
    try:
        import ctypes
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        if lid == 0x11:
            return "ja"
        if lid == 0x09:
            return "en"
        return "zh"
    except Exception:
        pass
    try:
        import locale
        name = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        name = ""
    if name.startswith("ja"):
        return "ja"
    if name.startswith("en"):
        return "en"
    return "zh"
