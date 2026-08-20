# -*- coding: utf-8 -*-
"""PLUGIN_DEV.md 标准符合性测试：按文档规范写一个插件，
验证 加载/命令(元组+纯字符串)/设置 schema/消息钩子/纯字符串返回 全部按标准工作。
运行：python tests/test_plugin_std.py"""
import sys, os, json, tempfile

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from plugin_base import PluginBase

ok = 0
bad = 0
def check(c, m):
    global ok, bad
    if c:
        ok += 1
        print("  OK " + m)
    else:
        bad += 1
        print("  FAIL " + m)


# ---- 按 PLUGIN_DEV.md 规范写的测试插件 ----
class StdTestPlugin(PluginBase):
    name = "标准测试插件"
    version = "1.0"
    description = "验证插件标准"
    author = "test"
    enabled = True

    settings_schema = [
        {"key": "count", "label": "数量", "type": "int", "default": 3, "min": 1, "max": 10},
        {"key": "auto", "label": "自动", "type": "bool", "default": True},
        {"key": "greeting", "label": "问候", "type": "text", "default": "你好"},
        {"key": "mode", "label": "模式", "type": "choice", "default": "a",
         "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]},
    ]
    ui_buttons = [
        {"type": "method", "label": "🎲 测试", "method": "do_test"},
        {"type": "insert", "label": "🎯 插入", "text": "/hello"},
    ]

    loaded = False
    unloaded = False
    last_send = None
    last_received = None

    def on_load(self):
        self.loaded = True

    def on_unload(self):
        self.unloaded = True

    def on_message_send(self, user_input):
        self.last_send = user_input
        return user_input

    def on_message_received(self, user_input, ai_reply):
        self.last_received = (user_input, ai_reply)

    def on_command(self, command, args):
        if command == "hello":
            return "👋 你好！", False          # 元组 (text, False)
        if command == "askai":
            return "这句话会发给 AI", True      # 元组 (text, True)
        if command == "bare":
            return "纯字符串返回"                # 纯字符串（文档允许）
        if command == "count":
            return f"count={self.get_setting('count', 3)}", False
        return None

    def do_test(self):
        return "method 按钮回调"


def make_core_stub():
    """最小 core 桩（plugin_base 只用 core 存状态；真实场景是 ChatCore）"""
    class Core:
        is_processing = False
        tree = None
        mechanism_state = {}
        client = None
        model = "test"
        _mech_config = None
    return Core()


print("== ① 插件加载 ==")
core = make_core_stub()
p = StdTestPlugin(core)
p.on_load()
check(p.loaded, "on_load 被调用")
check(p.name == "标准测试插件" and p.version == "1.0", "name/version 属性")

print("== ② 声明式设置（settings_schema） ==")
check(p.get_setting("count", 3) == 3, "int 设置默认值")
check(p.get_setting("auto", True) is True, "bool 设置默认值")
check(p.get_setting("greeting", "") == "你好", "text 设置默认值")
p.set_setting("count", 5)
check(p.get_setting("count", 3) == 5, "set_setting 写入")
# 设置持久化到文件
sf = p._settings_file
check(sf and os.path.isfile(sf), "设置写入文件 plugin_settings/<插件名>.json")
if sf and os.path.isfile(sf):
    data = json.load(open(sf, encoding="utf-8"))
    check(data.get("count") == 5, "设置文件内容正确")

print("== ③ ui_buttons 声明 ==")
check(len(p.ui_buttons) == 2 and p.ui_buttons[0]["type"] == "method", "ui_buttons method 项")
check(p.ui_buttons[1]["type"] == "insert" and p.ui_buttons[1]["text"] == "/hello", "ui_buttons insert 项")

print("== ④ 命令钩子（元组返回） ==")
# 模拟管理器 handle_command（与 plugin_manager.py 同逻辑）
def handle(cmd_input):
    parts = cmd_input[1:].strip().split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    r = p.on_command(command, args)
    if r is None:
        return None
    if isinstance(r, str):
        response, send_to_ai = r, False
    else:
        response, send_to_ai = r
    return (response, send_to_ai)

r1 = handle("/hello")
check(r1 == ("👋 你好！", False), "元组返回 (text, False)")
r2 = handle("/AskAI")
check(r2 == ("这句话会发给 AI", True), "命令大小写不敏感 + (text, True)")
r3 = handle("/bare")
check(r3 == ("纯字符串返回", False), "纯字符串返回兼容（标准允许）")
r4 = handle("/count")
check(r4 and "count=5" in r4[0], "命令读取设置: %r" % (r4,))
check(handle("/不存在的命令") is None, "未处理命令返回 None")

print("== ⑤ 消息钩子 ==")
out = p.on_message_send("测试输入")
check(out == "测试输入", "on_message_send 透传")
check(p.last_send == "测试输入", "on_message_send 记录")
p.on_message_received("用户说", "AI 说")
check(p.last_received == ("用户说", "AI 说"), "on_message_received 记录")

print("== ⑥ 卸载钩子 ==")
p.on_unload()
check(p.unloaded, "on_unload 被调用")

# 清理测试设置文件
try:
    if p._settings_file and os.path.isfile(p._settings_file):
        os.remove(p._settings_file)
except Exception:
    pass

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
