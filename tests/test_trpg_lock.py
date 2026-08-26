# -*- coding: utf-8 -*-
"""会期锁定：跑团 start 锁定 GM+PC 卡（api_update_role/delete_role 被拒），end 解锁。"""
import sys, os, json, tempfile, shutil
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import html_app, app_paths
from plugins.trpg_plugin import TrpgPlugin

ok = bad = 0
def check(c, m):
    global ok, bad
    if c: ok += 1; print("  OK " + m)
    else: bad += 1; print("  FAIL " + m)

tmp = tempfile.mkdtemp(prefix="dick_trpglock_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()
for nm in ["GM", "凛", "咲", "路人"]:
    app.api_create_role(nm, json.dumps({"personality": "理性"}))

p = TrpgPlugin(None)
p.on_command("trpg", "gm GM")
p.on_command("trpg", "pc 凛")
p.on_command("trpg", "pc 咲")

print("== 锁定前可改 ==")
r = app.api_update_role("凛", json.dumps({"personality": "冷静"}))
check(r.get("ok") is True, "锁定前可改 凛")

print("== start 锁定 ==")
p.on_command("trpg", "start")
check(os.path.exists(os.path.join(tmp, "saves", ".trpg_lock.json")), "锁定文件已生成")

print("== 锁定后改/删被拒 ==")
r = app.api_update_role("凛", json.dumps({"personality": "狂热"}))
check(r.get("ok") is False and "锁定" in (r.get("err") or ""), "update 被拒: %s" % r)
r = app.api_delete_role("凛")
check(r.get("ok") is False and "锁定" in (r.get("err") or ""), "delete 被拒: %s" % r)
# 未锁定角色（不在队伍）仍可改
r = app.api_update_role("路人", json.dumps({"personality": "陌生"}))
check(r.get("ok") is True, "未锁定卡仍可改")

print("== end 解锁 ==")
p.on_command("trpg", "end")
check(not os.path.exists(os.path.join(tmp, "saves", ".trpg_lock.json")), "锁定文件已清除")
r = app.api_update_role("凛", json.dumps({"personality": "深情"}))
check(r.get("ok") is True, "解锁后可改")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
