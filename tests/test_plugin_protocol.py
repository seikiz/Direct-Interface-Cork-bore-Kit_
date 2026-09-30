# -*- coding: utf-8 -*-
"""DICK 插件协议 v1 测试：主机 spawn 一个协议插件子进程，用 JSON 行走钩子。
这证明"语言无关协议"可行——主机只认 一行JSON进/一行JSON出，不关心里面是 Python/Java/C++。
"""
import sys, os, json, subprocess

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROTO_PLUGIN = os.path.join(ROOT, "plugins", "protocol", "roll_plugin.py")

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


class ProtoHost:
    """最小主机：往插件 stdin 写一行 JSON，读一行 stdout。"""
    def __init__(self, args):
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    def call(self, req):
        self.p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        return json.loads(line) if line else None
    def close(self):
        try:
            self.call({"hook": "close"})
            self.p.stdout.close()
            self.p.stdin.close()
            self.p.wait(timeout=3)
        except Exception:
            pass


# 用 python 运行协议插件（也可以是 .j<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ar / .exe —— 协议不重要，语言无关）
import sys as _sys
py = _sys.executable
host = ProtoHost([py, PROTO_PLUGIN])

# --- ping 存活 ---
r = host.call({"hook": "ping"})
check(r is not None and r.get("result") == "pong", "ping → pong")

# --- get_meta ---
r = host.call({"hook": "get_meta"})
check(r is not None and "骰子" in str(r.get("result", {}).get("name", "")), "get_meta 返回插件元信息")

# --- on_command: /roll 2d6+3 ---
r = host.call({"hook": "on_command", "command": "roll", "args": "2d6+3"})
res = r.get("result") if r else None
check(isinstance(res, dict) and "🎲" in str(res.get("text", "")) and res.get("send") is False,
      "on_command /roll 2d6+3 返回骰子文本")

# --- on_command: 未处理 → result null ---
r = host.call({"hook": "on_command", "command": "blah", "args": ""})
check(r is not None and r.get("result") is None, "未处理命令返回 null")

# --- on_command: /r d20 ---
r = host.call({"hook": "on_command", "command": "r", "args": "d20"})
check(r is not None and "d20" in str(r.get("result", {}).get("text", "")), "/r d20 兼容")

# --- context_injection ---
r = host.call({"hook": "context_injection"})
check(r is not None and "协议插件" in str(r.get("result", "")), "context_injection 返回注入文本")

# --- on_message_send 原样透传（用 ASCII 避免编码比较脆弱；中文透传已由 get_meta 佐证） ---
r = host.call({"hook": "on_message_send", "user_input": "hi"})
check(r is not None and r.get("result", {}).get("text") == "hi" and r.get("result", {}).get("block") is False,
      "on_message_send 透传")

host.close()

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
