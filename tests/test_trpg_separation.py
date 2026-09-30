# -*- coding: utf-8 -*-
"""跑团会期锁 与 存档/导入 隔离测试：
1) _load_roles 不把 .trpg_lock.json 当角色卡加载/修复
2) save_guard.sweep 跳过 .trpg_lock.json（不校验/修复/备份/污染它）
3) _save_tree 对被锁卡不写记忆树、不推送
4) _ws_pull_tree 对被锁卡不覆盖（返回 False）
5) trpg_server._write_lock 写锁、_clear_lock 清锁（与插件锁文件同格式）
"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import html_app
import app_paths
import save_guard

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

tmp = tempfile.mkdtemp(prefix="dick_trpgsep_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp

saves = os.path.join(tmp, "saves")
os.makedirs(saves, exist_ok=True)
lock_path = os.path.join(saves, ".trpg_lock.json")
lock_content = {"locked": ["凛", "咲"], "gm": "咲", "pcs": ["凛", "咲"]}
with open(lock_path, "w", encoding="utf-8") as f:
    json.dump(lock_content, f, ensure_ascii=False)
# 一张普通角色卡（确保<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌保存目录里有真实卡）
app = html_app.HtmlApp()
app._ws_sync_enabled = lambda: False
check(bool(app.api_create_role("凛", json.dumps({"personality": "凛设定"}))["ok"]), "创建角色卡 凛")
# 此时 lock 文件已存在，_load_roles 应当跳过它（没有来自 lock 的幻影角色）
check(all(r["name"] in ("凛",) for r in app.roles), "角色列表不含锁文件的幻影角色")
# 锁文件不被 load/sweep 污染（没被加上 name/system_prompt）
with open(lock_path, "r", encoding="utf-8") as f:
    after_load = json.load(f)
check("locked" in after_load and "name" not in after_load and "system_prompt" not in after_load,
      "锁文件未被当成角色卡修复/污染")

# --- 2) sweep 跳过锁文件 ---
s = save_guard.sweep(tmp)
with open(lock_path, "r", encoding="utf-8") as f:
    after_sweep = json.load(f)
check(after_sweep == lock_content, "sweep 后锁文件内容不变（未被当存档处理）")
check(not any(".trpg_lock" in l for l in s["logs"]), "sweep 无锁文件修复/备份日志")

# --- 3) _save_tree 对被锁卡不写、不推送 ---
app.api_select_roles(json.dumps(["凛"]))
# 让树非空
u = app.core.add_user_message("测试行动")
a = app.core.add_assistant_message("GM 叙述。", parent_id=u)
pushed = []
app._ws_save_upload = lambda cid, tree: pushed.append((cid, dict(tree)))
app._ws_sync_enabled = lambda: True
# 用锁文件锁住「凛」：注意上面 api_create_role 的卡名是「凛」，重新写锁确保命中
with open(lock_path, "w", encoding="utf-8") as f:
    json.dump({"locked": ["凛"], "gm": "", "pcs": []}, f, ensure_ascii=False)
rd = next(r for r in app.roles if r["name"] == "凛")
before_tree = rd.get("data", {}).get("history_tree")
app._save_tree()
check(len(pushed) == 0, "_save_tree 对被锁卡不触发推送")
with open(os.path.join(saves, "凛.json"), "r", encoding="utf-8") as f:
    on_disk = json.load(f)
check("history_tree" not in on_disk or on_disk["history_tree"] == before_tree,
      "_save_tree 未覆盖被锁卡的记忆树")

# --- 4) _ws_pull_tree 对被锁卡返回 False ---
app._ws_save_fetch = lambda cid: {"ts": "2999-01-01T00:00:00+00:00", "tree": app.core.get_all_nodes_data()}
ok4 = app._ws_pull_tree("凛")
check(ok4 is False, "_ws_pull_tree 对被锁卡返回 False（不覆盖）")

# --- 5) trpg_server 写锁/清锁（去中心化：用引擎实例） ---
import trpg_server as ts
from trpg_session import TrpgSession
ts.ROOT = tmp
_s = TrpgSession(gm="咲", pcs=["凛"])
ts._write_lock(_s)
check(os.path.exists(lock_path), "trpg_server 已写锁文件")
with open(lock_path, "r", encoding="utf-8") as f:
    lk = json.load(f)
check(lk.get("locked") == ["咲", "凛"] and lk.get("gm") == "咲", "锁文件格式与插件一致（locked=[gm]+pcs）")
ts._clear_lock()
check(not os.path.exists(lock_path), "trpg_server 已清锁文件")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
