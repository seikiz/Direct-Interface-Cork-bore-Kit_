# -*- coding: utf-8 -*-
"""好感度事件：可重复触发 / 冷却 / 事件好感加成 / 进度面板 / 关键词留空。

用户反馈："好感度事件太烦琐"。四件事一起做，各自要有测试证明真的生效：
  ① 可视化编辑器（前端）—— 这里测它的数据契约：once/cooldown/aff 能存进卡
  ② 进度面板 —— core.event_progress() 要给出正确的状态与差距
  ③ 可重复触发 —— once=False 时按冷却反复触发，once=True 时仍然只一次
  ④ 好感度自动化 —— 事件自带 aff 时自动加减好感，不依赖模型标 [aff]

另有一条重要的行为改动：关键词留空 = 只看好感（不设闸门）。
原来 keywords 是硬闸门，好感到了但玩家没说那几个字，事件永不触发。

跑法：utau_env\\Scripts\\python.exe tests\\test_affection_events.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from DICK_core import ChatCore     # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [OK] %s" % name)
    else:
        FAIL += 1
        print("  [FAIL] %s  %s" % (name, detail))


def engine(events, aff_max=100, initial=50, crit=0.0):
    c = ChatCore.__new__(ChatCore)
    c._mech_config = {
        "affection": {"enabled": True, "initial": initial, "min": 0,
                      "max": aff_max, "crit": crit},
        "events": events,
    }
    c.mechanism_state = {"affection": initial, "status": {}, "flags": {},
                         "_turn": 0, "event_counts": {}}
    c.pending_event = None
    return c


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_once_still_once():
    print("\n== ① 老行为不能变：once 缺省仍然是只触发一次 ==")
    ev = {"id": "confess", "name": "告白", "aff_ge": 80, "prompt": "演出告白"}
    c = engine([ev])
    c.mechanism_state["affection"] = 90
    r1 = c.check_mech_events("随便说点什么")
    check("第一次触发", r1 is not None and r1["id"] == "confess", str(r1))
    r2 = c.check_mech_events("再说点什么")
    check("第二次不再触发（once 缺省=True）", r2 is None, str(r2))
    r3 = c.check_mech_events("第三次")
    check("第三次也不触发", r3 is None, str(r3))


def test_repeatable():
    print("\n== ② 可重复：once=False + cooldown 轮冷却 ==")
    ev = {"id": "daily", "name": "日常", "aff_ge": 0, "once": False,
          "cooldown": 2, "prompt": "来一段日常"}
    c = engine([ev])
    got = []
    for i in range(7):
        r = c.check_mech_events("轮 %d" % (i + 1))
        got.append(1 if r else 0)
    # cooldown=2 的语义 = 距上次触发至少隔 2 个回合计数，即"每 2 轮最多一次"。
    # 第1轮触发(at=1) → 第2轮(1-1=0<2)跳过 → 第3轮(3-1=2>=2)触发 → ...
    check("触发节奏符合 cooldown=2（每 2 轮一次）",
          got == [1, 0, 1, 0, 1, 0, 1], str(got))
    check("触发次数记进了 event_counts",
          c.mechanism_state["event_counts"].get("daily", {}).get("n") == 4,
          str(c.mechanism_state["event_counts"]))
    check("event_log 里同一 id 不重复堆叠（结局链判定要用）",
          c.mechanism_state["event_log"].count("daily") == 1,
          str(c.mechanism_state["event_log"]))


def test_cooldown_zero():
    print("\n== ③ 可重复 + 冷却 0：每轮都能触发 ==")
    ev = {"id": "x", "name": "X", "once": False, "cooldown": 0, "prompt": "p"}
    c = engine([ev])
    got = [1 if c.check_mech_events("t%d" % i) else 0 for i in range(5)]
    check("5 轮全触发", got == [1] * 5, str(got))


def test_keywords_optional():
    print("\n== ④ 关键词留空 = 只看好感（原来会一直不触发）==")
    ev = {"id": "storm", "name": "风暴夜", "aff_ge": 30, "prompt": "暴风雨夜"}
    c = engine([ev])
    c.mechanism_state["affection"] = 29
    check("好感不够时不触发", c.check_mech_events("今天天气不错") is None)
    c.mechanism_state["affection"] = 30
    r = c.check_mech_events("今天天气不错")
    check("好感到了、没说任何关键词也触发", r is not None and r["id"] == "storm",
          str(r))

    print("\n      对照：写了关键词就仍然是闸门（向后兼容）")
    ev2 = {"id": "k", "name": "K", "keywords": ["告白"], "prompt": "p"}
    c2 = engine([ev2])
    check("没说到关键词 → 不触发", c2.check_mech_events("你好啊") is None)
    r2 = c2.check_mech_events("我想跟你告白")
    check("说到关键词 → 触发", r2 is not None and r2["id"] == "k", str(r2))


def test_event_affection_auto():
    print("\n== ⑤ 好感度自动化：事件自带 aff 时自动加减 ==")
    evs = [{"id": "date", "name": "约会", "aff_ge": 0, "aff": 10, "prompt": "约会"},
           {"id": "fight", "name": "吵架", "aff": -20, "prompt": "吵架"}]
    c = engine(evs)
    c.check_mech_events("第一次")
    check("触发 'date' 后好感 50 → 60（10% of 100）",
          c.mechanism_state["affection"] == 60, str(c.mechanism_state["affection"]))
    # 注意：一轮只注入一个事件（check_mech_events 命中即 return），
    # 所以 'fight' 要等下一轮才轮得到。这不是 bug —— 一轮塞两个事件提示会打架。
    c.check_mech_events("第二次")
    check("触发 'fight' 后好感 60 → 40（-20%）",
          c.mechanism_state["affection"] == 40, str(c.mechanism_state["affection"]))

    print("\n      上限不是 100 时按百分比算（与 [aff:+N] 同口径）")
    c2 = engine([{"id": "d", "name": "D", "aff": 5, "prompt": "p"}],
                aff_max=1314, initial=0)
    c2.check_mech_events("x")
    expect = round(1314 * 5 / 100.0)
    check("上限 1314 时 +5%% → %d" % expect,
          c2.mechanism_state["affection"] == expect,
          str(c2.mechanism_state["affection"]))

    print("\n      没写 aff 就不动好感（缺省不改变行为）")
    c3 = engine([{"id": "n", "name": "N", "prompt": "p"}])
    c3.check_mech_events("x")
    check("好感仍是初始 50", c3.mechanism_state["affection"] == 50,
          str(c3.mechanism_state["affection"]))


def test_progress_panel():
    print("\n== ⑥ 进度面板：状态与差距要准 ==")
    evs = [
        {"id": "meet", "name": "初遇", "aff_ge": 0, "prompt": "p"},
        {"id": "storm", "name": "风暴夜", "aff_ge": 30, "prompt": "p"},
        {"id": "confess", "name": "告白", "aff_ge": 80, "prompt": "p"},
        {"id": "daily", "name": "日常", "once": False, "cooldown": 3, "prompt": "p"},
    ]
    c = engine(evs)
    # 初遇的 aff_ge=0 意味着好感 50 已经达标，所以它不是"差多少"的例子
    c.mechanism_state["affection"] = 10
    items = c.event_progress()
    by = {x["id"]: x for x in items}
    check("列出全部事件", len(items) == 4, str(len(items)))
    check("初遇：无条件 → 可以触发", by["meet"]["state"] == "ready", str(by["meet"]))
    check("风暴夜：还差 20（当前 10 / 需要 30）", by["storm"]["state"] == "blocked"
          and "差 20" in by["storm"]["why"], str(by["storm"]))
    check("告白：还差 70（当前 10 / 需要 80）",
          by["confess"]["state"] == "blocked" and "差 70" in by["confess"]["why"],
          str(by["confess"]))
    c.mechanism_state["affection"] = 50
    c.check_mech_events("t")   # 命中第一个满足的（meet），一轮只注入一个
    by = {x["id"]: x for x in c.event_progress()}
    check("初遇触发后 → fired", by["meet"]["state"] == "fired", str(by["meet"]))

    # 冷却状态要单独测 —— 上面的 check 命中的是 meet，daily 还没轮到
    print("\n      单独测冷却状态（不掺别的事件）")
    c2 = engine([{"id": "daily", "name": "日常", "once": False, "cooldown": 3,
                  "prompt": "p"}])
    c2.check_mech_events("t")
    d = {x["id"]: x for x in c2.event_progress()}["daily"]
    check("日常刚触发 → 冷却中", d["state"] == "cooling", str(d))
    check("冷却剩余轮数写进说明", "还差" in d["why"], d["why"])
    c2.check_mech_events("t2")   # 跳过：1-1=0 < 3
    c2.check_mech_events("t3")   # 跳过：2-1=1 < 3
    d = {x["id"]: x for x in c2.event_progress()}["daily"]
    check("冷却剩 1 轮时仍报冷却", d["state"] == "cooling" and "还差 1" in d["why"],
          str(d))
    c2.check_mech_events("t4")   # 触发：3-1=2... 第 4 轮才 4-1=3>=3 → 第 2 次
    d = {x["id"]: x for x in c2.event_progress()}["daily"]
    check("第 4 轮再次触发，次数累计为 2", d["times"] == 2, str(d))
    check("刚触发完立刻回到冷却", d["state"] == "cooling" and "还差 3" in d["why"],
          str(d))
    # 再走满一个冷却周期 → 第 7 轮第 3 次
    c2.check_mech_events("t5")
    c2.check_mech_events("t6")
    c2.check_mech_events("t7")
    d = {x["id"]: x for x in c2.event_progress()}["daily"]
    check("第 7 轮第 3 次触发（节奏 1,4,7）", d["times"] == 3, str(d))

    c.mechanism_state["affection"] = 85
    by = {x["id"]: x for x in c.event_progress()}
    check("好感提到 85 → 告白变可触发", by["confess"]["state"] == "ready",
          str(by["confess"]))


def test_progress_does_not_mutate():
    print("\n== ⑦ 进度面板不能有副作用 ==")
    c = engine([{"id": "a", "name": "A", "aff_ge": 0, "prompt": "p"}])
    before = dict(c.mechanism_state)
    before["flags"] = dict(before["flags"])
    c.event_progress()
    c.event_progress()
    check("好感没变", c.mechanism_state["affection"] == before["affection"])
    check("回合数没变（进度是纯读）",
          c.mechanism_state.get("_turn") == before.get("_turn"),
          "%s vs %s" % (c.mechanism_state.get("_turn"), before.get("_turn")))
    check("没有偷偷置 flag", c.mechanism_state["flags"] == before["flags"],
          str(c.mechanism_state["flags"]))


def test_backward_compat_state():
    print("\n== ⑧ 旧存档没有 _turn / event_counts 也能跑 ==")
    c = engine([{"id": "a", "name": "A", "aff_ge": 0, "prompt": "p"}])
    # 模拟读进来的旧状态：缺两个新键
    c.mechanism_state = {"affection": 50, "status": {}, "flags": {}}
    r = c.check_mech_events("x")
    check("旧状态照样触发", r is not None and r["id"] == "a", str(r))
    check("自动补上 _turn", c.mechanism_state.get("_turn") == 1,
          str(c.mechanism_state.get("_turn")))
    check("自动补上 event_counts",
          isinstance(c.mechanism_state.get("event_counts"), dict),
          str(c.mechanism_state.get("event_counts")))
    items = c.event_progress()
    check("进度面板也能读旧状态", len(items) == 1 and items[0]["state"] == "fired",
          str(items))


def test_prompt_block_mentions_repeat():
    print("\n== ⑨ 机制提示要把「可重复/冷却」告诉模型 ==")
    c = engine([{"id": "d", "name": "日常", "once": False, "cooldown": 3,
                 "prompt": "p"}])
    blk = c._mech_prompt_block(c._mech_config)
    check("提示里写了可重复", "可重复" in blk, blk[-120:])
    check("提示里写了冷却轮数", "冷却3轮" in blk, blk[-120:])


if __name__ == "__main__":
    print("=" * 62)
    print("好感度事件：可重复 / 自动化 / 进度面板")
    print("=" * 62)
    test_once_still_once()
    test_repeatable()
    test_cooldown_zero()
    test_keywords_optional()
    test_event_affection_auto()
    test_progress_panel()
    test_progress_does_not_mutate()
    test_backward_compat_state()
    test_prompt_block_mentions_repeat()
    print("\n" + "=" * 62)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)
