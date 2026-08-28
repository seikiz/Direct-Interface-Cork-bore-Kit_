# ============================================================
#   trpg_server.py - 局域网剧情跑团主机（v0.1）
#
#   PC 当主机：加载 DICK 的 config(API) + GM/PC 角色卡，
#   局域网内玩家用浏览器打开 http://<电脑IP>:<端口> 即可加入，
#   各自控制一张 PC，提交行动 → GM(AI) 剧情叙述 → 全员可见。
#
#   用法：python trpg_server.py [端口]
#   （默认取 WORKSHOP_PORT 或 5080）
#   GM/PC 卡从 saves/<名字>.json 读取；默认 GM=咲, PC=凛 可改。
# ============================================================

import os
import sys
import json
import re
import atexit
import threading

from flask import Flask, request, jsonify, send_file

from openai import OpenAI

app = Flask(__name__)


def _app_root() -> str:
    """应用根目录：源码运行用 __file__；冻结为 EXE 后用 sys.executable，
    保证 trpg_server.exe 能定位旁边的 config.json / saves / web。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


ROOT = _app_root()

PORT = int(os.environ.get("WORKSHOP_TRPG_PORT", "5080"))
DISCOVER_PORT = int(os.environ.get("WORKSHOP_TRPG_DISCOVER", "5081"))
DISCOVER_MAGIC = b"DICK_TRPG_DISCOVER_V1"

_conf = {}
_gm = ""             # GM 卡名
_pcs = []            # PC 卡名（列表）
_story = []          # [{"actor":..,"action":..,"gm":..}] 剧情日志
_turn = ""           # 当前行动者
_joined = {}         # pc 名 -> 玩家昵称（去重）
_lock = threading.Lock()

_GM_PROMPT = (
    "【跑团模式 · 剧情为主】你是一名 TRPG 主持人(GM)，正在一场以剧情为核心的冒险。规则："
    "① 节奏由剧情驱动，把每个行动演成有画面感的场景并自然引出下一段剧情，不机械播报数值；"
    "② 在节点给当前行动者 2-4 个下一步选项(GAL 分支)；③ 不确定性用掷骰(大成功/大失败/暴击要演出)；"
    "④ 每个 PC 一张角色卡，贴合各自设定，绝不串戏；⑤ 保持世界观一致，让故事有因果、悬念、情感。"
    "你用 GM 口吻叙述：先一句场景，再给该行动的结果，结尾给 2-4 个下一步选项。"
)


def _load_config():
    global _conf
    p = os.path.join(ROOT, "config.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            _conf = json.load(f)
    except Exception:
        _conf = {}


# ---------- 会期锁定：与 DICK 本机 /trpg 插件共用 .trpg_lock.json ----------
# 局域网多人跑团进行中，本机卡片编辑器据此锁定 GM+PC 卡（不可改/不可删/不可被导入覆盖），
# 从根本上杜绝「导入存档」与「跑团会期」互相串扰。
def _lockfile():
    return os.path.join(ROOT, "saves", ".trpg_lock.json")


def _locked_names():
    names = ([_gm] if _gm else []) + list(_pcs)
    # 去重且保留顺序
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n); out.append(n)
    return out


def _write_lock():
    names = _locked_names()
    if not names:
        return
    try:
        os.makedirs(os.path.dirname(_lockfile()), exist_ok=True)
        with open(_lockfile(), "w", encoding="utf-8") as f:
            json.dump({"locked": names, "gm": _gm, "pcs": _pcs}, f, ensure_ascii=False, indent=2)
        print("[跑团会期] 已锁定角色卡(本机不可改)：", ", ".join(names))
    except Exception as e:
        print("[跑团会期] 写锁失败：", e)


def _clear_lock():
    try:
        if os.path.exists(_lockfile()):
            os.remove(_lockfile())
            print("[跑团会期] 已解除角色卡锁定")
    except Exception:
        pass


def _card_prompt(name):
    """从 saves/<name>.json 读取该角色卡的 system_prompt"""
    try:
        with open(os.path.join(ROOT, "saves", name + ".json"), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("system_prompt") or d.get("name") or ""
    except Exception:
        return ""


def _lan_ip() -> str:
    """获取本机局域网 IP（连接外网探测到的本地地址；失败回退回环）"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip or "127.0.0.1"
    except Exception:
        return "127.0.0.1"


def _udp_discover_loop():
    """局域网发现：客户端发 DISCOVER_MAGIC 到 UDP DISCOVER_PORT，回复自己 URL。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", DISCOVER_PORT))
    except Exception as e:
        print(f"[跑团发现] UDP 监听失败(端口 {DISCOVER_PORT}): {e}")
        return
    print(f"[跑团发现] 已启动：玩家客户端发探测到 UDP {DISCOVER_PORT} 即可一键找到本局")
    while True:
        try:
            data, addr = s.recvfrom(1024)
        except Exception:
            continue
        if data and data.strip() == DISCOVER_MAGIC:
            try:
                reply = json.dumps({"service": "trpg", "name": "DICK 跑团", "url": f"http://{_lan_ip()}:{PORT}", "gm": _gm}).encode("utf-8")
                s.sendto(reply, addr)
            except Exception:
                pass


def _gm_system(actor):
    parts = [_GM_PROMPT]
    if _gm:
        parts.append("（主持者 GM 卡：\n" + _card_prompt(_gm) + "\n）")
    if _pcs:
        parts.append("本次队伍(PC)：" + "、".join(_pcs) + "。各角色设定如下：")
        for pc in _pcs:
            sp = _card_prompt(pc)
            if sp:
                parts.append("■ " + pc + "：\n" + sp)
    if _story:
        parts.append("【剧情回顾】")
        for s in _story[-12:]:
            parts.append("- " + s["actor"] + "：" + s["action"] + " → 「" + s["gm"] + "」")
    parts.append("当前行动者：" + actor + "，请围绕他/她的行动叙事并给 2-4 个下一步选项。")
    return "\n\n".join(parts)


def _llm(system, user):
    """调用模型叙述。返回文本；失败返回友好提示。"""
    cfg = _conf
    key = (cfg.get("api_key") or "").strip() or "free"
    base = (cfg.get("base_url") or "https://api.deepseek.com").strip()
    model = (cfg.get("model") or "deepseek-v4-flash").strip()
    client = OpenAI(api_key=key, base_url=base)
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stream=False, timeout=120,
    )
    return (r.choices[0].message.content or "").strip()


# ---------------- 端 ----------------
@app.get("/")
def index():
    """返回跑团控制台页。兼容两种布局：web/ 在 EXE 旁，或冻结后落在 _internal/web。"""
    for cand in (os.path.join(ROOT, "web", "trpg.html"),
                 os.path.join(ROOT, "_internal", "web", "trpg.html")):
        if os.path.exists(cand):
            return send_file(cand)
    return "trpg.html not found", 404


@app.get("/api/state")
def state():
    with _lock:
        return jsonify({
            "gm": _gm, "pcs": _pcs, "turn": _turn,
            "story": _story[-40:], "joined": _joined,
        })


@app.post("/api/setup")
def setup():
    global _gm, _pcs, _turn
    d = request.get_json(silent=True) or {}
    if d.get("gm"):
        _gm = str(d["gm"]).strip()
    if isinstance(d.get("pcs"), list):
        _pcs = [str(x).strip() for x in d["pcs"] if str(x).strip()]
    if _pcs:
        _turn = _pcs[0]
    _write_lock()   # 会期锁定：本机编辑器据此锁定 GM+PC 卡（防导入存档串扰）
    return jsonify({"ok": True, "turn": _turn})


@app.post("/api/end")
def end():
    """结束本局跑团：解除本机角色卡锁定（/trpg end 的对等操作）。"""
    _clear_lock()
    return jsonify({"ok": True})


@app.post("/api/join")
def join():
    d = request.get_json(silent=True) or {}
    pc = str(d.get("name") or "").strip()
    player = str(d.get("player") or "").strip() or "玩家"
    if pc not in _pcs:
        return jsonify({"error": "该角色不在队伍中"}), 400
    with _lock:
        _joined[pc] = player
    return jsonify({"ok": True, "turn": _turn})


@app.post("/api/leave")
def leave():
    """PC 退出跑团：从已加入名单移除（前端离开会话时调用）。"""
    d = request.get_json(silent=True) or {}
    pc = str(d.get("name") or "").strip()
    with _lock:
        if pc:
            _joined.pop(pc, None)
    return jsonify({"ok": True, "joined": list(_joined.keys())})


@app.post("/api/act")
def act():
    d = request.get_json(silent=True) or {}
    actor = str(d.get("actor") or "").strip()
    action = str(d.get("action") or "").strip()
    if not action:
        return jsonify({"error": "行动不能为空"}), 400
    if not actor:
        actor = _turn or (_pcs[0] if _pcs else "你")

    system = _gm_system(actor)
    narration = _llm(system, f"{actor}的行动：{action}\n请叙述接下来发生什么，结尾给 2-4 个下一步选项。")

    with _lock:
        _story.append({"actor": actor, "action": action, "gm": narration})
        # 轮换行动者（自动）
        if _pcs:
            i = _pcs.index(actor) if actor in _pcs else 0
            _turn = _pcs[(i + 1) % len(_pcs)]
    return jsonify({"ok": True, "gm": narration, "turn": _turn})


if __name__ == "__main__":
    import threading as _th
    _load_config()
    # 默认 GM/PC（可改）
    if not _gm:
        _gm = "咲"
    if not _pcs:
        _pcs = ["凛", "咲"]
    if _pcs:
        _turn = _pcs[0]
    _write_lock()   # 启动即锁定本局 GM+PC 卡
    atexit.register(_clear_lock)   # 进程退出时解锁，避免残留锁导致改卡被拒
    _th.Thread(target=_udp_discover_loop, daemon=True).start()
    print("🎭 局域网剧情跑团主机启动中...")
    print(f"📱 玩家在同一 Wi-Fi 打开: http://{_lan_ip()}:{PORT} （或客户端一键加入）")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
