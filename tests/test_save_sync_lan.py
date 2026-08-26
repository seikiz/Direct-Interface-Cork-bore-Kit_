# -*- coding: utf-8 -*-
"""局域网直连同步测试：真实起 net.py (随机端口)，PC 走 requests 推/拉，
验证 /api/save 端到端（含拉取采用/旧版本不采用）。"""
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

# 隔离服务器数据目录，避免污染
save_tmp = tempfile.mkdtemp(prefix="dick_lan_srv_")
net.SAVES_DIR = os.path.join(save_tmp, "saves")
os.makedirs(net.SAVES_DIR, exist_ok=True)
net._save_path = lambda cid: os.path.join(net.SAVES_DIR,
    (cid or "unknown").strip().replace("/", "_").replace("\\", "_").replace("..", "_")[:80] + ".json")

# 在随机端口起动真实服务器
srv = make_server("127.0.0.1", 0, net.app)
port = srv.server_port
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"
# 等 server 就绪
for _ in range(50):
    try:
        import requests as _rq
        if _rq.get(base + "/api/health", timeout=1).status_code < 400:
            break
    except Exception:
        time.sleep(0.1)

# PC（html_app）：配置工坊地址为该服务器，并让它优先用这个地址（避免探测隧道）
tmp = tempfile.mkdtemp(prefix="dick_lan_pc_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()
app._ws_active_server = lambda: base   # 直连本服务器，不探测隧道

check(bool(app.api_create_role("角色A", json.dumps({"personality": "理性"}))["ok"]), "创建角色")
app.api_select_roles(json.dumps(["角色A"]))
app._ws_sync_enabled = lambda: True

tree = app.core.get_all_nodes_data()
# 造一点对话
u = app.core.add_user_message("你好")
a = app.core.add_assistant_message("你好呀，我是咲。", parent_id=u)
tree = app.core.get_all_nodes_data()

print("== 推送（真实 HTTP → net.py） ==")
d_ok, d_ts = app._ws_save_upload("角色A", tree)
check(d_ok is True and bool(d_ts), "上传成功并返回时间戳")

print("== 拉取（真实 HTTP） ==")
fetched = app._ws_save_fetch("角色A")
check(fetched is not None and isinstance(fetched.get("tree"), dict), "拉取成功")
check(fetched["tree"]["current_leaf_id"] == a, "拉取树内容正确")
check(app._ws_save_fetch("不存在的角色") is None, "无存档返回 None")

print("== 采用服务器新版本（局域网续聊场景） ==")
rd = next(r for r in app.roles if r["name"] == "角色A")
rd["data"]["_tree_ts"] = "2000-01-01T00:00:00+00:00"   # 本地故意改旧
ok1 = app._ws_pull_tree("角色A")
check(ok1 is True, "服务器更新：采用服务器版本")
check((rd["data"]["history_tree"] or {}).get("current_leaf_id") == a, "本地树替换为服务器树")

app._ws_save_fetch = lambda cid: {"ts": "1999-01-01T00:00:00+00:00", "tree": tree}
ok2 = app._ws_pull_tree("角色A")
check(ok2 is False, "服务器旧版本：不采用")

srv.shutdown()
shutil.rmtree(save_tmp, ignore_errors=True)
shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
