# -*- coding: utf-8 -*-
"""PC 端 API 同步测试：真实起 net.py，推送/拉取模型连接配置（后来者胜）；空 Key 不推送。"""
import sys, os, json, tempfile, shutil, threading, time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import net
import html_app
import app_paths
from werkzeug.serving import make_server

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

save_tmp = tempfile.mkdtemp(prefix="dick_apisd_")
net.SAVES_DIR = os.path.join(save_tmp, "saves")
net.SYNC_SETTINGS_FILE = os.path.join(save_tmp, "sync_settings.json")
net._save_path = lambda cid: os.path.join(net.SAVES_DIR, "x.json")
os.makedirs(net.SAVES_DIR, exist_ok=True)

srv = make_server("127.0.0.1", 0, net.app)
base = "http://127.0.0.1:" + str(srv.server_port)
threading.Thread(target=srv.serve_forever, daemon=True).start()
for _ in range(50):
    try:
        import requests as _rq
        if _rq.get(base + "/api/health", timeout=1).status_code < 400:
            break
    except Exception:
        time.sleep(0.1)

tmp = tempfile.mkdtemp(prefix="dick_apipc_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()   # __init__ 会启一条拉取线程；_ws_sync_enabled=False 时不动作
app._ws_sync_enabled = lambda: True
app._ws_active_server = lambda: base

print("== 推送（真实 HTTP） ==")
payload = {"api_key": "sk-test", "base_url": "https://api.deepseek.com",
           "model": "deepseek-v4-flash", "provider": "deepseek"}
app._ws_push_api_sync(payload)
import requests as _rq
r = _rq.get(base + "/api/sync/api", timeout=3)
check(r.status_code == 200 and r.json().get("api_key") == "sk-test", "服务器已存 API 配置")

print("== 拉取并应用（后来者胜） ==")
app.config["api_key"] = ""
app.config["model"] = ""
ok1 = app._ws_pull_api()
check(ok1 is True, "拉取成功")
check(app.config.get("api_key") == "sk-test", "本地应用了服务器 API Key")
check(app.config.get("model") == "deepseek-v4-flash", "本地应用了模型")

print("== 空 Key 不推送 ==")
calls = []
app._ws_push_api_sync = lambda p: calls.append(p)
app.config["api_key"] = ""
app._ws_push_api()
check(len(calls) == 0, "本地无 Key 时不推送（不覆盖服务器配置）")
app.config["api_key"] = "sk-later"
app._ws_push_api()
time.sleep(0.3)
check(any(c.get("api_key") == "sk-later" for c in calls), "有 Key 时推送")

srv.shutdown()
shutil.rmtree(save_tmp, ignore_errors=True)
shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
