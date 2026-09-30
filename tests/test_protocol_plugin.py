# -*- coding: utf-8 -*-
"""DICK 插件协议主机适配器测试：ProtocolPlugin spawn 一个协议插件进程，
验证它能像普通插件一样被调用（命令 / 上下文注入 / 消息拦截）。"""
import sys, os, json

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from protocol_plugin import ProtocolPlugin

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

ROLL = os.path.join(ROOT, "plugins", "protocol", "roll_plugin.py")
# 用当前解释器 spa<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌wn（与源码环境一致）
pl = ProtocolPlugin(core=None, name="骰子(协议)", command=sys.executable, args=[ROLL], base_dir=ROOT)

check(pl._spawn_err is None, "协议插件成功 spawn")
check("骰子" in pl.name, "get_meta 填充名称: " + pl.name)
check(pl.description != "语言无关协议插件", "get_meta 填充描述")
check(pl.ui_buttons and pl.ui_buttons[0].get("type") == "insert", "list_ui_buttons 拿到按钮")

# --- on_command /roll ---
r = pl.on_command("roll", "2d6+3")
check(isinstance(r, tuple) and "🎲" in r[0] and r[1] is False, "on_command /roll 返回 (骰子文本, False)")

# --- on_command 未处理 → None ---
check(pl.on_command("blah", "") is None, "on_command 未处理返回 None")

# --- /r 兼容 ---
r2 = pl.on_command("r", "d20")
check(r2 is not None and "d20" in r2[0], "/r d20 兼容")

# --- contextInjection ---
check("协议插件" in pl.contextInjection(), "contextInjection 返回注入文本")

# --- on_message_send 透传 ---
check(pl.on_message_send("hi") == "hi", "on_message_send 原样透传")

# --- on_message_send 拦截（block）---
# 注入一个"block"命令的请求不便，这里用 roll 插件的默认（不拦截）即可，
# 拦截逻辑由协议应答 block=true 触发，已在 test_plugin_protocol 的协议层验证。

pl.on_unload()
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
