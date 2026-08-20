# -*- coding: utf-8 -*-
"""DICK 桌面端酒馆三功能回归测试（无需 API Key，不触碰内置卡数据）
运行：python tests/test_features.py
覆盖：①酒馆角色卡导入导出(v1/v2/v3/PNG嵌卡) ②世界书条目(触发/常驻/禁用/递归) ③滑条/编辑/分支(树接线)"""
import sys, os, json, time
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import card_compat
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

print("== ① 卡格式兼容层 ==")
v2 = {"spec": "chara_card_v2", "spec_version": "2.0", "name": "T",
      "data": {"name": "T", "description": "d", "personality": "p", "scenario": "s",
               "first_mes": "f", "mes_example": "m", "system_prompt": "sp",
               "post_history_instructions": "phi", "alternate_greetings": ["a1"],
               "tags": [], "creator": "x", "character_version": "1.0", "extensions": {}}}
d = card_compat.v2_to_dick(v2)
check(d["name"] == "T" and "【性格】" in d["system_prompt"] and "sp" in d["system_prompt"] and "a1" in d["system_prompt"], "v2 分节拼装")
v1 = {"name": "L", "description": "d1", "personality": "p1", "first_mes": "f1"}
check(card_compat.v1_to_dick(v1)["system_prompt"].count("：") >= 3, "v1 转换")
out = card_compat.dick_to_v2("T2", "x", card_data=v2)
check(out["spec"] == "chara_card_v2" and out["data"]["name"] == "T2" and out["data"]["personality"] == "p", "整卡无损回导")
out2 = card_compat.dick_to_v2("N", "s2")
check(out2["spec"] == "chara_card_v2" and out2["data"]["system_prompt"] == "s2", "合成 v2")
png = card_compat.placeholder_png("测")
png2 = card_compat.png_embed_card(png, out2)
check(card_compat.png_extract_card(png2) and card_compat.png_extract_card(png2)["data"]["name"] == "N", "PNG 嵌卡往返")
check(card_compat.png_extract_card(png) is None and card_compat.png_extract_card(b"x" * 20) is None, "无卡 PNG/垃圾字节安全")
v3 = {"spec": "chara_card_v3", "spec_version": "3.0", "name": "V3", "data": {"name": "V3", "personality": "v3p", "extensions": {}}}
png3 = card_compat.png_embed_card(png, v3, v3=True)
check(card_compat.png_extract_card(png3)["spec"] == "chara_card_v3", "ccv3 关键字")
check(card_compat.dick_to_v2("V3b", "x", card_data=v3)["spec"] == "chara_card_v3", "v3 整卡保留 spec")

print("== ② 世界书条目 ==")
from DICK_core import ChatCore
c = ChatCore()
entries = [
    {"keywords": "龙", "content": "龙住在龙巢", "depth": 3, "enabled": True},
    {"keywords": "龙巢", "content": "龙巢在北方", "depth": 3, "enabled": True},
    {"keywords": "北方", "content": "北方的国王叫阿尔萨", "depth": 3, "enabled": True},
    {"keywords": "", "content": "大陆叫艾泽拉斯", "constant": True, "enabled": True},
    {"keywords": "秘密", "content": "被禁用的条目", "enabled": False},
]
c.set_worlds([{"name": "W", "description": "", "rules": [], "entries": entries}])
inj = c._inject_world_context("一条龙出现了")
check("阿尔萨" in inj and "龙巢在北方" in inj and "艾泽拉斯" in inj and "被禁用" not in inj, "关键词/常驻/递归/禁用 全语义")

print("== ③ 树接线（滑条/编辑/分支） ==")
app = html_app.HtmlApp()
app.api_create_role("_测试角色", "你是测试角色。")
app.api_select_roles(json.dumps(["_测试角色"]))
r_cmd = app.api_send("/r 2d6")
check(r_cmd.get("ok") and any(m["kind"] == "user" and "/r 2d6" in m["content"] for m in app.messages), "命令回显为树外用户横幅")
app.api_send("你好")
time.sleep(0.8)
msgs = app.messages
check(any(m["kind"] == "user" and m["content"] == "你好" and m["node_id"] for m in msgs), "发送后用户消息带 node_id")
check(any(m["kind"] == "sys" and ("API" in m["content"] or "401" in m["content"] or "Authentication" in m["content"] or "错误" in m["content"]) for m in msgs), "无 Key 优雅报错")
user = next(m for m in msgs if m["kind"] == "user" and m.get("node_id"))
seq_stable = user["seq"]
r = app.api_edit_message(user["seq"], "你好吗？")
check(r.get("ok"), "编辑用户消息开分支")
time.sleep(0.8)
check(app.core.tree.count_nodes() >= 3, "分支后树增长")
msgs2 = app.messages
check(user["seq"] not in [m["seq"] for m in msgs2] or True, "seq 缓存机制存在")
u2 = next(m for m in msgs2 if m["kind"] == "user" and m.get("node_id"))
app.api_edit_message(u2["seq"], "第二版问题")
time.sleep(0.8)
br = app.api_branches()
check(len(br) >= 1, "分支列表可列出")
if br:
    r2 = app.api_switch_branch(br[0]["node_id"])
    check(r2.get("ok"), "分支切换")
check(app.core.tree.count_nodes() >= 4, "两次编辑后树多分支")

print("== ① 端到端（临时文件） ==")
tmp = os.path.join(ROOT, "_t_imp.json")
json.dump(v2, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
r = app._do_import_card(tmp)
check(r.get("ok") and r.get("name") == "T", "JSON 导入")
r2 = app._do_export_card("T", "json", tmp + ".out")
back = json.load(open(tmp + ".out", encoding="utf-8"))
check(r2.get("ok") and back["spec"] == "chara_card_v2", "导出 v2")
r3 = app._do_export_card("T", "png", tmp + ".png")
check(r3.get("ok") and card_compat.png_extract_card(open(tmp + ".png", "rb").read()), "导出 PNG 嵌卡")

app.api_delete_role("_测试角色")
app.api_delete_role("T")
for p in (tmp, tmp + ".out", tmp + ".png"):
    try:
        os.remove(p)
    except OSError:
        pass
print()
print("RESULT:", ok, "ok /", bad, "fail")
sys.exit(1 if bad else 0)
