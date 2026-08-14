# plugins/official_mode_plugin.py
from plugin_base import PluginBase

class OfficialModePlugin(PluginBase):
    name = "公文模式"
    version = "1.0"
    description = "AI 回复自动转换为公文/正式文书风格"
    author = "seiki"
    enabled = True

    # 预置指令
    PROMPTS = {
        "公文": "\n——请以正式公文格式回复，包含标题、正文、落款，语言严谨、结构清晰，段落分明。",
        "公告": "\n——请以官方公告格式回复，标题清晰，内容简洁明了，语气庄重。",
        "通知": "\n——请以内部通知格式回复，语言简洁，信息明确，包含通知事项和执行要求。",
        "会议纪要": "\n——请以会议纪要格式回复，包含时间、地点、参会人员、议题、决议事项。",
        "请示报告": "\n——请以请示报告格式回复，包含请示事项、理由说明、附件说明。"
    }

    def __init__(self, core):
        super().__init__(core)
        self.mode = "公文"
        self.active = True  # 是否启用公文模式

    def on_message_send(self, user_input):
        if not self.active:
            return user_input

        # 命令检测
        for cmd in self.PROMPTS.keys():
            if user_input.startswith(f"/{cmd}"):
                self.mode = cmd
                return f"✅ 已切换为【{cmd}】模式，请重新发送消息。"

        # 正常消息：添加公文格式指令
        prompt = self.PROMPTS.get(self.mode, self.PROMPTS["公文"])
        return user_input + prompt