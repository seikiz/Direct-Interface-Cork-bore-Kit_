# ============================================================
#   trpg_server.py - 去中心化跑团主机（薄壳版）v0.2
#
#   跑团核心已提炼到 trpg_session.py（TrpgSession，可嵌入任意设备），
#   本文件只做 HTTP 薄壳：把它 LAN 暴露给浏览器/手机客户端。
#   成员直连"跑团主机(GM 设备)"即可加入 —— 该主机可以是 PC，也可以是
#   任一手机(另一端 App 内嵌 TrpgSession + 当 GM)。
#
#   用法：python trpg_server.py [端口]
#   （默认 WORKSHOP_TRPG_PORT 或 5080；GM/PC 卡从 saves/<名字>.json 读）
# ============================================================

import os
import sys
import json
import atexit
import threading

from flask import Flask, request, jsonify, send_file

from trpg_session import TrpgSession

app = Flask(__name__)


def _app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


ROOT = _app_root()

PORT = int(os.environ.get("WORKSHOP_TRPG_PORT", "5080"))
DISCOVER_PORT = int(os.environ.get("WORKSHOP_TRPG_DISCOVER", "5081"))
DISCOVER_MAGIC = b"DICK_TRPG_DISCOVER_V1"

# 会期锁定：跑团进行中，本机编辑器据此锁定 GM+PC 卡（防导入存档串扰）
def _lockfile():
    return os.path.join(ROOT, "saves", ".trpg_lock.json")


def _write_lock(session):
    names = [session.gm] if session.gm else []
    names += session.pcs
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n); out.append(n)
    if not out:
        return
    try:
        os.makedirs(os.path.dirname(_lockfile()), exist_ok=True)
        with open(_lockfile(), "w", encoding="utf-8") as f:
            json.dump({"locked": out, "gm": session.gm, "pcs": session.pcs}, f, ensure_ascii=False, indent=2)
        print("[跑团会期] 已锁定角色卡(本机不可改)：", ", ".join(out))
    except Exception as e:
        print("[跑团会期] 写锁失败：", e)


def _clear_lock():
    try:
        if os.path.exists(_lockfile()):
            os.remove(_lockfile())
            print("[跑团会期] 已解除角色卡锁定")
    except Exception:
        pass


def _lan_ip() -> str:
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip or "127.0.0.1"
    except Exception:
        return "127.0.0.1"


def _udp_discover_loop(session):
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
                reply = json.dumps({"service": "trpg", "name": "DICK 跑团",
                                    "url": f"http://{_lan_ip()}:{PORT}", "gm": session.gm}).encode("utf-8")
                s.sendto(reply, addr)
            except Exception:
                pass


# ---- 全局会话引擎（薄壳持有；也可由手机端内嵌同样逻辑） ----
_session = None  # TrpgSession；在 __main__ 初始化


def _config():
    try:
        with open(os.path.join(ROOT, "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------- 端（薄壳转发到引擎） ----------------
@app.get("/")
def index():
    for cand in (os.path.join(ROOT, "web", "trpg.html"),
                 os.path.join(ROOT, "_internal", "web", "trpg.html")):
        if os.path.exists(cand):
            return send_file(cand)
    return "trpg.html not found", 404


@app.get("/api/state")
def state():
    return jsonify(_session.state())


@app.post("/api/setup")
def setup():
    d = request.get_json(silent=True) or {}
    r = _session.setup(gm=d.get("gm"), pcs=d.get("pcs"))
    _write_lock(_session)
    return jsonify(r)


@app.post("/api/end")
def end():
    _clear_lock()
    return jsonify(_session.end())


@app.post("/api/join")
def join():
    d = request.get_json(silent=True) or {}
    r = _session.join(str(d.get("name") or "").strip(), str(d.get("player") or "").strip())
    if "error" in r:
        return jsonify(r), 400
    return jsonify(r)


@app.post("/api/leave")
def leave():
    d = request.get_json(silent=True) or {}
    return jsonify(_session.leave(str(d.get("name") or "").strip()))


@app.post("/api/act")
def act():
    d = request.get_json(silent=True) or {}
    r = _session.act(str(d.get("actor") or "").strip(), str(d.get("action") or "").strip())
    if "error" in r:
        return jsonify(r), 400
    return jsonify(r)


if __name__ == "__main__":
    cfg = _config()
    gm = os.environ.get("WORKSHOP_TRPG_GM") or "咲"
    pcs = os.environ.get("WORKSHOP_TRPG_PCS") or "凛,咲"
    _session = TrpgSession(config=cfg, gm=gm, pcs=[x.strip() for x in pcs.split(",") if x.strip()],
                           save_dir=os.path.join(ROOT, "saves"))
    _write_lock(_session)
    atexit.register(_clear_lock)
    threading.Thread(target=lambda: _udp_discover_loop(_session), daemon=True).start()
    print("🎭 去中心化跑团主机(GM 设备)启动...")
    print(f"📱 玩家同一 Wi-Fi 打开: http://{_lan_ip()}:{PORT} （或客户端一键加入 / 蓝牙接近握手）")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
