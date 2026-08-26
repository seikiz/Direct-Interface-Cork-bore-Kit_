# -*- coding: utf-8 -*-
"""防数值膨胀测试：人物血上限 150、普攻封顶 29（5回合杀不死满血）、招式封顶 50、BOSS 卡豁免血上限。"""
import sys, os, re
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from DICK_core import ChatCore

ok = bad = 0
def check(c, m):
    global ok, bad
    if c: ok += 1; print("  OK " + m)
    else: bad += 1; print("  FAIL " + m)

def dmg_of(txt):
    m = re.search(r"造成 (\d+) 点伤害", txt or "")
    return int(m.group(1)) if m else 0

# 普通人物战斗：hp max 9999（应压到 150），普攻无公式、招式超强公式
BATTLE = {
    "enabled": True,
    "attrs": {"hp": {"label": "生命", "initial": 100, "max": 9999},
              "atk": {"label": "攻击", "initial": 10}, "def": {"label": "防御", "initial": 5}},
    "formulas": {"damage": "player_atk * 2 - def", "crit_chance": "0.0", "crit_mult": "2"},
    "moves": [
        {"id": "basic", "name": "普攻"},                                      # 无公式 → 普攻
        {"id": "nuke", "name": "核弹", "formula": "player_atk * 100 - def"},  # 带公式 → 招式
    ],
}
BOSS_BATTLE = dict(BATTLE)  # 复制；改 max 为 9999 且 boss=true（可超上限）
BOSS_BATTLE["boss"] = True
BOSS_BATTLE["attrs"] = {"hp": {"label": "生命", "initial": 500, "max": 9999}}

def make(bb, atk=9999):
    c = ChatCore()
    c.set_player_persona({"name": "P", "advanced": {"battle": {"enabled": True,
        "attrs": {"hp": {"initial": 100, "max": 9999}, "atk": {"initial": atk}}}}})
    c.set_active_roles([{"name": "敌", "system_prompt": "x", "unlocked": False, "advanced": {"battle": bb}}])
    return c

print("== 普通人物：血上限 150 ==")
c = make(BATTLE)
check(c.mechanism_state["status"]["hp"] == 150, "普人物 HP 压到 150")
check(c.mechanism_state["player"]["hp"] == 150, "玩家 HP 压到 150")

print("== 普攻（无公式）封顶 29 ==")
tx, _ = c.resolve_battle_move("basic")
check(dmg_of(tx) == 29, "普攻封顶 29（基础公式被压）: " + str(dmg_of(tx)))
c2 = make(BATTLE); st = c2.mechanism_state["status"]
for _ in range(5):
    c2.resolve_battle_move("basic")
check(st["hp"] == 150 - 5 * 29, "普攻 5 回合未击倒满血（%s）" % st["hp"])

print("== 招式（带公式）封顶 50 ==")
c3 = make(BATTLE)
tx, _ = c3.resolve_battle_move("nuke")
check(dmg_of(tx) == 50, "招式封顶 50: " + str(dmg_of(tx)))

print("== BOSS 卡豁免血上限 ==")
cb = make(BOSS_BATTLE)
check(cb.mechanism_state["status"]["hp"] == 9999, "BOSS 血上限不设限（9999）")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
