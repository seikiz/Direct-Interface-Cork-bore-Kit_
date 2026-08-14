# plugin_base.py
class PluginBase:
    name = "未命名插件"
    version = "1.0"
    description = "无描述"
    author = "匿名"
    enabled = True

    def __init__(self, core):
        """core 是 ChatCore 实例"""
        self.core = core

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