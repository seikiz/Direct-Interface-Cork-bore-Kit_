# -*- coding: utf-8 -*-
"""twin_http.py —— 双子模式的服务端接口（Flask 蓝图，单独成文件）。

为什么单独一个文件：net.py 已经 1438 行、顶在 1000 行闸门的豁免上限边上，
往里加接口就会破棘轮。双子这块是**新功能**，本来就该独立。

三个接口：
    GET /api/node  这台是谁：node_id / port / data_dir / 启动时间 / 运行时长
    GET /api/twin  这台 + 伙伴们的健康（用 /api/node 探，2 秒超时）
    GET /api/health 活着就 200（客户端也用这个做快速探测）

注册方式（net.py 里两行）：
    from twin_http import register_twin_routes
    register_twin_routes(app)
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.request

from flask import jsonify

import twin as twin_mod

STARTED_AT = time.time()


def _node_id():
    """节点标识：优先 env，其次 主机名:端口，最后 hostname。"""
    env = os.environ.get("WORKSHOP_NODE_ID", "").strip()
    if env:
        return env
    port = os.environ.get("WORKSHOP_PORT", "")
    host = os.environ.get("WORKSHOP_HOST", "")
    try:
        name = socket.gethostname()
    except Exception:
        name = "node"
    return "%s:%s" % (name, port or (host or "?"))


def _peers():
    """伙伴地址（逗号分隔）。服务端只做展示/探测，不做转发。"""
    return twin_mod.parse_list(os.environ.get("WORKSHOP_PEERS", ""))


def _probe(url, timeout=2.0):
    """探一台服务器的 /api/node；返回 (ok, payload)。"""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/api/node",
                                     headers={"User-Agent": "dick-twin/1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False, {"status": resp.status}
            raw = resp.read(4096).decode("utf-8", "replace")
        return True, json.loads(raw or "{}")
    except Exception as e:
        return False, {"err": str(e)[:120]}


def register_twin_routes(app, data_dir=None):
    """把双子接口挂到 app 上。data_dir 由调用方传（net.py 知道自己的数据目录）。"""
    pool = twin_mod.TwinPool(_peers(), state_file=None)

    @app.route("/api/health", methods=["GET"])
    def _twin_health():
        return jsonify({"ok": True, "node": _node_id(), "uptime": int(time.time() - STARTED_AT)})

    @app.route("/api/node", methods=["GET"])
    def _twin_node():
        return jsonify({
            "ok": True,
            "node": _node_id(),
            "host": os.environ.get("WORKSHOP_HOST", "0.0.0.0"),
            "port": os.environ.get("WORKSHOP_PORT", ""),
            "data_dir": data_dir or "",
            "started_at": int(STARTED_AT),
            "uptime": int(time.time() - STARTED_AT),
        })

    @app.route("/api/twin", methods=["GET"])
    def _twin_status():
        nodes = []
        for url in pool.servers:
            ok, payload = _probe(url)
            pool.report(url, ok)
            nodes.append({"url": url, "ok": ok, "node": payload.get("node", ""),
                          "uptime": payload.get("uptime", 0),
                          "err": "" if ok else payload.get("err", "")})
        snap = pool.snapshot()
        snap["self"] = {"node": _node_id(), "uptime": int(time.time() - STARTED_AT)}
        snap["nodes"] = nodes or snap["nodes"]
        return jsonify(snap)
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌