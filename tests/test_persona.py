# -*- coding: utf-8 -*-
"""玩家角色卡精细化：api_get_persona / api_set_persona 结构化往返。"""
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

tmp = tempfile.mkdtemp(prefix="dick_pp_")
_real = app_paths.get_base_dir()
app_paths.get_base_dir = lambda: tmp
app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

# 空 persona
g = app.api_get_persona()
check(g["name"] == "" and all(g[k] == "" or g[k] is None for k in g), "空 persona 全字段为空")

# 结构化保存
p = {"name": "主角", "appearance": "黑发少年", "personality": "沉稳冷静",
     "background": "异世界旅人", "speech": "话少", "first_mes": "……", "notes": "无"}
r = app.api_set_persona(json.dumps(p, ensure_ascii=False))
check(r.get("ok") is True, "set_persona 保存")
g2 = app.api_get_persona()
check(g2["name"] == "主角" and g2["appearance"] == "黑发少年" and g2["personality"] == "沉稳冷静", "字段往返一致")
check(g2["speech"] == "话少" and g2["notes"] == "无", "speech/notes 保留")
# 玩家卡名字 → 聊天显示名（与 _rebuild_messages 同一逻辑）
check((app.persona or {}).get("name") == "主角", "显示名 = 玩家卡名字")
# 改名迁移逻辑（api_set_persona 内部对头像文件的重命名在文件存在时才发生，这里验证无异常）
r3 = app.api_set_persona(json.dumps(dict(p, name="冒险者"), ensure_ascii=False))
check(r3.get("ok") is True and app.api_get_persona()["name"] == "冒险者", "改名保存正常")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
