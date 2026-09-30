# -*- coding: utf-8 -*-
"""角色卡·多存档（新存档功能）回归测试。
运行：python tests/test_save_slots.py
覆盖：①新存档固化进度并设活动指针 ②覆盖保存写入当前进度 ③读档/切换还原对话树+机制状态
      ④重命名 ⑤删除（含活动指针清理） ⑥存档点随卡片落盘（保存/读档/切换一体）"""
import sys, os, json, tempfile, shutil

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import html_app

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

tmp = tempfile.mkdtemp(prefix="dick_saveslots_")
html_app.BASE_DIR = tmp
app = html_app.HtmlApp()

# 带去重：用一套<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌可复现的机制卡
mech = {"mechanics": {
    "affection": {"enabled": True, "min": 0, "max": 100, "initial": 50, "crit": 0.0},
    "status": {"enabled": False, "fields": []},
    "events": [],
}}
fields = {"personality": "安静", "advanced": mech}

def ensure_role(name):
    if not any(r["name"] == name for r in app.roles):
        r = app.api_create_role(name, json.dumps(fields))
        assert r["ok"], r
    app.api_select_roles(json.dumps([name]))

def conv_talk(app, user, asst):
    u = app.core.add_user_message(user)
    app.core.add_assistant_message(asst, parent_id=u)
    app._save_tree()

def card_data(name):
    with open(os.path.join(tmp, "saves", name + ".json"), encoding="utf-8") as f:
        return json.load(f)

print("== ① 新存档固化当前进度 ==")
ensure_role("樱")
# 先讲一句，让进度非零
conv_talk(app, "你好", "你好呀。")
app.core.apply_mechanism_effect({"aff": 40})   # 50 + 40 -> 90
r = app.api_card_save_new("樱", "初见")
check(bool(r.get("ok")), "新存档成功")
sid1 = r["save"]["id"]
check(r["active_save"] == sid1, "新存档设为活动指针")
check(r["save"]["progress"] == 2, "进度=2（去系统节点）")

print("== ② 覆盖保存 ==")
conv_talk(app, "再说一句", "嗯嗯。")
app.core.apply_mechanism_effect({"aff": 10})   # 90 + 10 -> 100
r2 = app.api_card_save("樱", "", sid1)
check(bool(r2.get("ok")), "覆盖保存成功")
check(r2["save"]["id"] == sid1, "写入原存档点")
check(r2["save"]["progress"] == 4, "覆盖后进度=4")
# 卡片落盘应含该存档点
cd = card_data("樱")
check(len(cd.get("saves") or []) == 1, "卡片落盘含 1 个存档点")
check(cd.get("active_save") == sid1, "活动指针已落盘")
check((cd["saves"][0].get("mechanism_state") or {}).get("affection") == 100,
      "覆盖后机制好感=100")

print("== ③ 读档/切换还原 + 再存新档 ==")
r3 = app.api_card_save_new("樱", "重逢")
sid2 = r3["save"]["id"]
check(len(app.api_card_saves("樱")["saves"]) == 2, "已有 2 个存档点")
# 读档回『初见』（affect=100, progress=4）
r4 = app.api_card_save_load("樱", sid1)
check(bool(r4.get("ok")), "读档成功")
check(app.core.mechanism_state and app.core.mechanism_state.get("affection") == 100,
      "读档后机制状态还原（affection=100）")
check(app.api_card_saves("樱")["active_save"] == sid1, "读档后活动指针指向该点")

print("== ④ 重命名 + ⑤ 删除 ==")
r5 = app.api_card_save_rename("樱", sid2, "终章")
check(bool(r5.get("ok")) and r5["save"]["label"] == "终章", "重命名成功")
r6 = app.api_card_save_delete("樱", sid2)
check(bool(r6.get("ok")), "删除成功")
cl = app.api_card_saves("樱")["saves"]
check(len(cl) == 1 and cl[0]["id"] == sid1, "删除后仅剩『初见』")
check(app.api_card_saves("樱")["active_save"] == sid1, "删除非活动点不影响活动指针")

shutil.rmtree(tmp, ignore_errors=True)
print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
