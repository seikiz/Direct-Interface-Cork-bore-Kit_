# -*- coding: utf-8 -*-
"""状态变量 README 一致性测试：验证文档描述的标签/变量与实现完全一致。
覆盖：aff 百分比、ph 玩家HP、int 相对/绝对、enum 赋值、roll 档位、战斗公式变量。
运行：python tests/test_state_readme.py"""
import sys, os, json

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from DICK_core import ChatCore

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

MECH = {
    "affection": {"enabled": True, "initial": 50, "min": 0, "max": 100, "crit": 0.0},
    "status": {"enabled": True, "fields": [
        {"key": "mood", "name": "心情", "type": "enum",
         "initial": "平静", "options": ["平静", "开心", "生气"]},
        {"key": "energy", "name": "体力", "type": "int", "initial": 100, "min": 0, "max": 100},
    ]},
}
BATTLE = {
    "enabled": True,
    "attrs": {"hp": {"label": "生命", "initial": 100, "max": 100},
              "atk": {"label": "攻击", "initial": 10},
              "def": {"label": "防御", "initial": 5}},
    "formulas": {"damage": "player_atk * 2 - def", "crit_chance": "0.0", "crit_mult": "2"},
    "moves": [{"id": "fire", "name": "火球术", "formula": "player_atk * 3 - def"}],
}
PB = {"enabled": True, "attrs": {"hp": {"label": "生命", "initial": 100, "max": 100},
                                  "atk": {"label": "攻击", "initial": 20},
                                  "def": {"label": "防御", "initial": 8}}}

def make_core():
    c = ChatCore()
    c.set_active_roles([{"name": "测试", "system_prompt": "x", "unlocked": False,
                         "advanced": {"mechanics": MECH, "battle": BATTLE}}])
    c.set_player_persona({"name": "勇者", "advanced": {"battle": PB}})
    return c

print("== ① 好感度百分比 ==")
c = make_core()
c.strip_mechanism_tags("[aff:+5] 微笑", apply=True)
check(c.mechanism_state["affection"] == 55, "[aff:+5] 上限100 → 55（5%=5点）")
c.strip_mechanism_tags("[aff:-3]", apply=True)
check(c.mechanism_state["affection"] == 52, "[aff:-3] → 52")
c.strip_mechanism_tags("[aff:+100]", apply=True)
check(c.mechanism_state["affection"] == 100, "[aff:+100] → 拉满 100")

print("== ② 1314 上限百分比 ==")
MECH2 = json.loads(json.dumps(MECH))
MECH2["affection"]["max"] = 1314
c2 = ChatCore()
c2.set_active_roles([{"name": "测试", "system_prompt": "x", "unlocked": False,
                      "advanced": {"mechanics": MECH2}}])
c2.strip_mechanism_tags("[aff:+5]", apply=True)
# 1314 的 5% = 65.7 → round = 66（文档说 65.7→66）
check(c2.mechanism_state["affection"] == 50 + round(1314 * 5 / 100),
      "[aff:+5] 上限1314 → 50+66=116（5pct=65.7→66）实际 %d" % c2.mechanism_state["affection"])

print("== ③ 玩家 HP（ph 标签） ==")
c3 = make_core()
c3.strip_mechanism_tags("[ph:-10] 被打", apply=True)
check(c3.mechanism_state["player"]["hp"] == 90, "[ph:-10] 玩家 hp 100→90")
c3.strip_mechanism_tags("[ph:+15]", apply=True)
check(c3.mechanism_state["player"]["hp"] == 105, "[ph:+15] 玩家 hp 90→105")

print("== ④ int 状态：绝对 + 相对 ==")
c4 = make_core()
c4.strip_mechanism_tags("[energy:80] 跑完步", apply=True)
check(c4.mechanism_state["status"]["energy"] == 80, "[energy:80] 绝对赋值")
c4.strip_mechanism_tags("[energy:-10]", apply=True)
check(c4.mechanism_state["status"]["energy"] == 70, "[energy:-10] 相对减")
c4.strip_mechanism_tags("[energy:+5]", apply=True)
check(c4.mechanism_state["status"]["energy"] == 75, "[energy:+5] 相对加")

print("== ⑤ enum 状态：直接赋值 ==")
c5 = make_core()
c5.strip_mechanism_tags("[mood:开心] 她笑了", apply=True)
check(c5.mechanism_state["status"]["mood"] == "开心", "[mood:开心] 枚举赋值")

print("== ⑥ 战斗公式变量 ==")
c6 = make_core()
txt, _ = c6.resolve_battle_move("fire")
# fire: player_atk*3 - def = 20*3 - 5 = 55
check(txt is not None and "55" in txt, "fire 公式 player_atk*3-def = 55（player_atk=20, def=5）: %s" % (txt or ""))
check(c6.mechanism_state["status"]["hp"] == 45, "敌方 hp 100→45")

print("== ⑦ ROLL 档位（文档六） ==")
import html_app
from unittest import mock
app = html_app.HtmlApp()
item = {"text": "x", "aff": 3}
with mock.patch("random.random", return_value=0.000005):
    eff, kind, note = app._roll_option(item)
check(kind == "collapse", "坍缩档（十万分之一）")
with mock.patch("random.random", return_value=0.0005):
    eff, kind, note = app._roll_option(item)
check(kind == "chosen", "天选档（千分之一）")
with mock.patch("random.random", return_value=0.1):
    eff, kind, note = app._roll_option(item)
check(kind == "crit" and eff["aff"] == 6, "暴击档（aff×2）")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
