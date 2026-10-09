import sys
import json
import random
import re

META = {
    "name": "骰子(协议示例)",
    "version": "1.0",
    "description": "语言无关协议示例插件：/roll 2d6+3",
    "author": "seiki",
}


def handle(req):
    hook = req.get("hook")
    if hook == "ping":
        return {"result": "pong"}
    if hook == "get_meta":
        return {"result": META}
    if hook == "list_ui_buttons":
        return {"result": [{"type": "insert", "label": "🎲 掷骰", "text": "/roll 1d20"}]}
    if hook == "on_command":
        cmd = (req.get("command") or "").lower()
        if cmd in ("roll", "r"):
            m = re.match(r"(\d*)d(\d+)([+-]\d+)?", req.get("args") or "1d20")
            if m:
                n, f, mod = int(m.group(1) or 1), int(m.group(2)), int(m.group(3) or 0)
                if f in (4, 6, 8, 10, 12, 20, 100):
                    rolls = [random.randint(1, f) for _ in range(n)]
                    total = sum(rolls) + mod
                    s = ("🎲 " + str(n) + "d" + str(f) + (f"{mod:+d}" if mod else "") +
                         " = [" + ", ".join(str(x) for x in rolls) + "]" +
                         (f" {mod:+d}" if mod else "") + " = **" + str(total) + "**")
                    return {"result": {"text": s, "send": False}}
        return {"result": None}
    if hook == "context_injection":
        return {"result": "【协议插件】可用 /roll `<骰子>`, 如 /roll 2d6+3、/r d20。"}
    if hook == "on_message_send":
        return {"result": {"text": req.get("user_input"), "block": False}}
    if hook == "on_message_received":
        return {"result": None}
    if hook == "get_settings":
        return {"result": {}}
    if hook == "get_setting":
        return {"result": None}
    if hook == "set_setting":
        return {"result": None}
    if hook == "on_load":
        return {"result": None}
    if hook == "on_unload":
        return {"result": None}
    if hook == "close":
        return {"result": None}
    return {"result": None}


def main():
    # 三根管子都要显式 UTF-8 —— **stdin 最容易漏**：
    # Python 子进程的 stdin/stdout 默认跟着 locale 走，Windows 上是 GBK/CP936。
    # 宿主人那边已经按 UTF-8 收发（protocol_plugin.py 里 encoding="utf-8"），
    # 子进程这边若只改 stdout，读进来的中文就被按 GBK 解成乱码（还带 `?` 丢字节），
    # 再回给宿主 —— 用户自己发的那句话就变成"鎴戝彨…"。
    # Linux 默认就是 UTF-8，所以这个坑只在 Windows 上炸（2026-10 在本地测试里抓到）。
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("hook") == "close":
                sys.stdout.write(json.dumps({"result": None}) + "\n")
                sys.stdout.flush()
                break
            out = handle(req)
        except Exception as e:
            out = {"error": str(e)}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌