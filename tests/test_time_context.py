# -*- coding: utf-8 -*-
"""时间上下文：把历史链的【间隔】读出来粘给模型。

起因：MessageNode.timestamp 从第一天就一直在存，但代码里【没有任何地方读它】
（全项目只有 4 处：定义、赋值、序列化、反序列化）。
所以模型看到的对话是没有时间的一袋字 —— 不知道那些事是昨天还是上个月发生的。

打点计时器能读出东西不是因为记了字，是因为纸带匀速走、点距=时间。
所以这里把间隔读出来，粘到内容上。

要证的：
  ① 只有值得说的间隔才吭声（<30 分钟不标注）
  ② 人话单位对（秒/分钟/小时/天/月）
  ③ 最多标 3 段（长历史不能把提示撑爆）
  ④ 脏时间戳不能让流程崩
  ⑤ 真的进了 API 载荷（不是写了个没人调的函数）

跑法：utau_env\\Scripts\\python.exe tests\\test_time_context.py
"""
import os
import sys
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import DICK_core as DC   # noqa: E402

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


def chain(*gaps_minutes):
    """按给定间隔（分钟）造一条链，每段间隔生成【一对】消息。

    这里踩过两次坑，都记下来：
      ① 第一版把起点算成 now-sum(gaps) 再逐条加 gap，结果时间戳落到未来，
         间隔算成负数 —— 全部测不出东西。
      ② 第二版从 now 倒着摆，但只给每段间隔生成【一条】消息。
         一段间隔需要【两条】消息才算得出来（差值在相邻两条之间），
         所以 chain(31) 只有 1 条非 system 消息，time_context_for 正确地
         返回了空串 —— 是测试假设错了，不是被测代码错了。

    现在：每段间隔生成一 user 一 assistant，保证差值是给定的 gap。
    """
    now = datetime.now()
    out = [{"role": "system", "content": "sys",
            "timestamp": (now - timedelta(minutes=sum(gaps_minutes) + 1)).isoformat(),
            "metadata": {}}]
    t = now - timedelta(minutes=sum(gaps_minutes))
    for g in gaps_minutes:
        out.append({"role": "user", "content": "u", "timestamp": t.isoformat(),
                    "metadata": {}})
        t = t + timedelta(minutes=g)
        out.append({"role": "assistant", "content": "a", "timestamp": t.isoformat(),
                    "metadata": {}})
    return out


def test_empty_and_single():
    print("\n== ① 空链 / 单条 / 没有时间戳 → 不吭声 ==")
    check("空链返回空串", DC.time_context_for([]) == "")
    check("None 不崩", DC.time_context_for(None) == "")
    one = [{"role": "user", "content": "a", "timestamp": datetime.now().isoformat()}]
    check("只有一条 → 没有间隔可说", DC.time_context_for(one) == "")
    check("全都没时间戳 → 空串",
          DC.time_context_for([{"role": "user", "content": "a"}] ) == "")
    check("只有 system → 空串",
          DC.time_context_for([{"role": "system", "content": "s",
                                "timestamp": datetime.now().isoformat()}]) == "")


def test_short_gap_silent():
    print("\n== ② 短间隔不标注（刚说完不值得写进提示）==")
    c = chain(1, 2, 3)          # 全在 30 分钟内
    check("1~3 分钟的间隔 → 不吭声", DC.time_context_for(c) == "",
          repr(DC.time_context_for(c)))
    c2 = chain(29)              # 差一分钟到阈值
    check("29 分钟仍在阈值下", DC.time_context_for(c2) == "")
    c3 = chain(31)
    got = DC.time_context_for(c3)
    check("31 分钟开始吭声", got != "", repr(got))


def test_units():
    print("\n== ③ 人话单位对 ==")
    CASES = [
        (45, "分钟"),
        (90, "小时"),
        (19 * 60, "小时"),        # 19 小时：仍在 DAY_NOTICE_HOURS(20) 之下
        (30 * 60, "天"),          # 30 小时 = 1.25 天 → 报"天"（边界在 20 小时）
        (60 * 24 * 3, "天"),
        (60 * 24 * 90, "个月"),
    ]
    for mins, want in CASES:
        got = DC.time_context_for(chain(mins))
        check("%-10s → 提到「%s」" % ("%d 分钟" % mins, want),
              want in got, repr(got[:70]))


def test_marks_capped():
    print("\n== ④ 最多标 3 段（长历史不能把提示撑爆）==")
    c = chain(60, 120, 180, 240, 300, 360)   # 6 段都过阈值
    got = DC.time_context_for(c)
    check("确实报了间隔", got != "")
    # 数"、"分隔的段数：正文里是 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌"、".join(...)
    seg = got.split("中途有过 ")[1].split("。")[0]
    n = len(seg.split("、"))
    check("最多 3 段，实际 %d 段" % n, n <= DC.GAP_MAX_MARKS, seg)


def test_dirty_timestamps():
    print("\n== ⑤ 脏时间戳不崩 ==")
    # 前面几条全是坏的，最后两条给出一个真实间隔（50 小时）
    base = datetime.now() - timedelta(hours=50)
    bad = [
        {"role": "user", "content": "a", "timestamp": "不是时间"},
        {"role": "assistant", "content": "b", "timestamp": ""},
        {"role": "user", "content": "c", "timestamp": None},
        {"role": "assistant", "content": "d", "timestamp": 12345},
        {"role": "user", "content": "e", "timestamp": base.isoformat()},
        {"role": "assistant", "content": "f",
         "timestamp": (base + timedelta(hours=50)).isoformat()},
    ]
    try:
        got = DC.time_context_for(bad)
        check("没抛异常", True)
        check("从坏数据里挑出了那条有效间隔", got != "", repr(got))
        check("单位对（50 小时 → 天）", "天" in got, repr(got[:60]))
    except Exception as e:
        check("没抛异常", False, "抛了 %r" % (e,))


def test_get_current_chain_keeps_timestamp():
    print("\n== ⑥ 链里必须带上 timestamp（原来是在这里丢的）==")
    from DICK_core import TreeManager
    t = TreeManager()
    nid = t.add_node("user", "你好")
    t.add_node("assistant", "嗯。", parent_id=nid)
    c = t.get_current_chain()
    check("链非空", len(c) >= 2, str(c))
    miss = [m for m in c if "timestamp" not in m]
    check("每条都带 timestamp", not miss, str(miss))
    check("timestamp 是有效 ISO", bool(c[-1].get("timestamp")),
          repr(c[-1].get("timestamp")))
    # 端到端：链直接喂给 time_context_for 能工作。
    # 注意必须把【倒数第二条】也推到过去 —— 差值在相邻两条之间，
    # 只改最后一条的话差值是负的（最后一条比前一条早），算不出间隔。
    # 也要显式传 scale=1：不传会读系统设置（默认 720 倍），
    # 于是 40 小时变成 3.3 年、报"个月"，断言就挂了（踩过一次）。
    c2 = list(c)
    c2[-1]["timestamp"] = datetime.now().isoformat()
    c2[-2]["timestamp"] = (datetime.now() - timedelta(hours=40)).isoformat()
    got = DC.time_context_for(c2, scale=1)
    check("链 → 时间上下文 端到端可用", got != "", repr(got))
    check("报出了 40 小时量级", ("天" in got or "小时" in got), repr(got[:70]))


def test_scale_multiplies_reported_time():
    print("\n== ⑧ 时间流速：报给模型的是【那边】过了多久 ==")
    # 建一次、复用 —— chain() 用的是"相对现在"，每次重建都会得到不同的绝对时间戳，
    # 而 time_context_for 会用【真实现在】去算"距上一次多久"，
    # 于是跨时间比较把间隔莫名放大（踩过一次，报成了 1 个月）。
    ch = chain(60)      # 现实隔了 1 小时
    base = DC.time_context_for(ch, scale=1)
    check("1 倍时报「小时」", "小时" in base, repr(base[:80]))

    fast = DC.time_context_for(ch, scale=720)
    check("720 倍时同一个现实间隔报得更长（不再是小时）",
          "小时" not in fast, repr(fast[:90]))
    check("720 倍时 1 小时 → 30 天量级", "天" in fast or "个月" in fast,
          repr(fast[:90]))

    huge = DC.time_context_for(ch, scale=86400)
    check("86400 倍时 1 小时 → 约 10 年，报「个月」", "个月" in huge, repr(huge[:90]))

    print("\n      高倍率要在提示里说明，否则模型会以为现实也过了这么久")
    check("720 倍时提示里写了流速", "倍" in fast, repr(fast[-90:]))
    check("1 倍时不写流速（不该啰嗦）", "比现实快" not in base, repr(base[-60:]))

    print("\n      记忆寿命【不】受倍率影响（AGE_MODE=real，默认）")
    import salience as S
    now = time.time()
    m = {"content": "嗯，知道了。", "_node_id": "fixed-1",
         "_ts": now - 5 * 86400.0}
    s1 = S.salience(m, now=now, scale=1)
    s720 = S.salience(m, now=now, scale=720)
    s86400 = S.salience(m, now=now, scale=86400)
    check("传 1 / 720 / 86400 得到同样清晰度（默认不按流速衰老）",
          abs(s1 - s720) < 1e-12 and abs(s1 - s86400) < 1e-12,
          "%.6f / %.6f / %.6f" % (s1, s720, s86400))
    print("      5 天前的平淡内容：1倍=%.3f  720倍=%.3f  86400倍=%.3f"
          % (s1, s720, s86400))


def test_time_scale_module():
    print("\n== ⑨ time_scale 模块：范围、预设、稳定性 ==")
    import time_scale as TS
    check("下限是 10 倍", TS.MIN_SCALE == 10.0, str(TS.MIN_SCALE))
    check("默认值在预设表里", any(abs(TS.DEFAULT_SCALE - m) < 0.5
                                  for m, _ in TS.PRESETS), str(TS.DEFAULT_SCALE))
    check("钳位：低于下限被抬到下限", TS.clamp(1) == TS.MIN_SCALE,
          str(TS.clamp(1)))
    check("钳位：高于上限被压到上限", TS.clamp(10 ** 12) == TS.MAX_SCALE,
          str(TS.clamp(10 ** 12)))
    check("钳位：垃圾输入回默认值", TS.clamp("abc") == TS.DEFAULT_SCALE,
          str(TS.clamp("abc")))
    check("钳位：NaN 回默认值", TS.clamp(float("nan")) == TS.DEFAULT_SCALE)
    check("预设表从小到大", [m for m, _ in TS.PRESETS]
          == sorted(m for m, _ in TS.PRESETS), str([m for m, _ in TS.PRESETS]))
    check("预设覆盖了用户给的锚点 720 / 3600 / 86400",
          all(any(abs(m - x) < 0.5 for m, _ in TS.PRESETS)
              for x in (720, 3600, 86400)),
          str([m for m, _ in TS.PRESETS]))
    check("describe 给得出人话", "倍" in TS.describe(720), TS.describe(720))
    check("virtual_age 按倍率放大",
          TS.virtual_age_seconds(10, 720) == 7200.0,
          str(TS.virtual_age_seconds(10, 720)))
    check("virtual_age 不吃负数", TS.virtual_age_seconds(-5, 720) == 0.0)
    print("      当前设置：%s（%.0f 倍）" % (TS.describe(), TS.load()))


def test_injected_into_payload():
    print("\n== ⑦ 真的进了 API 载荷（不是没人调的函数）==")
    # 不重构生产代码，改用桩 + 假 _stream_create 把真实载荷截下来。
    # 桩必须齐：_fetch_response 依赖 22 个 self 属性，缺一个就抛
    # AttributeError 并被 except 吞掉，表现成"载荷截不到"，极难查。
    # 完整的桩清单见 _probe_payload.py（那段代码 grep 出来的依赖）。
    import threading
    sys.path.insert(0, ROOT)
    from _probe_payload import make_probe
    Probe, captured = make_probe()
    p = Probe()
    uid = p.tree.add_node("user", "你好")
    p.tree.add_node("assistant", "嗯。", parent_id=uid)
    nodes = list(p.tree.nodes.values())
    p.tree.nodes[p.tree.current_leaf_id].timestamp = datetime.now().isoformat()
    nodes[-2].timestamp = (datetime.now() - timedelta(hours=40)).isoformat()

    p._fetch_response("在吗", None, lambda *a, **k: None,
                      lambda *a, **k: None,
                      parent_node_id=None, _locked=True)
    msgs = captured.get("m")
    check("截到了真实载荷", isinstance(msgs, list) and len(msgs) > 0,
          str(type(msgs)))
    if not isinstance(msgs, list):
        return
    joined = "\n".join(str(m.get("content") or "") for m in msgs
                       if isinstance(m, dict))
    check("载荷里有【时间】那段", "【时间】" in joined, joined[:200])
    check("报出了 40 小时量级（天）", "天" in joined)
    for m in msgs:
        c = str(m.get("content") or "")
        if "【时间】" in c:
            print("        载荷条数 %d；时间那段 = %s" % (len(msgs), c[:110]))
            break


if __name__ == "__main__":
    print("=" * 62)
    print("时间上下文：把间隔粘给模型")
    print("=" * 62)
    test_empty_and_single()
    test_short_gap_silent()
    test_units()
    test_marks_capped()
    test_dirty_timestamps()
    test_get_current_chain_keeps_timestamp()
    test_scale_multiplies_reported_time()
    test_time_scale_module()
    test_injected_into_payload()
    print("\n" + "=" * 62)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)
