# -*- coding: utf-8 -*-
"""net.py 同步设置 + 局域网自动发现测试。
- /api/sync/api 存/取共享 API 码配置
- UDP 发现线程：收 DISCOVER_MAGIC 回自身 IP + HTTP 端口"""
import sys, os, json, tempfile, shutil, socket, threading, time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import net

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

tmp = tempfile.mkdtemp(prefix="dick_syncset_")
net.SAVES_DIR = os.path.join(tmp, "saves")
net.SYNC_SETTINGS_FILE = os.path.join(tmp, "sync_settings.json")
net._save_path = lambda cid: os.path.join(net.SAVES_DIR,
    (cid or "unknown").strip().replace("/", "_").replace("\\", "_").replace("..", "_")[:80] + ".json")
os.makedirs(net.SAVES_DIR, exist_ok=True)
client = net.app.test_client()

print("== /api/sync/api 存/取 ==")
api = {"api_key": "sk-test", "base_url": "https://api.deepseek.com", "model": "deepseek-v4-flash"}
r = client.post("/api/sync/api", json=api)
check(r.status_code == 200 and r.get_json().get("ok") is True, "保存 API 配置")
r2 = client.get("/api/sync/api")
d = r2.get_json()
check(d.get("api_key") == "sk-test" and d.get("base_url") == "https://api.deepseek.com", "取回 API 配置")
# 覆盖（后来者胜）
client.post("/api/sync/api", json={"api_key": "sk-new"})
check(client.get("/api/sync/api").get_json().get("api_key") == "sk-new", "后来者胜覆盖")

print("== UDP 局域网自动发现 ==")
# 挑一个空闲 UDP 端口
probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
probe.bind(("127.0.0.1", 0))
free_port = probe.getsockname()[1]
probe.close()
net.DISCOVER_PORT = free_port
threading.Thread(target=net._udp_discover_loop, daemon=True).start()
time.sleep(0.2)

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(3)
s.sendto(net.DISCOVER_MAGIC, ("127.0.0.1", free_port))
try:
    data, addr = s.recvfrom(1024)
    d = json.loads(data.decode("utf-8"))
    check(d.get("service") == "dick-sync", "回包带 service=dick-sync")
    check(d.get("port") == net.PORT, "回包带 HTTP 端口 %s" % d.get("port"))
    check(addr[0] == "127.0.0.1", "回包来源地址可识别")
except socket.timeout:
    check(False, "未收到发现回包")
finally:
    s.close()

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
