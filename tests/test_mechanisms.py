# -*- coding: utf-8 -*-
"""机制卡测试：好感度/状态/事件/回溯恢复/GAL 效果（stub LLM）。
运行：python tests/test_mechanisms.py"""
import sys, os, json, time, tempfile, shutil

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
        {"key": "mood", "name": "心情", "type": "enum", "initial": "平静", "options": ["平静", "开心", "生气"]},
        {"key": "hp", "name": "体力", "type": "int", "initial": 100, "min": 0, "max": 100}]},
    "events": [{"id": "confess", "name": "告白", "aff_ge": 80, "keywords": ["告白", "表白"], "prompt": "触发告白剧情", "once": True}],
}

print("== ① 状态初始化 + 系统提示注入 ==")
c = ChatCore()
c.set_active_roles([{"name": "猫娘", "system_prompt": "你是猫娘", "unlocked": False,
                     "advanced": {"mechanics": MECH}}])
check(c.mechanism_state["affection"] == 50, "好感初始 50")
check(c.mechanism_state["status"]["mood"] == "平静", "枚举状态初始")
check(c.mechanism_state["status"]["hp"] == 100, "整数状态初始")
sys_text = c.tree.nodes[c.tree.root_id].content
check("机制·好感度" in sys_text and "当前好感度 50/100" in sys_text, "系统提示注入好感规则")
check("机制·状态栏" in sys_text and "心情=平静" in sys_text, "系统提示注入状态栏")
check("机制·事件" in sys_text and "好感度≥80" in sys_text, "系统提示注入事件")

print("== ② 标签解析 ==")
c.add_user_message("你好")
reply = "她脸红了。[aff:+5][mood:开心][hp:-10]"
clean = c.strip_mechanism_tags(reply, apply=True)
check(clean == "她脸红了。", "标签被剥离: %r" % clean)
check(c.mechanism_state["affection"] == 55, "好感 +5")
check(c.mechanism_state["status"]["mood"] == "开心", "枚举状态赋值")
check(c.mechanism_state["status"]["hp"] == 90, "整数相对减")
check(c.strip_mechanism_tags("他说：[系统提示：测试]", apply=True) == "他说：[系统提示：测试]", "未知标签原样保留")
before = c.mechanism_state["affection"]
c.strip_mechanism_tags("[aff:+1] 显示", apply=False)
check(c.mechanism_state["affection"] == before, "显示剥离不改状态")

print("== ③ 暴击（crit=1.0 必满） ==")
c2 = ChatCore()
mech2 = json.loads(json.dumps(MECH))
mech2["affection"]["crit"] = 1.0
c2.set_active_roles([{"name": "R", "system_prompt": "x", "unlocked": False, "advanced": {"mechanics": mech2}}])
c2.mechanism_state["affection"] = 10
c2.strip_mechanism_tags("[aff:+1]", apply=True)
check(c2.mechanism_state["affection"] == 100, "暴击直接满好感")

print("== ④ 事件触发（once） ==")
c3 = ChatCore()
c3.set_active_roles([{"name": "R", "system_prompt": "x", "unlocked": False,
                      "advanced": {"mechanics": MECH}}])
check(c3.check_mech_events("随便聊聊") is None, "低好感不触发")
c3.mechanism_state["affection"] = 80
check(c3.check_mech_events("我喜欢你") is None, "关键词不中不触发")
ev = c3.check_mech_events("我喜欢你，和我告白吧")
check(ev is not None and ev["id"] == "confess", "好感+关键词触发")
check(c3.mechanism_state["flags"]["confess"] is True, "once 标记")
check(c3.check_mech_events("再告白一次") is None, "once 不重复触发")

print("== ⑤ 回溯恢复快照 ==")
c4 = ChatCore()
c4.set_active_roles([{"name": "R", "system_prompt": "x", "unlocked": False,
                      "advanced": {"mechanics": MECH}}])
n1 = c4.add_user_message("第一句")
c4.tree.nodes[n1].metadata["ms"] = c4.mechanism_snapshot()
c4.mechanism_state["affection"] = 77
n2 = c4.add_user_message("第二句")
c4.tree.nodes[n2].metadata["ms"] = {"affection": 33, "status": {"mood": "生气", "hp": 5}, "flags": {}}
c4.restore_mechanisms(n2)
check(c4.mechanism_state["affection"] == 33 and c4.mechanism_state["status"]["mood"] == "生气",
      "回溯恢复节点快照: %r" % c4.mechanism_state)
c4.restore_mechanisms(n1)
check(c4.mechanism_state["affection"] == 50, "回溯恢复早期快照（无 ms 则向上找）")

print("== ⑥ GAL 选项效果 ==")
c5 = ChatCore()
c5.set_active_roles([{"name": "R", "system_prompt": "x", "unlocked": False,
                      "advanced": {"mechanics": MECH}}])
c5.apply_mechanism_effect({"aff": -5, "st": {"mood": "生气"}})
check(c5.mechanism_state["affection"] == 45, "选项好感 -5")
check(c5.mechanism_state["status"]["mood"] == "生气", "选项状态变化")
c5.apply_mechanism_effect({"aff": None, "st": {"hp": "-20"}})
check(c5.mechanism_state["status"]["hp"] == 80, "选项整数状态")

print("== ⑦ 事件注入待触发（pending_event 语义） ==")
c6 = ChatCore()
c6.set_active_roles([{"name": "R", "system_prompt": "x", "unlocked": False,
                      "advanced": {"mechanics": MECH}}])
c6.mechanism_state["affection"] = 90
ev6 = c6.check_mech_events("我想和你告白")
check(ev6 is not None, "事件返回")
check(c6.pending_event is None, "初始无待注入事件")

print("== ⑧ 隐藏 ROLL（概率不公布） ==")
from unittest import mock
import html_app
app = html_app.HtmlApp()
item = {"text": "温柔关心她", "aff": 3}
# 边界：0.000005 → 坍缩（0.00001 内，十万分之一）
with mock.patch("random.random", return_value=0.000005):
    eff, kind, note = app._roll_option(item)
check(kind == "collapse" and eff["aff"] == 3, "0.000005 → 坍缩")
# 0.0005 → 天选（0.00101 内，千分之一）
with mock.patch("random.random", return_value=0.0005):
    eff, kind, note = app._roll_option(item)
check(kind == "chosen" and eff["aff"] == 3, "0.0005 → 天选")
# 0.01 → 大失败（0.02101 内）
with mock.patch("random.random", return_value=0.01):
    eff, kind, note = app._roll_option(item)
check(kind == "fail" and eff["aff"] == -3, "0.01 → 大失败（aff 反转）")
# 0.05 → 稀有（0.06101 内）
with mock.patch("random.random", return_value=0.05):
    eff, kind, note = app._roll_option(item)
check(kind == "rare" and eff["aff"] == 3, "0.05 → 稀有")
# 0.1 → 暴击（0.16101 内）
with mock.patch("random.random", return_value=0.1):
    eff, kind, note = app._roll_option(item)
check(kind == "crit" and eff["aff"] == 6, "0.1 → 暴击（aff×2）")
# 0.5 → 正常
with mock.patch("random.random", return_value=0.5):
    eff, kind, note = app._roll_option(item)
check(kind == "normal" and eff["aff"] == 3, "0.5 → 正常")
# 无 aff 的选项：crit/fail 不空转（note 置空）
with mock.patch("random.random", return_value=0.01):
    eff, kind, note = app._roll_option({"text": "无效果选项"})
check(kind == "fail" and eff == {} and note == "", "无效果选项 fail 不空转")
# 状态效果保留
with mock.patch("random.random", return_value=0.5):
    eff, kind, note = app._roll_option({"text": "x", "aff": 2, "st": {"mood": "开心"}})
check(kind == "normal" and eff["aff"] == 2 and eff["st"]["mood"] == "开心", "st 效果保留")

print("== ⑨ int 状态累加不清零（回溯/重激活语义） ==")
IM = {"affection": {"enabled": True, "initial": 50, "min": 0, "max": 100, "crit": 0.0},
      "status": {"enabled": True, "fields": [
          {"key": "energy", "name": "体力", "type": "int", "initial": 100, "min": 0, "max": 100}]}}
def _mk():
    cc = ChatCore()
    cc.set_active_roles([{"name": "测试", "system_prompt": "x", "unlocked": False,
                          "advanced": {"mechanics": IM}}])
    return cc
# 累加持续
c9 = _mk()
c9.strip_mechanism_tags("[energy:-10]", apply=True)  # 90
c9.strip_mechanism_tags("[energy:-10]", apply=True)  # 80
check(c9.mechanism_state["status"]["energy"] == 80, "int 累加 100→90→80")
# 回溯到无快照节点 → 保留累加（不清零）
n9 = c9.add_user_message("回溯点")
c9.restore_mechanisms(n9)
check(c9.mechanism_state["status"]["energy"] == 80,
      "回溯无快照不清零: %s" % c9.mechanism_state["status"]["energy"])
# 切角色重激活 → 新会话重置 initial
c10 = _mk()
c10.strip_mechanism_tags("[energy:-10]", apply=True)  # 90
c10.set_active_roles([{"name": "测试", "system_prompt": "x", "unlocked": False,
                       "advanced": {"mechanics": IM}}])
check(c10.mechanism_state["status"]["energy"] == 100, "重激活新会话重置 initial")
# 续聊带快照 → 恢复快照值
c11 = _mk()
c11.strip_mechanism_tags("[energy:-10]", apply=True)  # 90
aid11 = c11.tree.add_node("assistant", "回复", parent_id=c11.tree.current_leaf_id,
                          metadata={"ms": c11.mechanism_snapshot()})
c11.set_active_roles([{"name": "测试", "system_prompt": "x", "unlocked": False,
                       "advanced": {"mechanics": IM},
                       "history_tree": c11.get_all_nodes_data()}])
check(c11.mechanism_state["status"]["energy"] == 90, "续聊恢复快照 90")

print("结果：%d 通过, %d 失败" % (ok, bad))
sys.exit(1 if bad else 0)
