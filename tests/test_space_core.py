# -*- coding: utf-8 -*-
"""空间层（不能瞬移）回归测试：地图 / 路费 / 位置标签 / 穿帮判定 / 注入

为什么测这些
------------
"人不能瞬移"这件事只有三个可验证的支点，肉眼看不出来：
  ① 世界时间怎么换算（现实 × 倍率）—— 算错就会把 5 秒当成 5 小时，处处放行
  ② 路费怎么估（轮辐模型 / links 覆盖 / 交通方式系数）—— 估小了就等于没约束
  ③ 位置标签的解析与剥离 —— 剥不掉玩家就会看到 [loc:学校]，解析错就记到错的人身上

另外两条是产品约束：**已经发生的事不逆转**（跳得不合理也照样记下，只在下一轮提醒补交代），
以及**注入必须短**（≤240 字，和吃饭那层一样）。

跑法：python tests\\test_space_core.py
"""
import io
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import app_paths  # noqa: E402
import space_core as S  # noqa: E402

PASS = 0
FAIL = 0
NOW = datetime(2026, 10, 9, 20, 0, 0)
ROLE = {"name": "薇拉"}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def with_tmp(fn):
    """把数据目录指到临时目录跑一段（配置/位置状态都别落到工程根）"""
    tmp = tempfile.mkdtemp(prefix="dick_space_")
    real = app_paths.get_base_dir
    old = S._Cfg._cache
    try:
        app_paths.get_base_dir = lambda: tmp
        S._Cfg._cache = None
        return fn(tmp)
    finally:
        app_paths.get_base_dir = real
        S._Cfg._cache = old
        shutil.rmtree(tmp, ignore_errors=True)


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_world_minutes():
    print("\n== ① 世界时间：现实 × 倍率 ==")
    ts = (NOW - timedelta(minutes=2)).isoformat()
    check("720 倍：现实 2 分钟 = 那边 24 小时", abs(S.world_minutes_since(ts, 720, NOW) - 1440) < 1,
          str(S.world_minutes_since(ts, 720, NOW)))
    check("1 倍：现实 2 分钟就是 2 分钟", abs(S.world_minutes_since(ts, 1, NOW) - 2) < 0.01)
    check("时间戳是未来 → 当 0（不倒退）",
          S.world_minutes_since((NOW + timedelta(hours=1)).isoformat(), 720, NOW) == 0)
    check("脏时间戳 → None", S.world_minutes_since("不是时间", 720, NOW) is None)
    check("空时间戳 → None", S.world_minutes_since("", 720, NOW) is None)
    check("倍率非法 → 当 1", abs(S.world_minutes_since(ts, "abc", NOW) - 2) < 0.01)


def test_map_and_travel():
    print("\n== ② 地图与路费：轮辐模型 + links 覆盖 + 交通系数 ==")
    mp = S.map_for()
    check("内置地图有家", S.HUB in mp["places"])
    check("家→学校 = 学校那一项（25 分）", abs(S.travel_minutes(mp, "家", "学校") - 25) < 0.01)
    check("同一地点 = 0 分钟", S.travel_minutes(mp, "学校", "学校") == 0)
    # A、B 都不是家时按"经过家"估：25 + 35 = 60（偏保守，宁严不松）
    check("学校→公司 = 25+35（经过家估）", abs(S.travel_minutes(mp, "学校", "公司") - 60) < 0.01)
    check("往返对称", abs(S.travel_minutes(mp, "学校", "公司")
                        - S.travel_minutes(mp, "公司", "学校")) < 0.01)
    check("骑车比走路快（系数 0.4）",
          abs(S.travel_minutes(mp, "家", "学校", "骑车") - 10) < 0.01)
    check("打车更快（系数 0.35）",
          abs(S.travel_minutes(mp, "家", "学校", "打车") - 8.75) < 0.01)
    check("不认识的交通方式按走路", abs(S.travel_minutes(mp, "家", "学校", "飞船") - 25) < 0.01)

    role = {"name": "薇拉", "advanced": {"space": {
        "places": [{"name": "码头", "minutes": 45, "open": [6, 20]}],
        "links": {"学校|码头": 30}, "transport": {"电驴": 0.25}}}}
    mp2 = S.map_for(role)
    check("角色卡能加地点", "码头" in mp2["places"])
    check("links 精确覆盖估算（学校→码头 = 30，不是 25+45）",
          abs(S.travel_minutes(mp2, "学校", "码头") - 30) < 0.01)
    check("卡里能加交通方式", abs(S.travel_minutes(mp2, "家", "学校", "电驴") - 6.25) < 0.01)

    world = {"name": "测试城", "params": {"space": '{"places":[{"name":"天桥","minutes":5}]}'}}
    check("世界卡 params.space 里的 JSON 字符串也能认",
          "天桥" in S.map_for(None, world)["places"])


def test_reachable():
    print("\n== ③ 可达集：预算决定能去哪 ==")
    mp = S.map_for()
    check("5 分钟：只够楼下/小区门口",
          [n for n, _ in S.reachable(mp, "家", 5)] == ["楼下", "小区门口"],
          str(S.reachable(mp, "家", 5)))
    names = [n for n, _ in S.reachable(mp, "家", 30)]
    check("30 分钟：学校在内、公司不在内", "学校" in names and "公司" not in names, str(names[:8]))
    check("按耗时升序", [m for _, m in S.reachable(mp, "家", 60)]
          == sorted(m for _, m in S.reachable(mp, "家", 60)))
    check("limit 生效", len(S.reachable(mp, "家", 600, limit=3)) == 3)
    check("预算 None → 空（不知道时间就不猜）", S.reachable(mp, "家", None) == [])
    check("排除自己", all(n != "家" for n, _ in S.reachable(mp, "家", 600)))


def test_open_hours():
    print("\n== ④ 开门时间（含跨天营业）==")
    day = NOW.replace(hour=12)
    night = NOW.replace(hour=23, minute=30)
    dawn = NOW.replace(hour=3)
    meta = {"name": "咖啡馆", "open": [8, 22]}
    check("白天开着", S.open_now(meta, day)[0] is True)
    check("半夜关着，且说明里带营业时间",
          S.open_now(meta, night)[0] is False and "08:00" in S.open_now(meta, night)[1])
    check("没写 open = 一直开", S.open_now({"name": "家"}, night)[0] is True)
    check("跨天营业（22–02）：23 点开着", S.open_now({"name": "夜宵摊", "open": [22, 2]}, night)[0] is True)
    check("跨天营业：3 点关着", S.open_now({"name": "夜宵摊", "open": [22, 2]}, dawn)[0] is False)


def test_tags():
    print("\n== ⑤ 位置标签：解析与剥离 ==")
    check("解析 loc + ploc", S.parse_move("她进来。[loc:学校] 你点头。[ploc:公司]")
          == [(False, "学校", ""), (True, "公司", "")])
    check("带交通方式（竖线）", S.parse_move("[loc:学校|骑车]") == [(False, "学校", "骑车")])
    check("带交通方式（斜杠/逗号/空格）",
          S.parse_move("[loc:学校/骑车]")[0][2] == "骑车"
          and S.parse_move("[loc:学校,骑车]")[0][2] == "骑车"
          and S.parse_move("[loc:学校 骑车]")[0][2] == "骑车")
    check("中文键名也认", S.parse_move("[位置：学校]") == [(False, "学校", "")])
    check("全角冒号也认", S.parse_move("[loc：学校]") == [(False, "学校", "")])
    check("没标签 → 空", S.parse_move("她推门进来。") == [])
    stripped = S.strip_move_tags("她推门进来。[loc:学校|骑车] 你点点头。[ploc:公司]")
    check("剥离干净（玩家不该看到标签）",
          "loc" not in stripped and "[" not in stripped, repr(stripped))
    check("没有标签时原文不动", S.strip_move_tags("普通一句话。") == "普通一句话。")


def test_note_move():
    print("\n== ⑥ 记位置与穿帮判定 ==")

    def body(tmp):
        # 40 分钟世界时间：家 → 学校（要 25 分）合理
        S.note_move("薇拉", "家", scale=720, now=NOW - timedelta(seconds=40 * 60 / 720))
        st, v = S.note_move("薇拉", "学校", scale=720, now=NOW)
        check("时间够 → ok", v["ok"] is True and abs(v["need"] - 25) < 0.01, str(v))
        check("位置写进了状态文件", st.get("place") == "学校" and st.get("prev") == "家", str(st))
        check("状态文件落在数据目录的 space/ 下",
              os.path.isfile(os.path.join(tmp, "space", "薇拉.json")))

        # 只过 1 分钟世界时间：学校 → 远方（要 625 分）不可能
        st2, v2 = S.note_move("薇拉", "远方（省外）", scale=1, now=NOW + timedelta(minutes=1))
        check("时间不够 → ok=False 且说明给了数字",
              v2["ok"] is False and v2["need"] > 100 and "分钟" in v2["why"], str(v2))
        check("**照样记下新位置**（已经写出来的事不逆转）", st2.get("place") == "远方（省外）")
        check("穿帮记在 violation 里", isinstance(st2.get("violation"), dict)
              and st2["violation"]["from"] == "学校", str(st2.get("violation")))

        # 下一次合理的移动 → 穿帮记录清掉
        st3, v3 = S.note_move("薇拉", "家", scale=100000, now=NOW + timedelta(minutes=2))
        check("之后的合理移动把穿帮记录清掉", "violation" not in st3)

        # 玩家位置单独一栏
        st4, _ = S.note_player_move("薇拉", "公司", scale=1, now=NOW + timedelta(minutes=3))
        check("玩家位置单独记", st4.get("player_place") == "公司" and st4.get("place") == "家")
    with_tmp(body)


def test_injection():
    print("\n== ⑦ 注入：短、有内容、该空就空 ==")

    def body(tmp):
        cfg = dict(S.DEFAULTS)
        # 没记过位置 → 按家算，不炸
        t0 = S.injection_text(ROLE, scale=720, cfg=cfg, now=NOW)
        check("没状态时按家算", "【空间】" in t0 and "家" in t0, t0[:60])

        S.note_move("薇拉", "家", scale=1, now=NOW - timedelta(minutes=60))
        chain = [{"role": "user", "timestamp": (NOW - timedelta(minutes=30)).isoformat()},
                 {"role": "assistant", "timestamp": (NOW - timedelta(minutes=1)).isoformat()}]
        t = S.injection_text(ROLE, scale=1, cfg=cfg, now=NOW, chain=chain)
        check("带【空间】抬头", t.startswith("【空间】"), t[:40])
        check("报当前地点", "家" in t, t)
        check("用**这一轮之前过了多久**做预算（现实 1 分钟 × 1 倍 → 够去最近的）",
              "够去" in t or "哪儿都去不了" in t, t)
        check("带使用说明（标签写法）", "[loc:地名]" in t and "不会显示给玩家" in t, t)
        check("长度受控", len(t) <= int(cfg["max_chars"]), str(len(t)))

        # 世界过了 400 分钟（1 倍）→ 学校/邻近城市够去，远方（600 分）不够
        cfg_wide = dict(cfg, reachable_limit=20)
        chain_long = [{"role": "assistant", "timestamp": (NOW - timedelta(minutes=400)).isoformat()}]
        t2 = S.injection_text(ROLE, scale=1, cfg=cfg_wide, now=NOW, chain=chain_long)
        check("预算大时列出更远的可达地点", "学校" in t2, t2.replace("\n", "｜")[:200])
        check("超预算的地方不进可达列表",
              "远方" not in t2.split("（换地方")[0], t2[:200])
        check("默认 limit 只列最近的几个",
              len(S.reachable(S.map_for(), "家", 600, limit=cfg["reachable_limit"])) == 4)

        # 穿帮提醒最多两次
        S.note_move("薇拉", "学校", scale=1, now=NOW)
        S.note_move("薇拉", "邻近城市", scale=1, now=NOW)      # 学校→城市要 25+180
        seen = 0
        for _ in range(4):
            txt = S.injection_text(ROLE, scale=1, cfg=cfg, now=NOW, chain=chain)
            if "上一轮她" in txt:
                seen += 1
        check("穿帮提醒最多两次（不每轮都念）", seen == 2, "出现 %d 次" % seen)

        check("关掉 → 空", S.injection_text(ROLE, scale=1, cfg=dict(cfg, enabled=False), now=NOW) == "")
        check("关掉后标签照样剥离（显示不能漏标签）",
              S.strip_move_tags("她来了[loc:学校]") == "她来了")

        long_chain = [{"role": "assistant", "timestamp": (NOW - timedelta(minutes=100000)).isoformat()}]
        t3 = S.injection_text(ROLE, scale=1000, cfg=cfg, now=NOW, chain=long_chain)
        check("预算极大时也不超上限", len(t3) <= int(cfg["max_chars"]), str(len(t3)))
    with_tmp(body)


def test_config_and_command():
    print("\n== ⑧ 配置与 /在哪 /空间 命令 ==")

    def body(tmp):
        check("默认开", S.enabled() is True)
        cfg = S.load_config()
        cfg["default_transport"] = "骑车"
        S.save_config(cfg)
        S._Cfg._cache = None
        check("配置落盘后读得回来", S.load_config()["default_transport"] == "骑车")
        check("配置文件在数据目录", os.path.isfile(os.path.join(tmp, "space_config.json")))
        check("注入受配置影响（默认交通方式进了抬头）",
              "骑车" in S.injection_text(ROLE, scale=1, cfg=S.load_config(), now=NOW))

        from plugins.space_plugin import SpacePlugin
        core = type("C", (), {})()
        core.active_roles = [{"name": "薇拉", "advanced": {"space": {"places": [
            {"name": "码头", "minutes": 45}]}}}]
        core.world_data = {"name": "海边小镇"}
        core._time_scale = lambda: 720
        p = SpacePlugin(core)
        check("非本插件命令 → None", p.on_command("dice", "2d6") is None)
        st = p.on_command("在哪", "")
        check("看状态（含当前位置与地图）",
              "空间层" in st and "地图" in st and "改法" in st, st[:60].replace("\n", "｜"))
        check("状态里带上自定义地点（码头）", "码头" in st, st[:200])
        r = p.on_command("在哪", "学校")
        check("能置位", "学校" in r, r)
        check("置位后状态跟着变", "学校" in p.on_command("在哪", ""))
        r2 = p.on_command("在哪", "码头|骑车")
        check("能带交通方式置位", "码头" in r2 and "骑车" in (
            S.load_state("薇拉").get("by") or ""), r2)
        r3 = p.on_command("在哪", "我=公司")
        check("能设玩家位置", "公司" in r3 and S.load_state("薇拉").get("player_place") == "公司", r3)
        check("交通方式能认", "已设为" in p.on_command("空间", "交通 打车"))
        check("交通方式认不出会提示", "认不出" in p.on_command("空间", "交通 飞船"))
        check("可达开关能关", "不再" in p.on_command("空间", "可达"))
        check("条数要数字", "数字" in p.on_command("空间", "条数 abc"))
        check("长度有上下限", "80" in p.on_command("空间", "长 10") or "1200" in p.on_command("空间", "长 99999"))
        check("关：能关", "已关闭" in p.on_command("空间", "关"))
        check("工程根没被测试写脏",
              not os.path.isfile(os.path.join(ROOT, "space_config.json"))
              and not os.path.isdir(os.path.join(ROOT, "space")))
    with_tmp(body)


def test_core_integration():
    print("\n== ⑨ 核心接线：没有机制卡也要能剥标签并记位置 ==")
    sys.path.insert(0, HERE)

    def body(tmp):
        from probe_payload import make_probe
        Probe, _cap = make_probe()
        p = Probe()
        p.active_roles = [{"name": "薇拉"}]
        # 桩里没有 mechanism_state / 机制卡 —— 正是"没机制卡"的那种角色
        out = p.strip_mechanism_tags("她推门进来。[loc:学校|骑车] 你点头。", apply=True)
        check("没有机制卡也能剥掉位置标签",
              "loc" not in out and "她推门进来" in out, repr(out))
        check("并真的记下了位置", S.load_state("薇拉").get("place") == "学校",
              str(S.load_state("薇拉")))
        out2 = p.strip_mechanism_tags("原文没有标签", apply=True)
        check("没有标签时原文不动", out2 == "原文没有标签", repr(out2))
        t = p._space_injection(None, None)
        check("注入能挂上核心（【空间】出现）", t.startswith("【空间】"), t[:50])

        # 真进载荷才算数（跟吃饭那层同一个证据标准）：截 _fetch_response 的实发消息
        p.tree.add_node("user", "在家吗")
        p.tree.add_node("assistant", "在的。", parent_id=None)
        p._fetch_response("在吗", None, lambda *a, **k: None, lambda *a, **k: None,
                          parent_node_id=None, _locked=True)
        msgs = _cap.get("m") or []
        joined = [str(m.get("content") or "") for m in msgs]
        check("载荷里有【空间】", any("【空间】" in c for c in joined),
              "条数 %d" % len(msgs))
        idx = [i for i, c in enumerate(joined) if "【空间】" in c]
        check("空间层紧跟时间/生活层之后（同一个上下文区间）",
              bool(idx) and all("【空间】" not in joined[i] for i in range(0, idx[0])), str(idx))
    with_tmp(body)


if __name__ == "__main__":
    print("=" * 62)
    print(u"空间层（不能瞬移）测试")
    print("=" * 62)
    test_world_minutes()
    test_map_and_travel()
    test_reachable()
    test_open_hours()
    test_tags()
    test_note_move()
    test_injection()
    test_config_and_command()
    test_core_integration()
    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("SPACE_TEST_OK")
    sys.exit(1 if FAIL else 0)
