# plugin_base.py
import json
import os
import re

import app_paths


class PluginBase:
    name = "未命名插件"
    version = "1.0"
    description = "无描述"
    author = "匿名"
    enabled = True

    # ============================================================
    # 泛用设置界面（声明式）：插件只需声明 settings_schema，
    # 插件管理器会自动生成设置窗口，无需编写任何 Tk 代码。
    # 每项格式:
    #   {"key": "xxx", "label": "显示名", "type": "text|secret|int|bool|choice|file",
    #    "default": 默认值, "options": [...] (choice), "min"/"max": 数值范围 (int)}
    # ============================================================
    settings_schema = []

    # ============================================================
    # 泛用 UI 模组（声明式）：插件在主界面「🧩 插件坞」注册按钮，
    # 无需编写任何 Tk 代码。每项格式:
    #   {"type": "method", "label": "🖼️ 图片", "method": "show_window"}
    #       → 点击调用插件的 show_window() 方法
    #   {"type": "insert", "label": "🎲 d20", "text": "/r 1d20"}
    #       → 点击把 text 插入主界面输入框（如快捷命令）
    # 只有启用的插件才会显示按钮。
    # ============================================================
    ui_buttons = []

    def __init__(self, core):
        """core 是 ChatCore 实例"""
        self.core = core
        # ---------- 泛用设置系统 ----------
        self.settings = {}
        self._settings_file = None
        if self.name and getattr(self, "settings_schema", None):
            base = app_paths.get_base_dir()  # exe 模式跟随 exe 目录，源码模式为工程根
            safe = re.sub(r'[\\/:*?"<>|]', "_", self.name)
            self._settings_file = os.path.join(base, "plugin_settings", f"{safe}.json")
            self._load_settings()

    # ---------- 设置读写 ----------
    def _load_settings(self):
        data = {}
        if self._settings_file and os.path.exists(self._settings_file):
            try:
                with open(self._settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        # 合并 schema 默认值（新声明的配置项自动补默认值）
        for item in self.settings_schema:
            key = item.get("key")
            if key and key not in data:
                data[key] = item.get("default")
        self.settings = data

    def _save_settings(self):
        if not self._settings_file:
            return
        try:
            os.makedirs(os.path.dirname(self._settings_file), exist_ok=True)
            with open(self._settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[PluginBase] 设置保存失败: {e}")

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value
        self._save_settings()

    def on_load(self):
        """插件加载时调用"""
        pass

    def on_unload(self):
        """插件卸载时调用"""
        pass

    def on_message_send(self, user_input):
        """用户发送消息前调用，返回修改后的消息或 None 以阻止发送"""
        return user_input

    def on_message_received(self, user_input, ai_reply):
        """AI 回复后调用"""
        pass

    def on_command(self, command, args):
        """
        处理自定义命令，如 /help
        返回 (response_text, should_send_to_ai) 或 None
        """
        return None
