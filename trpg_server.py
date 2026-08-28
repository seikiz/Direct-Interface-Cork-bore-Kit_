# ============================================================
#   trpg_server.py - 去中心化跑团主机（房间管理版）v0.3
#
#   跑团核心在 trpg_session.py（TrpgSession，可嵌入任意设备），
#   本文件是 HTTP 薄壳 + **房间管理**：可同时承载多个跑团房间
#   （每个房间一个 TrpgSession + 元数据），提供列表/创建/加入/关闭。
#
#   房间接口：
#     GET    /api/rooms                     -> 房间列表
#     POST   /api/rooms                     -> 创建房间 {name,gm,pcs}
#     DELETE /api/rooms/<id>                -> 关闭房间
#     GET    /api/rooms/<id>/state          -> 房间状态
#     POST   /api/rooms/<id>/join|leave|act -> 房间操作
#   （保留旧单会话 /api/state|setup|end|join|leave|act 映射到"当前房间"，向后兼容）
#
#   用法：python trpg_server.py [端口]
# ============================================================

import os
import sys
import json
import uuid
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
            json.dump({"locked": out, "gm": session.gm, "pcs": session.pcs},
                      f, ensure_ascii=False, indent=2)
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


def _udp_discover_loop(rooms_getter):
    """局域网发现：回复本机所有房间的简要信息，供成员客户端一键扫到。"""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", DISCOVER_PORT))
    except Exception as e:
        print(f"[跑团发现] UDP 监听失败(端口 {DISCOVER_PORT}): {e}")
        return
    print(f"[跑团发现] 已启动：玩家客户端发探测到 UDP {DISCOVER_PORT} 即可找到本机房间")
    while True:
        try:
            data, addr = s.recvfrom(1024)
        except Exception:
            continue
        if data and data.strip() == DISCOVER_MAGIC:
            try:
                rooms = rooms_getter()
                reply = json.dumps({
                    "service": "trpg", "name": "DICK 跑团",
                    "url": f"http://{_lan_ip()}:{PORT}",
                    "rooms": rooms,
                    # 向后兼容：单房间场景仍带顶层 gm（旧客户端/旧测试识别用）
                    "gm": (rooms[0]["gm"] if rooms else ""),
                }, ensure_ascii=False).encode("utf-8")
                s.sendto(reply, addr)
            except Exception:
                pass


# ---- 房间注册表：id -> TrpgSession（含元数据） ----
_rooms = {}          # room_id -> {"session": TrpgSession, "name": str, "created_at": ts}
_rooms_lock = threading.Lock()
_active_room_id = None  # 当前房间（旧单会话接口映射到这）

# 收集房间列表（供 UDP 发现回复 / GET /api/rooms）
def _room_list():
    out = []
    with _rooms_lock:
        for rid, r in _rooms.items():
            sess = r["session"]
            out.append({
                "id": rid, "name": r.get("name") or "未命名房间",
                "gm": sess.gm, "pcs": sess.pcs,
                "turn": sess.turn,
                "joined": len(sess.joined),
                "story_len": len(sess.story),
            })
    return out


def _config():
    try:
        with open(os.path.join(ROOT, "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _room_or_404(room_id):
    with _rooms_lock:
        r = _rooms.get(room_id)
    if not r:
        return None
    return r


# ---------------- 房间管理接口 ----------------
@app.get("/api/rooms")
def rooms_list():
    return jsonify({"rooms": _room_list(), "count": len(_room_list())})


@app.post("/api/rooms")
def rooms_create():
    d = request.get_json(silent=True) or {}
    name = str(d.get("name") or "未命名房间").strip()[:40]
    gm = str(d.get("gm") or "").strip()
    pcs = [str(x).strip() for x in (d.get("pcs") or []) if str(x).strip()]
    cfg = _config()
    rid = uuid.uuid4().hex[:8]
    sess = TrpgSession(config=cfg, gm=gm, pcs=pcs, save_dir=os.path.join(ROOT, "saves"))
    with _rooms_lock:
        _rooms[rid] = {"session": sess, "name": name, "created_at": None}
        if _active_room_id is None:
            _active_room_id = rid
    _write_lock(sess)
    return jsonify({"ok": True, "id": rid, "name": name})


@app.delete("/api/rooms/<room_id>")
def rooms_delete(room_id):
    with _rooms_lock:
        r = _rooms.pop(room_id, None)
        if _active_room_id == room_id:
            _active_room_id = next(iter(_rooms), None) if _rooms else None
    if not r:
        return jsonify({"error": "房间不存在"}), 404
    return jsonify({"ok": True})


# ---------------- 房间子路由 ----------------
@app.get("/api/rooms/<room_id>/state")
def room_state(room_id):
    r = _room_or_404(room_id)
    if not r:
        return jsonify({"error": "房间不存在"}), 404
    return jsonify(r["session"].state())


@app.post("/api/rooms/<room_id>/join")
def room_join(room_id):
    r = _room_or_404(room_id)
    if not r:
        return jsonify({"error": "房间不存在"}), 404
    d = request.get_json(silent=True) or {}
    out = r["session"].join(str(d.get("name") or "").strip(), str(d.get("player") or "").strip())
    if "error" in out:
        return jsonify(out), 400
    return jsonify(out)


@app.post("/api/rooms/<room_id>/leave")
def room_leave(room_id):
    r = _room_or_404(room_id)
    if not r:
        return jsonify({"error": "房间不存在"}), 404
    d = request.get_json(silent=True) or {}
    return jsonify(r["session"].leave(str(d.get("name") or "").strip()))


@app.post("/api/rooms/<room_id>/act")
def room_act(room_id):
    r = _room_or_404(room_id)
    if not r:
        return jsonify({"error": "房间不存在"}), 404
    d = request.get_json(silent=True) or {}
    out = r["session"].act(str(d.get("actor") or "").strip(), str(d.get("action") or "").strip())
    if "error" in out:
        return jsonify(out), 400
    return jsonify(out)


# ---------------- 旧单会话接口（映射到当前房间，向后兼容） ----------------
def _active():
    global _active_room_id
    with _rooms_lock:
        if _active_room_id and _active_room_id in _rooms:
            return _rooms[_active_room_id]["session"]
    # 无房间时自动建一个默认，避免旧客户端 404
    if not _rooms:
        rid = uuid.uuid4().hex[:8]
        cfg = _config()
        sess = TrpgSession(config=cfg, gm=os.environ.get("WORKSHOP_TRPG_GM") or "咲",
                           pcs=[x.strip() for x in (os.environ.get("WORKSHOP_TRPG_PCS") or "凛,咲").split(",") if x.strip()],
                           save_dir=os.path.join(ROOT, "saves"))
        with _rooms_lock:
            _rooms[rid] = {"session": sess, "name": "默认房间", "created_at": None}
            _active_room_id = rid
        return sess
    with _rooms_lock:
        return _rooms[next(iter(_rooms))]["session"]


@app.get("/api/state")
def state():
    return jsonify(_active().state())


@app.post("/api/setup")
def setup():
    d = request.get_json(silent=True) or {}
    r = _active().setup(gm=d.get("gm"), pcs=d.get("pcs"))
    _write_lock(_active())
    return jsonify(r)


@app.post("/api/end")
def end():
    _clear_lock()
    return jsonify(_active().end())


@app.post("/api/join")
def join():
    d = request.get_json(silent=True) or {}
    r = _active().join(str(d.get("name") or "").strip(), str(d.get("player") or "").strip())
    if "error" in r:
        return jsonify(r), 400
    return jsonify(r)


@app.post("/api/leave")
def leave():
    d = request.get_json(silent=True) or {}
    return jsonify(_active().leave(str(d.get("name") or "").strip()))


@app.post("/api/act")
def act():
    d = request.get_json(silent=True) or {}
    r = _active().act(str(d.get("actor") or "").strip(), str(d.get("action") or "").strip())
    if "error" in r:
        return jsonify(r), 400
    return jsonify(r)


# 控制台页
@app.get("/")
def index():
    for cand in (os.path.join(ROOT, "web", "trpg.html"),
                 os.path.join(ROOT, "_internal", "web", "trpg.html")):
        if os.path.exists(cand):
            return send_file(cand)
    return "trpg.html not found", 404


if __name__ == "__main__":
    cfg = _config()
    # 启动时建默认房间（旧行为兼容）
    rid = uuid.uuid4().hex[:8]
    sess = TrpgSession(config=cfg,
                       gm=os.environ.get("WORKSHOP_TRPG_GM") or "咲",
                       pcs=[x.strip() for x in (os.environ.get("WORKSHOP_TRPG_PCS") or "凛,咲").split(",") if x.strip()],
                       save_dir=os.path.join(ROOT, "saves"))
    _rooms[rid] = {"session": sess, "name": "默认房间", "created_at": None}
    _active_room_id = rid
    _write_lock(sess)
    atexit.register(_clear_lock)
    threading.Thread(target=lambda: _udp_discover_loop(_room_list), daemon=True).start()
    print("🎭 去中心化跑团主机(房间管理)启动...")
    print(f"📱 房间列表: http://{_lan_ip()}:{PORT}/api/rooms （或客户端一键发现 / 蓝牙接近握手）")
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
