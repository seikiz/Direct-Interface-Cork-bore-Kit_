# ============================================================
#   jp_patch_plugin.py - 日文补丁（日中互译）v1.0
#
#   使用已配置的 LLM 进行翻译，无需额外 API Key：
#   - 可选：自动把用户输入翻译成日语再发送（AI 会用日语回复）
#   - /jp <文本>  翻译成日语
#   - /zh <文本>  翻译成中文
#   配合「日文朗读 TTS」插件可形成完整日文体验
# ============================================================

import re

from plugin_base import PluginBase


class JpPatchPlugin(PluginBase):
    name = "日文补丁"
    version = "1.0"
    description = "日中互译：输入自动译日语、/jp /zh 命令翻译（使用已配置的 LLM）"
    author = "seiki"
    enabled = True

    ui_buttons = [
        {"type": "insert", "label": "🗾 日译", "text": "/jp "},
        {"type": "insert", "label": "🀄 中译", "text": "/zh "},
    ]

    settings_schema = [
        {"key": "auto_translate_input", "label": "自动把输入翻译成日语再发送",
         "type": "bool", "default": False},
        {"key": "style", "label": "翻译风格", "type": "choice",
         "options": ["自然口语", "敬语（です/ます）", "简体（だ/である）"], "default": "自然口语"},
    ]

    def on_load(self):
        print("[日文补丁] 已加载：/jp 译日、/zh 译中；可在 ⚙️ 设置开启自动日译")

    # ---------- 翻译核心（复用主程序 LLM） ----------
    def _translate(self, text, direction, style=None):
        """direction: 'jp' 译成日语 / 'zh' 译成中文"""
        client = getattr(self.core, "client", None)
        if not client:
            return "⚠️ 请先启动聊天（需要 LLM 连接）"
        text = (text or "").strip()
        if not text:
            return "⚠️ 请输入要翻译的内容"
        style = style or self.get_setting("style", "自然口语")
        target = "日语" if direction == "jp" else "中文"
        try:
            resp = client.chat.completions.create(
                model=getattr(self.core, "model", "deepseek-chat"),
                messages=[
                    {"role": "system", "content":
                     f"你是专业日中翻译。只输出译文本身，不要任何解释、引号或前后缀。"
                     f"翻译风格：{style}。"},
                    {"role": "user", "content": f"把下面的内容翻译成{target}：\n{text}"},
                ],
                stream=False,
                timeout=60,
            )
            result = (resp.choices[0].message.content or "").strip()
            return result or "⚠️ 翻译结果为空"
        except Exception as e:
            return f"⚠️ 翻译失败：{e}"

    @staticmethod
    def _is_japanese(text):
        """包含假名则视为已是日语"""
        return bool(re.search(r'[\u3040-\u30ff]', text or ""))

    # ---------- 钩子：自动日译输入（翻译隐藏：显示原文，发送译文） ----------
    # 约定：返回 "\u200b<原文>\u200b<译文>" 时，发送层存树/显示用原文、发给 AI 用译文
    HIDE_MARK = "\u200b"

    def on_message_send(self, user_input):
        if not user_input:
            return user_input
        if not self.get_setting("auto_translate_input", False):
            return user_input
        if user_input.startswith("/"):
            return user_input  # 命令不翻译
        if self._is_japanese(user_input):
            return user_input  # 已是日语
        translated = self._translate(user_input, "jp")
        if translated.startswith("⚠️"):
            print(f"[日文补丁] {translated}")
            return user_input
        # 翻译隐藏：原文留在聊天显示，译文只进 AI 上下文
        print(f"[日文补丁] 🌐 已译为日语（显示保持原文）：{translated[:40]}...")
        return self.HIDE_MARK + user_input + self.HIDE_MARK + translated

    @staticmethod
    def split_hidden(text):
        """解析翻译隐藏标记 → (显示文本, 发送文本)。无标记则两者相同"""
        if not text:
            return text, text
        mark = JpPatchPlugin.HIDE_MARK
        if text.startswith(mark):
            parts = text.split(mark)
            # [空, 原文, 译文, ...]
            if len(parts) >= 3:
                return parts[1], mark.join(parts[2:])
        return text, text

    # ---------- 命令 ----------
    def on_command(self, command, args):
        if command == "jp":
            return self._translate(args, "jp"), False
        if command == "zh":
            return self._translate(args, "zh"), False
        if command in ("jphelp", "日语帮助"):
            return ("🗾 日文补丁 使用说明\n"
                    "  /jp <文本>     翻译成日语\n"
                    "  /zh <文本>     翻译成中文\n"
                    "  ⚙️ 设置可开启「自动把输入翻译成日语再发送」"), False
        return None
