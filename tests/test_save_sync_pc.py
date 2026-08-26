# -*- coding: utf-8 -*-
"""PC 端树存档同步测试：_save_tree 盖时间戳+推送；_ws_pull_tree 服务器更新则采用/旧则不采用；
api_select_roles 触发拉取（网络部分伪造，不连真实服务器）。"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import html_app
import app_paths

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

tmp = tempfile.mkdtemp(prefix="dick_syncp_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp

app = html_app.HtmlApp()
# 初始化阶段：同步关闭，避免连任何服务器
app._ws_sync_enabled = lambda: False
check(bool(app.api_create_role("同步测试", json.dumps({"personality": "理性"}))["ok"]), "创建角色")
app.api_select_roles(json.dumps(["同步测试"]))

# 造一点对话，让树非空
u = app.core.add_user_message("第一条")
a = app.core.add_assistant_message("你好呀，我是佐仓绫音。", parent_id=u)

# --- _save_tree：盖时间戳 + 触发推送 ---
pushed = []
app._ws_save_upload = lambda cid, tree: pushed.append((cid, dict(tree)))
app._ws_sync_enabled = lambda: True
app._save_tree()
rd = next(r for r in app.roles if r["name"] == "同步测试")
check(("data" in rd and "_tree_ts" in (rd.get("data") or {})), "本地存档盖了 _tree_ts")
check(any(c[0] == "同步测试" for c in pushed), "_save_tree 触发推送（角色名）")

# --- _ws_pull_tree：服务器更新则采用 ---
server_tree = app.core.get_all_nodes_data()
rd["data"]["_tree_ts"] = "2000-01-01T00:00:00+00:00"   # 故意改旧
app._ws_save_fetch = lambda cid: {"ts": "2999-01-01T00:00:00+00:00", "tree": server_tree}
ok1 = app._ws_pull_tree("同步测试")
check(ok1 is True, "服务器更新：采用服务器版本")
check((rd["data"].get("history_tree") or {}).get("current_leaf_id") == a, "本地树被替换为服务器树")

# --- _ws_pull_tree：服务器旧则不动 ---
app._ws_save_fetch = lambda cid: {"ts": "1999-01-01T00:00:00+00:00", "tree": server_tree}
ok2 = app._ws_pull_tree("同步测试")
check(ok2 is False, "服务器旧版本：不采用")

# --- api_select_roles 触发拉取 ---
pulled = []
app._ws_pull_tree = lambda name: pulled.append(name) or True
app.api_select_roles(json.dumps(["同步测试"]))
check(any(n == "同步测试" for n in pulled), "api_select_roles 触发拉取该角色")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
