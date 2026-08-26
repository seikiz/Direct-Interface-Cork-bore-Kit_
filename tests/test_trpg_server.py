# -*- coding: utf-8 -*-
"""局域网剧情跑团主机测试：状态/设置/加入/行动→GM叙述→轮换（LLM 用 mock）。"""
import sys, os, json
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import trpg_server as ts

ok = bad = 0
def check(c, m):
    global ok, bad
    if c: ok += 1; print("  OK " + m)
    else: bad += 1; print("  FAIL " + m)

# 隔离状态 + mock LLM
ts._conf = {"api_key": "test", "base_url": "http://x", "model": "m"}
ts._gm = "菲悠"
ts._pcs = ["凛", "咲"]
ts._turn = "凛"
ts._story = []
ts._joined = {}
ts._llm = lambda system, user: "（GM 叙述）夜色沉下来，凛推开了那扇门——里面仿佛有个世界在等待。你可以：① 走进去 ② 转身离开 ③ 敲门示警"

c = ts.app.test_client()

print("== 状态 ==")
r = c.get("/api/state").get_json()
check(r["gm"] == "菲悠" and r["pcs"] == ["凛", "咲"] and r["turn"] == "凛", "state 返回 gm/pcs/turn")
check(r["story"] == [] and r["joined"] == {}, "初始 story/joined 为空")

print("== 控制台页面 ==")
check(c.get("/").status_code == 200, "GET / 返回控制台页")

print("== 加入 ==")
check(c.post("/api/join", json={"name": "凛", "player": "阿明"}).get_json()["ok"] is True, "加入凛")
check(c.post("/api/join", json={"name": "路人"}).status_code == 400, "非队伍角色被拒")

print("== 行动 → GM 叙述 → 轮换 ==")
r = c.post("/api/act", json={"actor": "凛", "action": "推门"}).get_json()
check(r["ok"] is True, "act 成功")
check("GM 叙述" in r["gm"], "返回 GM 叙述")
check(r["turn"] == "咲", "行动者轮换到咲")
check(len(ts._story) == 1 and ts._story[0]["actor"] == "凛", "剧情日志已记录")

print("== 空行动被拒 ==")
check(c.post("/api/act", json={"actor": "凛", "action": ""}).status_code == 400, "空行动 400")

print("== setup 换配置 ==")
r = c.post("/api/setup", json={"gm": "咲", "pcs": ["凛", "咲", "小"]}).get_json()
check(r["ok"] is True and r["turn"] == "凛", "setup 更新 GM/PC 并重置行动者")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
