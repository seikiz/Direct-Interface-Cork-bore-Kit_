# -*- coding: utf-8 -*-
"""世界线动态切换测试：A) GM 回复带【世界线：xxx】标记 → 自动穿越 + 剔除标记。"""
import sys, os
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

core = ChatCore()
core.set_worlds([{"name": "主世界", "description": "正常位面"},
                 {"name": "败北线", "description": "失败的未来"},
                 {"name": "救世线", "description": "奇迹的结局"}])
core.current_world_name = "主世界"

print("== 已知世界线：自动穿越 + 剔除标记 ==")
t = "夜色越来越沉，你感到时空在扭曲。【世界线：败北线】"
cleaned, sw = core.apply_world_marker(t)
check(sw == "败北线", "命中世界线 败北线")
check("【世界线：败北线】" not in cleaned, "标记已被剔除")
check(core.current_world_name == "败北线", "已自动穿越到败北线")

print("== 未知世界线：不切、保留原文 ==")
cleaned2, sw2 = core.apply_world_marker("从未见过的【世界线：不存在线】")
check(sw2 is None, "未知世界线不切换")
check("【世界线：不存在线】" in cleaned2, "未知标记保留原文")

print("== 无标记：原样返回 ==")
cleaned3, sw3 = core.apply_world_marker("你好，继续剧情。")
check(sw3 is None and cleaned3 == "你好，继续剧情。", "无标记原样")

print("== 穿越到另一条线（救世线） ==")
ok_switch = core.set_current_world("救世线")
check(ok_switch is True and core.current_world_name == "救世线", "set_current_world 穿越成功")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
