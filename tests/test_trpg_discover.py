# -*- coding: utf-8 -*-
"""局域网跑团发现测试：主机广播 + 客户端 discover() 一键扫到。
适配 TrpgSession 引擎：构造实例并作为 ts._session + 传给发现线程。"""
import sys, os, socket, threading, time, json
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import trpg_server as ts
from trpg_session import TrpgSession
from plugins.trpg_plugin import TrpgPlugin

ok = bad = 0
def check(c, m):
    global ok, bad
    if c: ok += 1; print("  OK " + m)
    else: bad += 1; print("  FAIL " + m)

# 挑一个空闲 UDP 端口
probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
probe.bind(("127.0.0.1", 0))
free_port = probe.getsockname()[1]
probe.close()

# 用引擎实例 + 该端口跑主机发现线程（多房间：rooms_getter 返回列表）
ts.DISCOVER_PORT = free_port
sess = TrpgSession(gm="菲悠", pcs=["凛","咲"])
ts._rooms.clear(); ts._rooms["t1"] = {"session": sess, "name": "测试房", "created_at": None}
threading.Thread(target=ts._udp_discover_loop, args=(ts._room_list,), daemon=True).start()
time.sleep(0.2)

print("== 客户端 discover() 一键发现 ==")
found = TrpgPlugin.discover(free_port, timeout=2.0)
check(len(found) >= 1, "扫到至少 1 个主机: %d" % len(found))
if found:
    d = found[0]
    check(d.get("service") == "trpg", "service=trpg")
    check(":" in d.get("url", ""), "url 含端口")
    check(d.get("gm") == "菲悠", "识别 GM")
    check(d.get("host_ip"), "带 host_ip")

print("== 无主机时返回空 ==")
empty = TrpgPlugin.discover(free_port + 100, timeout=0.8)
check(empty == [], "扫不到则返回空列表")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
