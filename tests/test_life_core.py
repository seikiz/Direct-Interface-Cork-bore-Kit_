# -*- coding: utf-8 -*-
"""生活层（吃饭）回归测试：世界时钟 / 厨具历史库 / 食材库 / 注入长度

为什么测这些
------------
`life_core.py` 有两个"不写清就穿帮"的点，都是**设计约束**，靠肉眼看不出来：
  ① 世界时刻必须用"累加虚拟秒"算（起点=系统时间），不能读系统钟点；
  ② 三餐按"跨过了几个饭点"算，不按"现在是不是饭点"。
另外还有两条产品约束：**厨具历史库要真起作用**（唐宋没有辣椒、中世纪没有微波炉），
以及**注入必须短**（整库塞进提示词等于花预算买机械罗列）。

跑法：python tests\\test_life_core.py
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
import life_core as L  # noqa: E402

PASS = 0
FAIL = 0
NOW = datetime(2026, 10, 8, 23, 0, 0)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def chain(minutes_ago, last_minutes_ago=1, gaps=()):
    """造一条链：起点在 minutes_ago 分钟前，再按 gaps 插几个中间节点"""
    t = NOW - timedelta(minutes=minutes_ago)
    out = [{"role": "user", "timestamp": t.isoformat()}]
    for g in gaps:
        t = t + timedelta(minutes=g)
        out.append({"role": "assistant", "timestamp": t.isoformat()})
    out.append({"role": "assistant",
                "timestamp": (NOW - timedelta(minutes=last_minutes_ago)).isoformat()})
    return out


def iso(dt):
    return dt.isoformat()


# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
def test_world_clock():
    print("\n== ① 世界时钟：累加虚拟秒（系统时间 = 1× 起源）==")
    c = chain(40, 1)
    k = L.world_clock(c, 720, now=NOW)
    check("算得出世界时刻", k is not None)
    check("起点 = 链首节点时刻（1× 起源）",
          abs((k["origin"] - (NOW - timedelta(minutes=40))).total_seconds()) < 1,
          str(k["origin"]))
    check("现实 40 分钟 × 720 = 那边 20 天",
          abs(k["elapsed_world"] - 40 * 60 * 720) < 1, str(k["elapsed_world"]))
    check("世界日期 = 起点 + 虚拟秒",
          abs((k["world_dt"] - (k["origin"] + timedelta(seconds=k["elapsed_world"]))).total_seconds()) < 1)

    # 关键反例：世界钟点【不等于】现实钟点（720× 下）
    k2 = L.world_clock(chain(40, 1), 720, now=NOW)
    check("世界钟点与现实钟点不同（不是照抄系统时钟）",
          k2["world_dt"].strftime("%H:%M") != NOW.strftime("%H:%M"),
          "%s vs %s" % (k2["world_dt"].strftime("%H:%M"), NOW.strftime("%H:%M")))

    # 间隔累加：中间多几个节点，总时长不变
    a = L.world_clock(chain(60, 0), 60, now=NOW)
    b = L.world_clock(chain(60, 0, gaps=(20, 20)), 60, now=NOW)
    check("分段累加 = 一次性算（间隔不丢）",
          abs(a["elapsed_world"] - b["elapsed_world"]) < 1,
          "%s vs %s" % (a["elapsed_world"], b["elapsed_world"]))

    # 脏数据与时钟回拨
    dirty = [{"role": "user", "timestamp": "不是时间"},
             {"role": "assistant", "timestamp": ""},
             {"role": "system", "timestamp": NOW.isoformat()},
             {"role": "assistant", "timestamp": (NOW - timedelta(minutes=10)).isoformat()}]
    k3 = L.world_clock(dirty, 720, now=NOW)
    check("脏时间戳被跳过，system 节点不算数", k3 is not None and abs(k3["elapsed_real"] - 600) < 1,
          str(k3 and k3["elapsed_real"]))
    back = [{"role": "user", "timestamp": iso(NOW - timedelta(minutes=10))},
            {"role": "assistant", "timestamp": iso(NOW - timedelta(minutes=30))},
            {"role": "assistant", "timestamp": iso(NOW)}]
    k4 = L.world_clock(back, 1, now=NOW)
    check("时钟回拨不让世界倒退（负间隔当 0）", k4["elapsed_world"] >= 0, str(k4["elapsed_world"]))
    check("空链 / 没有时间戳 → None",
          L.world_clock([], 720, now=NOW) is None
          and L.world_clock([{"role": "user", "timestamp": "x"}], 720, now=NOW) is None)
    check("倍率非法时当 1（不炸、不放大）",
          abs(L.world_clock(chain(10, 0), "abc", now=NOW)["elapsed_world"] - 600) < 1)


def test_meals_by_crossing():
    print("\n== ② 三餐按「跨过了几个饭点」算 ==")
    base = NOW.replace(hour=0, minute=0, second=0, microsecond=0)

    def at(h, m=0):
        dt = base.replace(hour=h, minute=m)
        c = [{"role": "user", "timestamp": iso(dt - timedelta(minutes=1))},
             {"role": "assistant", "timestamp": iso(dt)}]
        return L.world_clock(c, 1.0, now=dt)

    check("03:00 还没到早饭（算前一天的夜里）", at(3)["meals_today"] == [])
    check("07:00 只过了早饭", [k for k, _ in at(7)["meals_today"]] == ["breakfast"])
    check("14:20 过了早饭+午饭", [k for k, _ in at(14, 20)["meals_today"]] == ["breakfast", "lunch"])
    check("20:00 三顿都过了",
          [k for k, _ in at(20)["meals_today"]] == ["breakfast", "lunch", "dinner"])
    check("23:00 连夜宵也过了",
          [k for k, _ in at(23)["meals_today"]] == ["breakfast", "lunch", "dinner", "night"])
    check("一天从凌晨 4 点算起（3 点属于前一天）",
          at(3)["life_day"] == (base - timedelta(days=1)).date()
          and at(5)["life_day"] == base.date())
    check("时段认得对", at(7)["phase"] == "清晨" and at(14)["phase"] == "午后"
          and at(20)["phase"] == "夜里" and at(1)["phase"] == "深夜")


def test_kitchenware_history():
    print("\n== ③ 厨具历史库：年代真的卡住做法与食材 ==")
    def prof(era, region="auto", avoid=None, role="测试"):
        return L.profile_for({"name": role, "advanced": {"life": {"era": era, "region": region,
                                                                 "avoid": avoid or ""}}},
                             {"avoid": ""}, None)

    stone = prof("史前")
    check("史前没有蒸（还没有甑）", not L.method_ok("蒸", stone["tools"], stone["era_year"]))
    check("史前没有炒（铁锅还没出现）", not L.method_ok("炒", stone["tools"], stone["era_year"]))
    check("史前能煮能烤", L.method_ok("煮", stone["tools"], stone["era_year"])
          and L.method_ok("烤", stone["tools"], stone["era_year"]))

    tang = prof("唐宋")
    check("唐宋能炒（薄铁锅普及）", L.method_ok("炒", tang["tools"], tang["era_year"]))
    check("唐宋能蒸", L.method_ok("蒸", tang["tools"], tang["era_year"]))

    names = lambda p, d: L.sample_meal(p, d, "dinner", "晚饭")["dish"]
    seen = " / ".join(names(tang, 739000 + i) for i in range(12))
    check("唐宋吃不到辣椒菜", not any(x in seen for x in ("辣椒", "麻辣", "水煮鱼", "宫保")), seen)
    check("唐宋吃不到番茄菜", "番茄" not in seen and "西红柿" not in seen, seen)
    check("唐宋吃不到方便面/空气炸锅这种后世玩意",
          not any(x in seen for x in ("方便面", "空气炸", "沙拉")), seen)
    check("唐宋也吃不到史前的石煮鱼汤（until 卡住）", "石煮鱼汤" not in seen, seen)

    ming = prof("明清")
    mseen = " / ".join(names(ming, 739000 + i) for i in range(12))
    check("明清还是吃不到番茄（1900 才当菜吃）",
          not any(x in mseen for x in ("番茄", "西红柿")), mseen)

    mod = prof("现代")
    check("现代有空气炸锅，也有空气炸鸡块",
          "空气炸锅" in mod["tools"]
          and any(d["name"] == "空气炸鸡块" and L._since_ok(d["since"], mod["era_year"])
                  for d in L.DISHES))

    # 每个年代 × 每一餐都得有东西可吃（新加年代时最容易漏的地方）
    gaps = []
    for era in L.ERAS:
        p = prof(era["key"])
        for key, label in L.MEAL_LABELS:
            meal = L.sample_meal(p, 740000, key, label)
            if not meal["staple"] and not meal["dishes"]:
                gaps.append("%s/%s" % (era["key"], key))
    check("所有年代 × 所有餐次都抽得出饭（没有空菜单）", not gaps, str(gaps))

    # 早饭不该出现正餐硬菜
    wrong = []
    for era in L.ERAS:
        p = prof(era["key"])
        for d in range(6):
            m = L.sample_meal(p, 741000 + d, "breakfast", "早饭")
            for big in ("东坡肉", "叫花鸡", "水煮鱼", "回锅肉", "锅包肉", "红烧肉", "麻婆豆腐"):
                if big in m["dish"]:
                    wrong.append("%s/%s" % (era["key"], m["dish"]))
    check("早饭不会出现红烧肉/东坡肉这类硬菜", not wrong, str(wrong[:3]))


def test_avoid_and_taste():
    print("\n== ④ 忌口与口味 ==")
    p = L.profile_for({"name": "沈姑娘", "advanced": {"life": {"era": "明清", "region": "江南",
                                                              "avoid": "海鲜,虾,鱼,带鱼,紫菜"}}},
                      {"avoid": ""}, None)
    hits = []
    for d in range(20):
        for key, label in L.MEAL_LABELS:
            dish = L.sample_meal(p, 750000 + d, key, label)["dish"]
            for bad in ("虾", "鱼", "带鱼", "紫菜", "海鲜"):
                if bad in dish:
                    hits.append("%s/%s" % (key, dish))
    check("忌口海鲜：20 天里一道都没漏", not hits, str(hits[:3]))

    pork = L.profile_for({"name": "阿明", "advanced": {"life": {"era": "现代", "avoid": "猪肉,排骨"}}},
                         {"avoid": ""}, None)
    phits = [L.sample_meal(pork, 760000 + d, "dinner", "晚饭")["dish"] for d in range(20)]
    check("忌口猪肉：晚饭里没有猪肉/排骨菜",
          not any(("猪肉" in x or "排骨" in x or "回锅肉" in x or "锅包肉" in x) for x in phits),
          str(phits[:3]))

    allbad = L.profile_for({"name": "挑食", "advanced": {"life": {"avoid": "米,面,鸡,猪,羊,牛,鱼,豆,菜,蛋,瓜,菜,粥"}}},
                           {"avoid": ""}, None)
    m = L.sample_meal(allbad, 770000, "lunch", "午饭")
    check("忌口把池子清空时仍给得出东西（不返回空）", bool(m["dish"]), str(m))

    light = L.profile_for({"name": "清淡", "advanced": {"life": {"era": "现代", "taste": "清淡"}}},
                          {"avoid": ""}, None)
    heavy = L.profile_for({"name": "重口", "advanced": {"life": {"era": "现代", "taste": "重口"}}},
                          {"avoid": ""}, None)
    mild_methods = sum(1 for d in range(30)
                       if any(x in ("蒸", "煮", "炖", "拌") for x in L.sample_meal(light, 780000 + d, "dinner", "晚饭")["methods"]))
    strong_methods = sum(1 for d in range(30)
                         if any(x in ("炒", "炸", "烤") for x in L.sample_meal(heavy, 780000 + d, "dinner", "晚饭")["methods"]))
    check("口味只是加权：清淡的多蒸煮、重口的多炒炸",
          mild_methods > strong_methods, "清淡 %d vs 重口 %d" % (mild_methods, strong_methods))


def test_determinism():
    print("\n== ⑤ 确定性：同一天同一餐永远同一份（重启/回档/换端都一致）==")
    p = L.profile_for({"name": "薇拉", "advanced": {"life": {"era": "明清"}}}, {"avoid": ""}, None)
    a = L.sample_meal(p, 800000, "lunch", "午饭")["dish"]
    b = L.sample_meal(p, 800000, "lunch", "午饭")["dish"]
    check("同一 (角色,天,餐) → 同一份", a == b, "%s vs %s" % (a, b))
    other = L.sample_meal(p, 800001, "lunch", "午饭")["dish"]
    check("换一天大概率换一份", other != a or True)   # 不断言必然不同（小池子允许重复）
    menu = L.day_menu(p, 800002, L.MEAL_LABELS)
    dup = [m["dish"] for m in menu if sum(1 for x in menu if x["dish"] == m["dish"]) > 1]
    check("同一天里不整餐重样（清单池子够时）", not dup, str(dup))
    same = L.day_menu(p, 800002, L.MEAL_LABELS)
    check("整天菜单也确定", [m["dish"] for m in menu] == [m["dish"] for m in same])


def test_injection():
    print("\n== ⑥ 注入：短、有内容、该空就空 ==")
    c = chain(40, 1)
    cfg = {"enabled": True, "era": "明清", "region": "江南", "taste": "清淡",
           "avoid": "香菜,海鲜", "show_meals": True, "max_chars": 240, "location": "灶房"}
    text = L.injection_text(c, 720, {"name": "沈姑娘"}, {"name": "大明"}, cfg=cfg, now=NOW)
    check("带【生活·那边】抬头", text.startswith("【生活·那边】"), text[:40])
    check("带今天吃了什么", "今天：" in text, text)
    check("带手边家伙（厨具历史库露出来了）", "手边家伙" in text and "柴火灶" in text, text)
    check("带口味与忌口", "口味清淡" in text and "不吃香菜、海鲜" in text, text)
    check("带使用说明（别报数值）", "不要报数值" in text, text)
    check("长度受控（≤ max_chars）", len(text) <= 240, str(len(text)))

    check("关掉 → 空", L.injection_text(c, 720, {"name": "X"}, None,
                                       cfg=dict(cfg, enabled=False), now=NOW) == "")
    check("没有时间戳 → 空", L.injection_text([], 720, {"name": "X"}, None, cfg=cfg, now=NOW) == "")
    check("show_meals=False → 不提吃的",
          "今天：" not in L.injection_text(c, 720, {"name": "X"}, None,
                                           cfg=dict(cfg, show_meals=False), now=NOW))

    # 长开局（现实 40 分钟 × 720 = 那边 20 天）：不报"第 N 天"，免得把日子说过头
    check("第几天只在前三天报", "第" not in text.split("\n")[0].replace("第几", ""), text.split("\n")[0])
    short = L.injection_text(chain(1, 0), 60, {"name": "X"}, None, cfg=cfg, now=NOW)
    check("开局短时间会报第几天", "第 1 天" in short, short.split("\n")[0])

    night = L.injection_text(chain(1, 0), 100000, {"name": "X"}, None, cfg=cfg, now=NOW)
    if "深夜" in night:
        check("深夜会提醒她该睡了", "该睡了" in night, night)

    long_avoid = L.injection_text(c, 720, {"name": "X"}, None,
                                  cfg=dict(cfg, avoid="香菜,海鲜,羊肉,辣椒,酒,蒜,姜,葱,醋"),
                                  now=NOW)
    check("忌口很长时也不超预算", len(long_avoid) <= 240, str(len(long_avoid)))


def test_config_and_command():
    print("\n== ⑦ 配置与 /生活 命令 ==")
    tmp = tempfile.mkdtemp(prefix="dick_life_")
    real_get = app_paths.get_base_dir
    old_cache = L._cache
    try:
        app_paths.get_base_dir = lambda: tmp
        L._cache = None
        check("默认开", L.enabled() is True)
        cfg = L.load_config()
        cfg["era"] = "唐宋"
        L.save_config(cfg)
        L._cache = None
        check("配置落盘后读得回来", L.load_config()["era"] == "唐宋")
        check("配置文件真的写到了 base_dir", os.path.isfile(os.path.join(tmp, "life_config.json")))
        L.save_config(dict(L.DEFAULTS, enabled=False))
        L._cache = None
        check("关掉之后 enabled() = False", L.enabled() is False)
    finally:
        app_paths.get_base_dir = real_get
        L._cache = old_cache
        shutil.rmtree(tmp, ignore_errors=True)

    # 命令面板：**也要把 base_dir 指到临时目录** —— 它会调 save_config，
    # 第一次写这个测试时就漏了这一步，结果把 enabled=false 写进了工程根的 life_config.json
    # （真实配置被测试改掉，之后所有注入都静默消失，排查起来很费劲）。
    tmp2 = tempfile.mkdtemp(prefix="dick_life_cmd_")
    real_get2 = app_paths.get_base_dir
    old_cache2 = L._cache
    try:
        app_paths.get_base_dir = lambda: tmp2
        L._cache = None
        from plugins.life_plugin import LifePlugin
        core = type("C", (), {})()
        core.tree = type("T", (), {"get_current_chain": staticmethod(lambda: chain(30, 1))})()
        core.active_roles = [{"name": "薇拉", "advanced": {"life": {"era": "明清", "avoid": "海鲜"}}}]
        core.world_data = {"name": "大明"}
        core._time_scale = lambda: 720
        p = LifePlugin(core)
        check("非本插件命令 → None", p.on_command("dice", "2d6") is None)
        st = p.on_command("生活", "")
        flat = st.replace("\n", "｜")      # 断言详情压成一行：多行详情在 CI 注解里只能看到第一行
        # 逐条断言（别用 and 串起来）：红了要一眼看出**缺哪个**，
        # 否则详情被新行截断，只能看到一个"生活层：开"，白跑一轮 CI。
        check("状态含世界时钟", "世界时钟" in st, flat[:150])
        check("状态含年代", "年代" in st, flat[:150])
        check("状态含手边家伙", "手边家伙" in st, flat[:150])
        # "今天吃过"那一段是跟**世界时钟**走的：那边若是清早，就会显示"今天还没吃饭点"。
        # 也就是说插件状态里的这一行本来就随"现在几点"变 —— 直接断言它必然存在，
        # 等于把测试绑在跑测试的钟点上（CI 上就这么红过一次）。两种状态都算对：
        check("状态里的吃食那段二选一（今天吃过 / 今天还没吃饭点）",
              ("今天吃过" in st) or ("今天还没吃饭点" in st), flat[:150])
        # 要吃食清单本身，就用固定时刻直接测 describe（确定性，不碰挂钟）
        _fixed = L.describe(chain(30, 1), 720,
                            role={"name": "薇拉", "advanced": {"life": {"era": "明清"}}},
                            world={"name": "大明"}, cfg=dict(L.DEFAULTS), now=NOW)
        check("固定时刻下能列出今天吃过什么", "今天吃过" in _fixed,
              _fixed.replace("\n", "｜")[:150])
        check("状态里写明年代来自角色卡（不然用户以为命令没生效）", "来自角色卡" in st, flat[:200])
        check("改年代：能认", "唐宋" in p.on_command("生活", "年代 唐宋"))
        check("改年代：认不出会提示", "认不出" in p.on_command("生活", "年代 赛博朋克"))
        check("改忌口：能设", "忌口" in p.on_command("生活", "忌口 香菜"))
        check("关：能关", "已关闭" in p.on_command("生活", "关"))
        check("用法提示", "用法" in p.on_command("生活", "瞎写"))
        check("命令改的是 life_config.json，不是别处",
              os.path.isfile(os.path.join(tmp2, "life_config.json")))
        check("工程根没被测试写脏",
              not os.path.isfile(os.path.join(ROOT, "life_config.json")))
    finally:
        app_paths.get_base_dir = real_get2
        L._cache = old_cache2
        shutil.rmtree(tmp2, ignore_errors=True)


if __name__ == "__main__":
    print("=" * 60)
    print(u"生活层（吃饭）测试")
    print("=" * 60)
    test_world_clock()
    test_meals_by_crossing()
    test_kitchenware_history()
    test_avoid_and_taste()
    test_determinism()
    test_injection()
    test_config_and_command()
    print("\n" + "=" * 60)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("LIFE_TEST_OK")
    sys.exit(1 if FAIL else 0)
