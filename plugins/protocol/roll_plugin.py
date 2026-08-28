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
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
