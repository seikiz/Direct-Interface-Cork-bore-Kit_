from plugin_base import PluginBase

class EchoPlugin(PluginBase):
    name = "Echo"
    version = "1.0"
    description = "回显用户消息（测试用）"
    author = "seiki"
    enabled = True

    def on_message_send(self, user_input):
        # 在消息前添加 "[Echo] " 前缀
        return "[Echo] " + user_input