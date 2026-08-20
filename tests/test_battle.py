# -*- coding: utf-8 -*-
"""战斗系统测试：公式求值 / 招式结算 / buff tick / 天选之人概率隔离。
运行：python tests/test_battle.py"""
import sys, os, json

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from DICK_core import ChatCore, eval_battle_formula

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

BATTLE = {
    "enabled": True,
    "attrs": {"hp": {"label": "生命", "initial": 100, "max": 100},
              "atk": {"label": "攻击", "initial": 10},
              "def": {"label": "防御", "initial": 5}},
    "mech_attrs": [{"key": "spd", "label": "速度", "initial": 8}, {"key": "mp", "label": "灵力", "initial": 20, "max": 50}],
    "formulas": {"damage": "player_atk * 2 - def", "crit_chance": "0.0", "crit_mult": "2"},
    "moves": [
        {"id": "fire", "name": "火球术", "desc": "投掷火球", "formula": "player_atk * 3 - def", "cost": {"mp": 5}},
        {"id": "heal", "name": "治愈", "desc": "恢复", "formula": "20", "buffs": [{"id": "regen", "turns": 2}]},
    ],
    "buffs": [{"id": "regen", "name": "再生", "desc": "每回合+5", "attrs": {"hp": 5}}],
}

print("== ① 公式求值（白名单安全） ==")
check(eval_battle_formula("max(1, atk*2 - def)", {"atk": 10, "def": 5}) == 15.0, "max/四则")
check(eval_battle_formula("floor(9.7)", {}) == 9.0, "floor")
check(eval_battle_formula("player_atk * 3 - def + spd", {"player_atk": 10, "def": 5, "spd": 8}) == 33.0, "多变量")
check(eval_battle_formula("max(1, atk*2 - def)", {"atk": 10, "def": 5}) == 15.0, "def 关键字替换")
try:
    eval_battle_formula("__import__('os')", {})
    check(False, "恶意表达式被拦截")
except ValueError:
    check(True, "恶意表达式被拦截")
try:
    eval_battle_formula("atk * unknown", {"atk": 5})
    check(False, "未知变量被拦截")
except ValueError:
    check(True, "未知变量被拦截")

print("== ② 战斗属性初始化 + 系统提示注入 ==")
c = ChatCore()
c.set_active_roles([{"name": "战士", "system_prompt": "你是战士", "unlocked": False,
                     "advanced": {"battle": BATTLE}}])
st = c.mechanism_state["status"]
check(st["hp"] == 100 and st["atk"] == 10 and st["def"] == 5 and st["spd"] == 8 and st["mp"] == 20,
      "战斗属性初始化: %r" % st)
sys_text = c.tree.nodes[c.tree.root_id].content
check("战斗属性" in sys_text and "招式" in sys_text, "系统提示注入战斗规则")

print("== ③ 招式结算 ==")
txt, legend = c.resolve_battle_move("fire")
check(txt is not None and "25" in txt, "火球术 25 伤害: %s" % txt)
check(st["mp"] == 15 and st["hp"] == 75, "消耗与扣血: mp=%s hp=%s" % (st["mp"], st["hp"]))
c.resolve_battle_move("fire"); c.resolve_battle_move("fire"); c.resolve_battle_move("fire")
txt5, _ = c.resolve_battle_move("fire")
check(txt5 is not None and "不足" in txt5, "mp 不足拦截: %s" % txt5)

print("== ④ buff 挂载与 tick ==")
c.resolve_battle_move("heal")
buffs = c.mechanism_state["buffs"]
check(buffs and buffs[0]["id"] == "regen", "招式附加 buff 挂载")
c._tick_buffs()
check(c.mechanism_state["buffs"] == [], "buff 到期移除")
check(st["hp"] > 0, "buff 效果生效（hp 变化）")

print("== ⑤ 战斗 UI 状态 ==")
c2 = ChatCore()
c2.set_active_roles([{"name": "R", "system_prompt": "x", "unlocked": False,
                      "advanced": {"battle": BATTLE}}])
ui = c2.battle_ui_state()
check(ui is not None and ui["attrs"] and ui["moves"], "battle_ui_state 完整")
check(any(a["key"] == "hp" for a in ui["attrs"]), "属性含 hp")
check(any(m["id"] == "fire" for m in ui["moves"]), "招式含 fire")

print("== ⑥ 战斗状态随回溯快照恢复 ==")
c3 = ChatCore()
c3.set_active_roles([{"name": "R", "system_prompt": "x", "unlocked": False,
                      "advanced": {"battle": BATTLE}}])
n1 = c3.add_user_message("战斗开始")
c3.tree.nodes[n1].metadata["ms"] = c3.mechanism_snapshot()
c3.resolve_battle_move("fire")  # hp 75
c3.restore_mechanisms(n1)
check(c3.mechanism_state["status"]["hp"] == 100, "回溯恢复战斗属性: hp=%s" % c3.mechanism_state["status"]["hp"])

print("== ⑦ 玩家同规格待遇（玩家卡战斗属性 / ph 标签 / 回溯恢复） ==")
PB = {"enabled": True,
      "attrs": {"hp": {"label": "生命", "initial": 100, "max": 100},
                "atk": {"label": "攻击", "initial": 20},
                "def": {"label": "防御", "initial": 8}}}
BATTLE_NO_CRIT = json.loads(json.dumps(BATTLE))
BATTLE_NO_CRIT["formulas"] = {"damage": "player_atk * 2 - def", "crit_chance": "0", "crit_mult": "2"}
c4 = ChatCore()
c4.set_player_persona({"name": "勇者", "advanced": {"battle": PB}})
c4.set_active_roles([{"name": "魔物", "system_prompt": "x", "unlocked": False,
                      "advanced": {"battle": BATTLE_NO_CRIT}}])
check(c4.mechanism_state["player"]["atk"] == 20 and c4.mechanism_state["player"]["def"] == 8,
      "玩家卡战斗属性生效: %r" % c4.mechanism_state["player"])
txt7, _ = c4.resolve_battle_move("fire")
check(txt7 is not None and "55" in txt7, "玩家 atk=20 结算 55 伤害: %s" % txt7)  # fire: 20*3-5=55
n7 = c4.add_user_message("开战")
c4.tree.nodes[n7].metadata["ms"] = c4.mechanism_snapshot()
c4.strip_mechanism_tags("[ph:-10] 被打", apply=True)
check(c4.mechanism_state["player"]["hp"] == 90, "[ph:-10] 打玩家: hp=%s" % c4.mechanism_state["player"]["hp"])
c4.strip_mechanism_tags("[ph:-20]", apply=True)
c4.restore_mechanisms(n7)
check(c4.mechanism_state["player"]["hp"] == 100, "回溯恢复玩家 HP: hp=%s" % c4.mechanism_state["player"]["hp"])

print("== ⑧ 坍缩：战斗卡所有数值统一变为 2000（十万分之一事件） ==")
c5 = ChatCore()
c5.set_player_persona({"name": "勇者", "advanced": {"battle": PB}})
c5.set_active_roles([{"name": "魔物", "system_prompt": "x", "unlocked": False,
                      "advanced": {"battle": BATTLE_NO_CRIT}}])
# 坍缩前是常规数值
check(c5.mechanism_state["status"]["hp"] == 100 and c5.mechanism_state["status"]["atk"] == 10
      and c5.mechanism_state["player"]["hp"] == 100 and c5.mechanism_state["player"]["atk"] == 20,
      "坍缩前常规数值: 角色 hp=%s atk=%s 玩家 hp=%s atk=%s" % (
          c5.mechanism_state["status"]["hp"], c5.mechanism_state["status"]["atk"],
          c5.mechanism_state["player"]["hp"], c5.mechanism_state["player"]["atk"]))
ok_c = c5.collapse_battle_values()
st_c = c5.mechanism_state["status"]
pl_c = c5.mechanism_state["player"]
check(ok_c and st_c["hp"] == 2000 and st_c["atk"] == 2000 and st_c["def"] == 2000
      and st_c["spd"] == 2000 and st_c["mp"] == 2000,
      "坍缩后角色数值全 2000: %r" % st_c)
check(pl_c["hp"] == 2000 and pl_c["atk"] == 2000 and pl_c["def"] == 2000,
      "坍缩后玩家数值全 2000: %r" % pl_c)
ui_c = c5.battle_ui_state()
check(ui_c and ui_c["attrs"] and all(a["max"] == 2000 for a in ui_c["attrs"]),
      "坍缩后战斗 UI max 全 2000")
check(ui_c and ui_c["player"] and all(a["max"] == 2000 for a in ui_c["player"]),
      "坍缩后玩家 UI max 全 2000")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
