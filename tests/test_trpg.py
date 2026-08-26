# -*- coding: utf-8 -*-
"""跑团模式插件测试：GM/PC 设置、剧情向提示注入、回合轮换、掷骰。"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from plugins.trpg_plugin import TrpgPlugin

ok = bad = 0
def check(c, m):
    global ok, bad
    if c: ok += 1; print("  OK " + m)
    else: bad += 1; print("  FAIL " + m)

class Core: pass
core = Core()
p = TrpgPlugin(core)

print("== 命令：设置 GM/PC ==")
check(p.on_command("trpg", "gm 菲悠")[0].find("GM") >= 0, "设 GM")
check(p.on_command("trpg", "pc 凛")[0].find("凛") >= 0, "加 PC 凛")
check(p.on_command("trpg", "pc 咲")[0].find("咲") >= 0, "加 PC 咲")
check(p.pcs == ["凛", "咲"], "PC 列表正确")

print("== 未开始不注入 ==")
check(p.contextInjection() == "", "未开始 contextInjection 为空")

print("== start 后注入 GM 提示 + 行动者 ==")
r = p.on_command("trpg", "start")
check(r[0].find("跑团开始") >= 0, "start 消息")
check(p.active is True, "active=True")
inj = p.contextInjection()
check("剧情为主" in inj, "注入含剧情为主 GM 提示")
check("当前行动者：凛" in inj, "注入当前行动者=凛")

print("== 回合轮换 ==")
r = p.on_command("trpg", "turn")
check(r[0].find("咲") >= 0, "轮到咲")
check(p.turn == "咲", "turn 更新为咲")
r = p.on_command("trpg", "turn")
check(r[0].find("凛") >= 0, "轮回到凛")

print("== 掷骰 ==")
r = p.on_command("trpg", "roll 2d6+3")
check("d6" in r[0] and "**" in r[0], "掷骰 2d6+3 正常")
# 确定性验证大成功：固定随机数 = 最大面
import plugins.trpg_plugin as tp
_orig = tp.random.randint
tp.random.randint = lambda a, b: b
check("大成功" in p.on_command("trpg", "roll 1d20")[0], "大成功判定")
tp.random.randint = lambda a, b: a
check("大失败" in p.on_command("trpg", "roll 1d20")[0], "大失败判定")
tp.random.randint = _orig

print("== status / end ==")
check(p.on_command("trpg", "status")[0].find("跑团中") >= 0, "status")
check(p.on_command("trpg", "end")[0].find("退出") >= 0, "end")
check(p.active is False, "end 后非 active")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
