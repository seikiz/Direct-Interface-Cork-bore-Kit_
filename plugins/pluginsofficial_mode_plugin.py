# plugins/official_mode_plugin.py
# 公文模式已迁移为「提示词预设」（预设下拉选择「公文模式」）。
# 本插件不再注入任何指令，仅保留引导与说明。
from plugin_base import PluginBase

class OfficialModePlugin(PluginBase):
    name = "公文模式"
    version = "2.0"
    description = "已迁移为预设：请在右上角「预设」下拉选择「公文模式」（自动禁用角色卡）"
    author = "seiki"
    enabled = True

    def on_load(self):
        print("[公文模式] 已迁移为预设：右上角「预设」→「公文模式」")

    def on_message_send(self, user_input):
        return user_input  # 不再注入指令（预设负责全部格式要求）

    def on_command(self, command, args):
        if command in ("公文", "公告", "通知", "会议纪要", "请示报告"):
            return ("📄 公文模式已升级为提示词预设。\n"
                    "请在右上角「预设」下拉选择「公文模式」，\n"
                    "然后在消息中直接说明文种（如：写一份会议纪要…）。"), False
        return None
