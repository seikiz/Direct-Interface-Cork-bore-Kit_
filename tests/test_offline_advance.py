# -*- coding: utf-8 -*-
"""离线世界推进审计：阈值 / 好感与状态结算 / 折算回合 / 方案与应用分离 / 可撤销。

为什么需要
----------
"你不在的时候世界自己走"最容易出的三类错，都只能靠测试挡住：
  · 阈值与倍率算错（现实 5 分钟 ×720 倍 = 2.5 软件天，本该触发；漏乘倍率就永远不触发）
  · 结算失控（一次掉光好感 / 状态被推过界 / 回合数爆掉把事件冷却一次性全放开）
  · 方案即应用（plan() 顺手改了状态 → 玩家点"忽略"也白改，且没法撤）
跑法：python tests/test_offline_advance.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import offline_advance as OA  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)


def tree_ago(minutes, role="ai", text="上次说的话"):
    """造一棵"最后一次互动在 N 分钟前"的树"""
    ts = (NOW - timedelta(minutes=minutes)).isoformat()
    older = (NOW - timedelta(minutes=minutes + 30)).isoformat()
    return {"nodes": {
        "n1": {"id": "n1", "role": "user", "content": "早", "parent_id": None,
               "children_ids": ["n2"], "timestamp": older, "metadata": {}},
        "n2": {"id": "n2", "role": role, "content": text, "parent_id": "n1",
               "children_ids": [], "timestamp": ts, "metadata": {}},
    }, "root_id": "n1", "current_leaf_id": "n2"}


MECH = {
    "affection": {"enabled": True, "initial": 50, "min": 0, "max": 100},
    "status": {"enabled": True, "fields": [
        {"key": "energy", "type": "int", "initial": 80},
        {"key": "mood", "type": "enum", "initial": "平静"},
    ]},
    "offline": {"enabled": True, "min_hours": 6, "max_days": 30,
                "aff_decay_per_day": 1.0, "aff_max_delta": 8.0,
                "status_decay_per_day": 0.5, "turn_per_day": 1.0},
}
STATE = {"affection": 62.0, "status": {"energy": 40, "mood": "疲惫"}, "flags": {}, "_turn": 5}


def main():
    print("=" * 62)
    print(u"离线世界推进审计")
    print("=" * 62)

    print(u"\n== ① 阈值与倍率：判定按【现实】时间，报数按软件时间 ==")
    # 现实 5 分钟 ×1 倍 = 5 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌软件分钟 → 远低于 6 小时
    p = OA.plan(tree_ago(5), MECH, STATE, scale=1, now=NOW)
    check(u"5 分钟（×1）不触发", (not p["ok"]) and bool(p["skipped"]), str(p.get("skipped")))
    # 关键回归：高速率下"切出去半分钟"绝不能触发
    # （旧实现按软件时间判：6 软件小时在 720 倍下只等于现实 30 秒 → 每次都弹）
    p_fast = OA.plan(tree_ago(5), MECH, STATE, scale=720, now=NOW)
    check(u"5 分钟 ×720 倍【也】不触发（判定按现实时间，防弹窗刷屏）",
          (not p_fast["ok"]) and u"现实" in p_fast["skipped"], str(p_fast.get("skipped")))
    p_slow = OA.plan(tree_ago(20), MECH, STATE, scale=1, now=NOW)
    check(u"20 分钟 ×1 倍不触发（软件时间不足 6 小时）",
          (not p_slow["ok"]) and u"软件时间" in p_slow["skipped"], str(p_slow.get("skipped")))
    # 现实 30 分钟 ×720 倍 = 15 软件天 → 必须触发
    p720 = OA.plan(tree_ago(30), MECH, STATE, scale=720, now=NOW)
    check(u"30 分钟 ×720 倍 = 15 软件天 → 触发", p720["ok"], str(p720.get("skipped")))
    check(u"软件时长 = 现实 × 倍率",
          abs(p720["elapsed_sw_sec"] - 30 * 60 * 720) < 1, str(p720["elapsed_sw_sec"]))
    check(u"人话说明里有天数", u"天" in p720["summary"], p720["summary"])

    print(u"\n== ② 好感结算：有上限、有下限，且算得清 ==")
    p = OA.plan(tree_ago(60 * 24 * 3), MECH, STATE, scale=1, now=NOW)   # 3 天
    check(u"3 天触发", p["ok"], str(p.get("skipped")))
    check(u"好感按每天 1 点下滑：62 → 59", p["affection"]["after"] == 59.0, str(p["affection"]))
    check(u"delta 是负的且被记录", p["affection"]["delta"] == -3.0, str(p["affection"]))
    p30 = OA.plan(tree_ago(60 * 24 * 30), MECH, STATE, scale=1, now=NOW)   # 30 天
    check(u"一次最多掉 aff_max_delta（8 点）", p30["affection"]["delta"] == -8.0, str(p30["affection"]))
    low = dict(STATE)
    low["affection"] = 3.0
    pl = OA.plan(tree_ago(60 * 24 * 30), MECH, low, scale=1, now=NOW)
    check(u"好感不会掉到地板以下（量程 15% = 15）",
          pl["affection"]["after"] >= 15.0, str(pl["affection"]))

    print(u"\n== ③ 上限保护：离开一年也不按一年算 ==")
    p = OA.plan(tree_ago(60 * 24 * 365), MECH, STATE, scale=1, now=NOW)
    check(u"天数被上限截到 30", abs(p["days"] - 30) < 1e-6, str(p["days"]))
    check(u"标记了 capped", p["capped"] is True)
    check(u"说明里写明按上限计", u"上限" in p["summary"], p["summary"])

    print(u"\n== ④ 数值状态回归初值（enum 不动）==")
    p = OA.plan(tree_ago(60 * 24 * 3), MECH, STATE, scale=1, now=NOW)
    kinds = {s["k"] for s in p["status"]}
    check(u"只动数值字段（energy），不动 enum（mood）", kinds == {"energy"}, str(p["status"]))
    e = p["status"][0]
    check(u"energy 40 朝初值 80 回升", e["before"] == 40 and e["after"] > 40, str(e))
    check(u"不会越过初值", e["after"] <= 80, str(e))

    print(u"\n== ⑤ 折算回合：喂给按回合计的事件冷却 ==")
    p = OA.plan(tree_ago(60 * 24 * 3), MECH, STATE, scale=1, now=NOW)
    check(u"3 天 → 3 个回合", p["turns"] == 3, str(p["turns"]))
    p2 = OA.plan(tree_ago(60 * 24 * 365), MECH, STATE, scale=1, now=NOW)
    check(u"回合数有上限（30）", p2["turns"] == 30, str(p2["turns"]))
    check(u"summary 提到回合推进", u"回合" in p2["summary"], p2["summary"])

    print(u"\n== ⑥ 方案与应用分离：plan 绝不改状态 ==")
    st = {"affection": 62.0, "status": {"energy": 40}, "flags": {}, "_turn": 5}
    snapshot = repr(st)
    p = OA.plan(tree_ago(60 * 24 * 3), MECH, st, scale=1, now=NOW)
    check(u"plan 之后状态一字未改", repr(st) == snapshot, repr(st))
    undo = OA.apply(p, st)
    check(u"apply 改了好感", st["affection"] == 59.0, str(st))
    check(u"apply 改了 state 并推进回合", st["_turn"] == 8, str(st["_turn"]))
    check(u"apply 返回 undo 记录", isinstance(undo, dict) and undo["affection"] == 62.0, str(undo))
    check(u"undo 前状态确实是改过的（防 apply 没生效造成假绿）", st["affection"] != 62.0)
    OA.revert(undo, st)
    check(u"revert 完全还原（含回合）",
          st["affection"] == 62.0 and st["_turn"] == 5 and st["status"]["energy"] == 40, repr(st))

    print(u"\n== ⑦ 不该动的时候一律不动 ==")
    off = dict(MECH)
    off["offline"] = {"enabled": False}
    p = OA.plan(tree_ago(60 * 24 * 30), off, STATE, scale=1, now=NOW)
    check(u"机制卡里关掉 → 不触发", (not p["ok"]) and u"关闭" in p["skipped"], str(p.get("skipped")))
    p = OA.plan({"nodes": {}}, MECH, STATE, scale=1, now=NOW)
    check(u"空树 → 给人话原因", (not p["ok"]) and u"时间戳" in p["skipped"], str(p.get("skipped")))
    p = OA.plan(tree_ago(60 * 24 * 3), MECH, STATE, scale=1, now=NOW,
                dismissed_ts=(NOW - timedelta(minutes=1)).isoformat())
    check(u"点过忽略（dismissed 更新）→ 不再重复提示", (not p["ok"]), str(p.get("skipped")))
    check(u"apply 对无效方案返回 None", OA.apply({"ok": False}, STATE) is None)

    print(u"\n== ⑧ 时间戳解析与时钟异常 ==")
    check(u"ISO 带时区", OA.parse_ts("2026-10-02T12:00:00+00:00") is not None)
    check(u"ISO 带 Z", OA.parse_ts("2026-10-02T12:00:00Z") is not None)
    check(u"空格分隔", OA.parse_ts("2026-10-02 12:00:00") is not None)
    check(u"纯日期", OA.parse_ts("2026-10-02") is not None)
    check(u"垃圾值返回 None", OA.parse_ts("不是时间") is None and OA.parse_ts(None) is None)
    future = tree_ago(-60)          # 时间戳在未来（时钟回拨）
    pf = OA.plan(future, MECH, STATE, scale=720, now=NOW)
    check(u"时间戳在未来时按 0 处理，不产生负结算",
          pf["elapsed_real_sec"] == 0 and (not pf["ok"]), str(pf.get("elapsed_real_sec")))
    check(u"缺 _tree_ts 时用节点时间戳兜底",
          OA.last_active(tree_ago(10)) is not None)
    check(u"完全没有时间戳时返回 None", OA.last_active({"nodes": {"x": {"content": "hi"}}}) is None)

    print(u"\n== ⑨ 给可选 LLM 的上下文 ==")
    p = OA.plan(tree_ago(60 * 24 * 3), MECH, STATE, scale=1, now=NOW)
    check(u"llm_brief 有内容且写明不要提问",
          u"离线推进" in p["llm_brief"] and u"不要提问" in p["llm_brief"], p["llm_brief"][:60])
    check(u"进聊天的系统消息带锤子图标", OA.summarize_for_chat(p).startswith(u"🕰"))
    check(u"无效方案不产生聊天消息", OA.summarize_for_chat({"ok": False}) == "")

    print(u"\n== ⑩ 坏输入不崩 ==")
    for bad in (None, [], "x", 123):
        try:
            OA.plan(bad, bad, bad, scale=bad, now=NOW)
            ok = True
        except Exception as e:
            ok = False
            print("     ", repr(bad), "->", e)
        check(u"坏输入不抛异常：%s" % (repr(bad)[:16]), ok)

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("OFFLINE_ADVANCE_TEST_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
