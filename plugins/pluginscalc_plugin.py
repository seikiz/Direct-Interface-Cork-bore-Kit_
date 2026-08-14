import re
from plugin_base import PluginBase

class CalcPlugin(PluginBase):
    name = "Calculator"
    version = "1.0"
    description = "支持 /calc 1+2 命令"
    author = "seiki"

    def on_command(self, command, args):
        if command == "calc":
            try:
                result = eval(args, {"__builtins__": {}}, {})
                return f"计算结果: {result}", False
            except Exception as e:
                return f"计算错误: {e}", False
        return None