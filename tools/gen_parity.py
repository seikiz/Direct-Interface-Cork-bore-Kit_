# -*- coding: utf-8 -*-
"""gen_parity.py —— 从电脑端的表/逻辑生成手机端的 Kotlin 表与对拍基准。

为什么这么做
------------
手机端要补生活层（吃饭）、空间层（不能瞬移）和常识库（年代 → 地点/交通/屋里）。
如果把年代、厨具、食材、地点这些表在 Kotlin 里**手抄一遍**，就一定会漂：
电脑端改了"辣椒明末才传入"，手机端忘了改，同一个角色在两端吃的东西不一样。

所以定两个规矩：

  ① **表只有一份真相**（Python 那几张表）→ 本脚本生成 `Tables.kt`；
  ② **行为要能对拍** → 本脚本把 Python 算出来的结果冻成 `ParityGoldens.kt`，
     手机端 `selftest` 用同样的输入算一遍，不许有差别（菜单是确定性抽样，
     种子 = 角色｜世界第几天｜哪一餐，所以"两端算出同一份菜单"是**可以验证**的）。

跑法：
    python tools/gen_parity.py            # 重新生成两个文件
    python tools/gen_parity.py --check    # 只检查是不是最新的（CI / 测试用，不写盘）
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app_paths          # noqa: E402
import commonsense as CS  # noqa: E402
import life_core as L     # noqa: E402
import space_core as S    # noqa: E402

AND = os.path.join(ROOT, "DICK-Android")
OUT_TABLES = os.path.join(AND, "app", "src", "main", "java", "com", "dick", "core", "Tables.kt")
OUT_GOLDENS = os.path.join(AND, "selftest", "ParityGoldens.kt")
# 世界卡库（world_packs/）要进 APK 才能<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌"装好就能用"：assets 里的那份是**复制品**，
# 由这里同步 —— 手改 assets 会被 --check 逮住（复制品不许有自己的想法）。
PACKS_SRC = os.path.join(ROOT, "world_packs")
ASSETS_PACKS = os.path.join(AND, "app", "src", "main", "assets", "world_packs")

HEADER = (u"// ⚠ 生成物：由 tools/gen_parity.py 从 life_core.py / space_core.py / commonsense.py\n"
          u"//   生成。别手改 —— 手改会被 `python tools/gen_parity.py --check` 判为过期，\n"
          u"//   而且下一次生成就没了。要改表就改 Python 那边，然后重新生成。\n")


# ============================================================
#  一、Kotlin 字面量
# ============================================================
def kstr(s):
    out = json.dumps(u"" if s is None else u"%s" % s, ensure_ascii=False)
    return out.replace(u"$", u"\\$")


def kd(v):
    v = float(v)
    if v == int(v) and abs(v) < 1e15:
        return u"%d.0" % int(v)
    return repr(v)


def kint(v):
    return u"%d" % int(v)


def kbool(v):
    return u"true" if v else u"false"


def koptint(v):
    return u"null" if v is None else kint(v)


def kstrlist(items):
    items = list(items or [])
    if not items:
        return u"emptyList()"
    return u"listOf(%s)" % u", ".join(kstr(x) for x in items)


def kdblpairs(items):
    items = list(items or [])
    if not items:
        return u"emptyList()"
    return u"listOf(%s)" % u", ".join(u"%s to %s" % (kstr(a), kd(b)) for a, b in items)


def kplace_triples(items):
    """(名字, 分钟, 是不是屋里) —— 排序交给测试，这里不排。"""
    items = list(items or [])
    if not items:
        return u"emptyList()"
    return u"listOf(%s)" % u", ".join(
        u"Triple(%s, %s, %s)" % (kstr(a), kd(b), kbool(c)) for a, b, c in items)


# ============================================================
#  二、Tables.kt
# ============================================================
def gen_tables():
    o = []
    o.append(HEADER)
    o.append(u"package com.dick.core\n")

    # ---------- 生活层 ----------
    o.append(u"/** 厨具历史库 + 食材/做法库 + 餐次/时段（来自 life_core.py）。 */")
    o.append(u"object LifeTables {\n")
    o.append(u"    val ERAS: List<LifeEra> = listOf(")
    for e in L.ERAS:
        o.append(u"        LifeEra(key = %s, name = %s, year = %s, tools = %s, note = %s),"
                 % (kstr(e["key"]), kstr(e["name"]), kint(e["year"]),
                    kstrlist(e["tools"]), kstr(e["note"])))
    o.append(u"    )")
    o.append(u"    val ERA_BY_KEY: Map<String, LifeEra> = ERAS.associateBy { it.key }\n")

    o.append(u"    /** 世界卡关键词 → 年代（越具体越优先，顺序就是优先级）。 */")
    o.append(u"    val ERA_HINTS: List<Pair<String, List<String>>> = listOf(")
    for key, hints in L.ERA_HINTS:
        o.append(u"        %s to %s," % (kstr(key), kstrlist(hints)))
    o.append(u"    )\n")

    o.append(u"    /** 做法 → 需要什么家伙才做得了（关键词宽松匹配）。 */")
    o.append(u"    val METHOD_NEEDS: Map<String, List<String>> = linkedMapOf(")
    for k, v in L.METHOD_NEEDS.items():
        o.append(u"        %s to %s," % (kstr(k), kstrlist(v)))
    o.append(u"    )")
    o.append(u"    val METHOD_SINCE: Map<String, Int> = linkedMapOf(")
    for k, v in L.METHOD_SINCE.items():
        o.append(u"        %s to %s," % (kstr(k), kint(v)))
    o.append(u"    )\n")

    def emit_items(name, items, has_method):
        o.append(u"    val %s: List<LifeItem> = listOf(" % name)
        for it in items:
            o.append(u"        LifeItem(name = %s, since = %s, until = %s, regions = %s, meals = %s,"
                     u" method = %s, ingredients = %s),"
                     % (kstr(it["name"]), kint(it.get("since", 0)), koptint(it.get("until")),
                        kstrlist(it.get("regions")), kstrlist(it.get("meals")),
                        kstr(it.get("method", "")) if has_method else kstr(u""),
                        kstrlist(it.get("ingredients")) if has_method else u"emptyList()"))
        o.append(u"    )\n")

    emit_items(u"STAPLES", L.STAPLES, False)
    emit_items(u"DISHES", L.DISHES, True)
    emit_items(u"DRINKS", L.DRINKS, False)

    o.append(u"    /** 时段（给模型一个「现在该干什么」的常识锚）。 */")
    o.append(u"    val PHASES: List<Pair<Int, String>> = listOf(%s)"
             % u", ".join(u"%s to %s" % (kint(a), kstr(b)) for a, b in L.PHASES))
    o.append(u"    const val LIFE_DAY_START_HOUR: Int = %s" % kint(L.LIFE_DAY_START_HOUR))
    o.append(u"    /** (key, 名字, 饭点开始小时) */")
    o.append(u"    val MEALS: List<Triple<String, String, Double>> = listOf(%s)"
             % u", ".join(u"Triple(%s, %s, %s)" % (kstr(a), kstr(b), kd(c)) for a, b, c in L.MEALS))
    o.append(u"    val MEAL_LABELS: List<Pair<String, String>> = listOf(%s)"
             % u", ".join(u"%s to %s" % (kstr(a), kstr(b)) for a, b in L.MEAL_LABELS))
    o.append(u"    val REGIONS: List<String> = %s" % kstrlist(L.REGIONS))
    d = L.DEFAULTS
    o.append(u"    val DEFAULTS: LifeConfig = LifeConfig(enabled = %s, era = %s, region = %s,"
             u" taste = %s, avoid = %s, showMeals = %s, maxChars = %s, location = %s)"
             % (kbool(d["enabled"]), kstr(d["era"]), kstr(d["region"]), kstr(d["taste"]),
                kstr(d["avoid"]), kbool(d["show_meals"]), kint(d["max_chars"]), kstr(d["location"])))
    o.append(u"}\n")

    # ---------- 常识库 ----------
    o.append(u"/** 年代 → 地点 / 交通 / 屋里（来自 commonsense.py）。 */")
    o.append(u"object CommonsenseTables {\n")
    o.append(u"    val ERAS: Map<String, CsEra> = linkedMapOf(")
    for key, e in CS.ERAS.items():
        places = u", ".join(u"CsPlace(%s, %s)" % (kstr(n), kd(m)) for n, m in e["places"])
        tr = u", ".join(u"%s to %s" % (kstr(a), kd(b)) for a, b in e["transports"].items())
        o.append(u"        %s to CsEra(places = listOf(%s), transports = linkedMapOf(%s),"
                 u" rooms = %s, notes = %s),"
                 % (kstr(key), places, tr, kstrlist(e["rooms"]), kstr(e["notes"])))
    o.append(u"    )")
    o.append(u"    const val DEFAULT_ERA: String = %s" % kstr(CS.DEFAULT_ERA))
    o.append(u"    val KINDS: List<String> = %s" % kstrlist(CS.KINDS))
    o.append(u"}\n")

    # ---------- 空间层 ----------
    sd = S.DEFAULTS
    o.append(u"/** 交通系数与默认值（来自 space_core.py；交通**以年代表为准**，这里只是认不出名字时的兜底）。 */")
    o.append(u"object SpaceTables {\n")
    o.append(u"    const val HUB: String = %s" % kstr(S.HUB))
    o.append(u"    const val DEFAULT_TRANSPORT: String = %s" % kstr(S.DEFAULT_TRANSPORT))
    o.append(u"    const val DEFAULT_ERA_FALLBACK: String = %s" % kstr(S.DEFAULT_ERA_FALLBACK))
    o.append(u"    const val MAX_MINUTES: Double = %s" % kd(S.MAX_MINUTES))
    o.append(u"    const val ROOM_MINUTES: Double = %s" % kd(S.ROOM_MINUTES))
    o.append(u"    /** 跨年代通用写法（打车/高铁…）：只当系数兜底，不并进地图。 */")
    o.append(u"    val TRANSPORT: Map<String, Double> = linkedMapOf(%s)"
             % u", ".join(u"%s to %s" % (kstr(a), kd(b)) for a, b in S.TRANSPORT.items()))
    o.append(u"    val DEFAULTS: SpaceConfig = SpaceConfig(enabled = %s, maxChars = %s,"
             u" showReachable = %s, reachableLimit = %s, defaultTransport = %s,"
             u" warnWhenImpossible = %s, stateDir = %s)"
             % (kbool(sd["enabled"]), kint(sd["max_chars"]), kbool(sd["show_reachable"]),
                kint(sd["reachable_limit"]), kstr(sd["default_transport"]),
                kbool(sd["warn_when_impossible"]), kstr(sd["state_dir"])))
    o.append(u"}\n")
    return u"\n".join(o)


# ============================================================
#  三、对拍基准
# ============================================================
def jdump(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=False)


ROLE_ALING = {u"name": u"阿绫", u"advanced": {}}
ROLE_SHEN = {u"name": u"沈砚", u"advanced": {u"life": {u"era": u"民国", u"region": u"粤",
                                                     u"taste": u"清淡", u"avoid": u"辣椒"},
                                             u"space": {u"places": [{u"name": u"报馆", u"minutes": 35}],
                                                        u"rooms": [u"亭子间"]}}}
ROLE_1950 = {u"name": u"周素芬", u"advanced": {u"life": {u"era": u"1950s"}}}

WORLD_URBAN = {u"name": u"现代都市·合租", u"description": u"地铁与便利店都在楼下",
               u"params": {}}
WORLD_MING = {u"name": u"江南水乡·明末", u"description": u"大明万历年间的江南小镇",
              u"params": {u"era": u"明清"}}
WORLD_XIANXIA = {u"name": u"仙侠·云梦宗", u"description": u"宗门立于云上",
                 u"params": {u"era": u"唐宋", u"era_kind": u"仙侠"}}
WORLD_WASTE = {u"name": u"末世·废土据点", u"description": u"路断了，油要省",
               u"params": {u"era_kind": u"末世"}}

WORLD_CUSTOM_SPACE = {
    u"name": u"校园日常",
    u"description": u"六月，栀子花开",
    u"params": {u"space": json.dumps({
        u"places": [{u"name": u"教学楼", u"minutes": 6},
                    {u"name": u"食堂", u"minutes": 8, u"open": [6, 20]},
                    {u"name": u"图书馆", u"minutes": 10, u"open": [8, 22]},
                    {u"name": u"便利店", u"minutes": 5, u"open": [22, 2]}],
        u"home": u"宿舍",
        u"rooms": [u"卧室", u"阳台"],
        u"transport": {u"走路": 1.0, u"骑车": 0.4},
        u"links": {u"教学楼|图书馆": 3},
    }, ensure_ascii=False)},
}
WORLD_MERGE_SPACE = {
    u"name": u"现代都市·加班版",
    u"params": {u"space": json.dumps({
        u"merge": True,
        u"places": [{u"name": u"公司", u"minutes": 35}, {u"name": u"夜宵摊", u"minutes": 9}],
        u"rooms": [u"卧室", u"客厅", u"厨房"],
    }, ensure_ascii=False)},
}
WORLD_DICT_SPACE = {
    u"name": u"地图直接写在 params 里",
    u"params": {u"space": {u"places": [{u"name": u"码头", u"minutes": 45}], u"home": u"船屋"}},
}


def cfg_life(**kw):
    d = dict(L.DEFAULTS)
    d.update(kw)
    return d


def life_era_cases():
    cases = []
    for label, world, role in (
            (u"现代都市", WORLD_URBAN, None),
            (u"明末江南", WORLD_MING, None),
            (u"仙侠（era=唐宋 + kind=仙侠）", WORLD_XIANXIA, None),
            (u"末世（只有 kind）", WORLD_WASTE, None),
            (u"角色卡写年代", None, ROLE_1950),
            (u"角色卡压过世界卡", WORLD_MING, ROLE_SHEN),
            (u"什么都没有", None, None)):
        cases.append({
            "label": label,
            "worldJson": jdump(world) if world else "",
            "roleJson": jdump(role) if role else "",
            "lifeEra": L.detect_era(world),
            "csEra": CS.detect_era(world, role),
            "csKind": CS.detect_kind(world, role),
        })
    return cases


def life_menu_cases():
    raw = [
        (u"唐宋江南清淡", ROLE_ALING, WORLD_MING, cfg_life(era=u"唐宋", region=u"江南", taste=u"清淡"), 739000,
         [u"breakfast", u"lunch", u"dinner", u"night"]),
        (u"史前只有火", ROLE_ALING, None, cfg_life(era=u"史前"), 738900, [u"lunch", u"dinner"]),
        (u"川渝重口＋忌口", ROLE_SHEN, WORLD_URBAN, cfg_life(era=u"现代", region=u"川渝", taste=u"重口",
                                                          avoid=u"香菜,海鲜"), 739500,
         [u"breakfast", u"night"]),
        (u"明清粤菜忌猪肉", ROLE_ALING, WORLD_MING, cfg_life(era=u"明清", region=u"粤", avoid=u"猪肉"), 739100,
         [u"lunch"]),
        (u"1950s 北方一天三顿", ROLE_ALING, None, cfg_life(era=u"1950s", region=u"北方"), 739200,
         [u"breakfast", u"lunch", u"dinner"]),
        (u"嗜甜早饭", ROLE_ALING, WORLD_URBAN, cfg_life(era=u"现代", taste=u"嗜甜"), 739300, [u"breakfast"]),
        (u"角色卡盖过配置", ROLE_SHEN, WORLD_URBAN, cfg_life(era=u"现代", region=u"川渝"), 739400, [u"dinner"]),
        (u"史前夜宵（多半没得吃）", ROLE_ALING, None, cfg_life(era=u"史前", region=u"粤",
                                                            avoid=u"野菜,鱼,野味"), 739600, [u"night"]),
        (u"仙侠（kind 不影响吃）", ROLE_ALING, WORLD_XIANXIA, cfg_life(region=u"江南"), 739700,
         [u"lunch", u"night"]),
    ]
    cases = []
    labels = dict(L.MEAL_LABELS)
    for label, role, world, cfg, day, meal_keys in raw:
        profile = L.profile_for(role, cfg, world)
        menu = L.day_menu(profile, day, [(k, labels[k]) for k in meal_keys])
        dishes = []
        for m in menu:
            dishes.append(u"%s|%s|%s|%s|%s" % (m["meal"], m["staple"], u",".join(m["dishes"]),
                                                m["drink"], u",".join(m["methods"])))
        cases.append({
            "label": label,
            "roleJson": jdump(role),
            "worldJson": jdump(world) if world else "",
            "cfgJson": jdump(cfg),
            "lifeDay": int(day),
            "meals": list(meal_keys),
            "dishes": dishes,
        })
    return cases


def life_inject_cases():
    base = datetime(2026, 5, 4, 7, 30, 0)
    raw = [
        (u"现代白天", [u"user", u"assistant", u"user"], base, 1.0, base + timedelta(minutes=50),
         ROLE_ALING, WORLD_URBAN, cfg_life()),
        (u"720× 隔世", [u"user", u"assistant"], base, 720.0, base + timedelta(minutes=3),
         ROLE_ALING, WORLD_MING, cfg_life()),
        (u"深夜", [u"user"], datetime(2026, 5, 4, 2, 10, 0), 1.0, datetime(2026, 5, 4, 2, 40, 0),
         ROLE_ALING, WORLD_URBAN, cfg_life()),
        (u"不开菜单", [u"user", u"assistant"], base, 1.0, base + timedelta(minutes=40),
         ROLE_ALING, WORLD_URBAN, cfg_life(show_meals=False)),
        (u"关掉生活层", [u"user"], base, 1.0, base, ROLE_ALING, WORLD_URBAN, cfg_life(enabled=False)),
        (u"没有时间戳", [u"system", u"system"], base, 1.0, base, ROLE_ALING, WORLD_URBAN, cfg_life()),
        (u"忌口与口味", [u"user"], base, 1.0, base + timedelta(minutes=20), ROLE_SHEN, WORLD_URBAN,
         cfg_life(region=u"川渝", taste=u"重口", avoid=u"香菜,海鲜")),
        (u"预算很小", [u"user"], base, 1.0, base + timedelta(minutes=20), ROLE_ALING, WORLD_URBAN,
         cfg_life(max_chars=120)),
        (u"第 2 天也报天数", [u"user"], base, 1.0, base + timedelta(hours=20), ROLE_ALING, WORLD_URBAN,
         cfg_life()),
    ]
    cases = []
    for label, roles, t0, scale, now, role, world, cfg in raw:
        stamps = [t0 + timedelta(minutes=7 * i) for i in range(len(roles))]
        chain = [{"role": r, "timestamp": s.isoformat()} for r, s in zip(roles, stamps)]
        expect = L.injection_text(chain, scale=scale, role=role, world=world, cfg=cfg, now=now)
        cases.append({
            "label": label,
            "roles": list(roles),
            "stamps": [s.isoformat() for s in stamps],
            "scale": float(scale),
            "nowIso": now.isoformat(),
            "roleJson": jdump(role),
            "worldJson": jdump(world) if world else "",
            "cfgJson": jdump(cfg),
            "expect": expect,
        })
    return cases


def life_describe_cases():
    """`/生活` 面板的整段文本也要两端一致（不然同一个命令两个样子）。"""
    base = datetime(2026, 5, 4, 8, 0, 0)
    raw = [
        (u"现代白天", [u"user", u"assistant"], base, 1.0, base + timedelta(minutes=40),
         ROLE_ALING, WORLD_URBAN, cfg_life(region=u"江南", taste=u"清淡", avoid=u"香菜")),
        (u"仙侠（物质口径唐宋）", [u"user"], base, 1.0, base + timedelta(minutes=15),
         ROLE_ALING, WORLD_XIANXIA, cfg_life()),
        (u"没有时间戳", [u"system", u"system"], base, 1.0, base,
         ROLE_ALING, WORLD_URBAN, cfg_life()),
        (u"关掉生活层", [u"user"], base, 1.0, base, ROLE_ALING, WORLD_URBAN, cfg_life(enabled=False)),
        (u"刚天亮还没到饭点", [u"user"], datetime(2026, 5, 4, 4, 30, 0), 1.0,
         datetime(2026, 5, 4, 4, 40, 0), ROLE_ALING, WORLD_URBAN, cfg_life()),
        (u"720× 一天之内", [u"user"], base, 720.0, base + timedelta(minutes=2),
         ROLE_ALING, WORLD_MING, cfg_life()),
    ]
    cases = []
    for label, roles, t0, scale, now, role, world, cfg in raw:
        stamps = [t0 + timedelta(minutes=7 * i) for i in range(len(roles))]
        chain = [{"role": r, "timestamp": s.isoformat()} for r, s in zip(roles, stamps)]
        expect = L.describe(chain, scale=scale, role=role, world=world, cfg=cfg, now=now)
        cases.append({
            "label": label,
            "roles": list(roles),
            "stamps": [s.isoformat() for s in stamps],
            "scale": float(scale),
            "nowIso": now.isoformat(),
            "roleJson": jdump(role),
            "worldJson": jdump(world) if world else "",
            "cfgJson": jdump(cfg),
            "expect": expect,
        })
    return cases


def _map_snapshot(mp):
    places = sorted(((n, float(m.get("minutes") or 0), bool(m.get("room")))
                     for n, m in (mp.get("places") or {}).items()), key=lambda x: x[0])
    rooms = list(mp.get("rooms") or [])
    transport = sorted(((k, float(v)) for k, v in (mp.get("transport") or {}).items()),
                       key=lambda kv: (kv[1], kv[0]))
    links = sorted(((k, float(v)) for k, v in (mp.get("links") or {}).items()), key=lambda kv: kv[0])
    return {"home": mp.get("home"), "places": places, "rooms": rooms,
            "transport": transport, "links": links}


def space_map_cases():
    raw = [
        (u"现代默认", None, None, None),
        (u"唐宋", WORLD_MING, None, None),
        (u"仙侠地图", WORLD_XIANXIA, None, None),
        (u"末世地图", WORLD_WASTE, None, None),
        (u"世界卡自带地图", WORLD_CUSTOM_SPACE, None, None),
        (u"世界卡 merge", WORLD_MERGE_SPACE, None, None),
        (u"地图直接写 dict", WORLD_DICT_SPACE, None, None),
        (u"角色卡加地点", WORLD_URBAN, ROLE_SHEN, None),
        (u"角色卡定年代", None, ROLE_1950, None),
        (u"显式指定年代", None, None, u"明清"),
    ]
    cases = []
    for label, world, role, era in raw:
        mp = S.map_for(role, world, S.load_config(), era)
        snap = _map_snapshot(mp)
        cases.append({
            "label": label,
            "worldJson": jdump(world) if world else "",
            "roleJson": jdump(role) if role else "",
            "era": era or "",
            "home": snap["home"],
            "places": snap["places"],
            "rooms": snap["rooms"],
            "transport": snap["transport"],
            "links": snap["links"],
        })
    return cases


def space_travel_cases():
    cfgs = S.load_config()
    raw = [
        (u"家 → 便利店（走路）", None, u"家", u"便利店", u""),
        (u"家 → 便利店（骑车）", None, u"家", u"便利店", u"骑车"),
        (u"两个非家地点（相加）", None, u"便利店", u"超市", u""),
        (u"学校 → 医院（相加）", None, u"学校", u"医院", u""),
        (u"原地不动", None, u"超市", u"超市", u""),
        (u"地图上没有的名字", None, u"家", u"月球", u""),
        (u"links 精确覆盖", WORLD_CUSTOM_SPACE, u"教学楼", u"图书馆", u""),
        (u"links 反向也算", WORLD_CUSTOM_SPACE, u"图书馆", u"教学楼", u"骑车"),
        (u"宿舍 → 便利店", WORLD_CUSTOM_SPACE, u"宿舍", u"便利店", u""),
        (u"唐宋没有地铁（退回通用系数）", WORLD_MING, u"自家宅院", u"茶肆", u"地铁"),
        (u"唐宋坐轿子", WORLD_MING, u"自家宅院", u"码头", u"轿子"),
    ]
    cases = []
    for label, world, a, b, by in raw:
        mp = S.map_for(None, world, cfgs)
        cases.append({
            "label": label,
            "worldJson": jdump(world) if world else "",
            "era": u"",
            "a": a, "b": b, "by": by,
            "expect": float(S.travel_minutes(mp, a, b, by or None)),
        })
    return cases


def space_reach_cases():
    mp_default = S.map_for(None, None, S.load_config())
    mp_campus = S.map_for(None, WORLD_CUSTOM_SPACE, S.load_config())
    raw = [
        (u"现代 20 分钟", mp_default, u"家", 20.0, 4, u"", False, u""),
        (u"现代 5 分钟（哪都去不了）", mp_default, u"家", 5.0, 4, u"", False, u""),
        (u"现代 600 分钟（含远方）", mp_default, u"家", 600.0, 20, u"", False, u""),
        (u"骑车更快", mp_default, u"家", 40.0, 6, u"骑车", False, u""),
        (u"算上屋里", mp_campus, u"宿舍", 1.0, 6, u"", True, jdump(WORLD_CUSTOM_SPACE)),
        (u"不算屋里", mp_campus, u"宿舍", 1.0, 6, u"", False, jdump(WORLD_CUSTOM_SPACE)),
        (u"不限条数", mp_default, u"家", 30.0, 0, u"", False, u""),
    ]
    cases = []
    for label, mp, frm, minutes, limit, by, rooms, world in raw:
        got = S.reachable(mp, frm, minutes, limit=(limit or None), by=(by or None), include_rooms=rooms)
        cases.append({
            "label": label,
            "worldJson": world,
            "era": u"",
            "from": frm,
            "minutes": float(minutes),
            "limit": int(limit),
            "by": by,
            "includeRooms": bool(rooms),
            "expect": [(n, float(m)) for n, m in got],
        })
    return cases


def space_open_cases():
    mp_campus = S.map_for(None, WORLD_CUSTOM_SPACE, S.load_config())
    places = mp_campus["places"]
    raw = [
        (u"食堂 05:59 没开", u"食堂", 5, 59),
        (u"食堂 06:00 开了", u"食堂", 6, 0),
        (u"食堂 19:59 还开", u"食堂", 19, 59),
        (u"食堂 20:00 关门", u"食堂", 20, 0),
        (u"便利店 23:00 开（跨天）", u"便利店", 23, 0),
        (u"便利店 01:30 还开（跨天）", u"便利店", 1, 30),
        (u"便利店 03:00 关门（跨天）", u"便利店", 3, 0),
        (u"图书馆没写 open 视为一直开", u"教学楼", 3, 0),
    ]
    cases = []
    for label, place, hh, mm in raw:
        ok, why = S.open_now(places.get(place), datetime(2026, 5, 4, hh, mm))
        cases.append({
            "label": label,
            "worldJson": jdump(WORLD_CUSTOM_SPACE),
            "era": u"",
            "place": place,
            "hour": int(hh),
            "minute": int(mm),
            "ok": bool(ok),
            "why": why,
        })
    return cases


def tag_cases():
    raw = [
        u"她推门进来。[loc:学校|骑车] 又坐下。",
        u"[ploc:家/厨房] 锅里的水开了。",
        u"先到 [loc: 图书馆 ｜ 地铁 ] 再说",
        u"[位置:菜市场][地点:超市]",
        u"[LOC:学校]",
        u"没有标签的一段话。",
        u"[loc:朝阳, 北京]",
        u"[loc:家/厨房|走路] 和 [ploc:公司|打车]",
        u"[loc:便利店|]",
        u"[loc:|骑车]",
        u"[loc:A|B|C]",
        u"",
    ]
    cases = []
    for text in raw:
        moves = S.parse_move(text)
        cases.append({
            "label": text[:12] if text else u"空串",
            "text": text,
            "moves": [u"%s|%s|%s" % (u"ploc" if p else u"loc", place, by) for p, place, by in moves],
            "stripped": S.strip_move_tags(text),
        })
    return cases


def space_inject_cases():
    """(label, 角色名, worldJson, now, 链上角色, 世界流速, cfgJson, stateJson)

    每条都在临时目录里从**同样的**状态文件出发算一遍期望值 —— 状态文件就是
    电脑端 `space/<角色>.json` 的格式，手机端要能读同一份。
    """
    base = datetime(2026, 5, 4, 12, 0, 0)
    campus_world = jdump(WORLD_CUSTOM_SPACE)
    ming_world = jdump(WORLD_MING)
    return [
        (u"从没记过位置", u"阿绫", u"", base, [u"user"], 1.0, jdump(cfg_space()), u""),
        (u"在学校，骑车来的", u"阿绫", campus_world, base, [u"user", u"assistant"], 1.0,
         jdump(cfg_space()),
         jdump({u"place": u"教学楼", u"since": (base - timedelta(minutes=20)).isoformat(),
                u"by": u"骑车", u"scale": 1.0})),
        (u"在家（该报屋里）", u"阿绫", campus_world, base, [u"user"], 1.0, jdump(cfg_space()),
         jdump({u"place": u"宿舍", u"since": (base - timedelta(minutes=70)).isoformat(),
                u"by": u"走路", u"scale": 1.0})),
        (u"地图外的地方", u"阿绫", u"", base, [u"user"], 1.0, jdump(cfg_space()),
         jdump({u"place": u"月球基地", u"since": (base - timedelta(minutes=15)).isoformat(),
                u"offmap": u"月球基地", u"by": u"走路"})),
        (u"穿帮一次（要提醒）", u"阿绫", u"", base, [u"user"], 1.0, jdump(cfg_space()),
         jdump({u"place": u"火车站", u"since": (base - timedelta(minutes=1)).isoformat(),
                u"prev": u"家", u"by": u"走路",
                u"violation": {u"from": u"家", u"to": u"火车站", u"need": 40.0, u"have": 1.0,
                               u"at": base.isoformat(),
                               u"why": u"从家到火车站要 40 分钟，这段时间只过了 1 分钟"}})),
        (u"穿帮已提醒两次（不再念）", u"阿绫", u"", base, [u"user"], 1.0, jdump(cfg_space()),
         jdump({u"place": u"火车站", u"since": (base - timedelta(minutes=1)).isoformat(),
                u"by": u"走路",
                u"violation": {u"from": u"家", u"to": u"火车站", u"need": 40.0, u"have": 1.0,
                               u"at": base.isoformat(), u"why": u"来不及", u"warned": 2}})),
        (u"玩家也在地图上", u"阿绫", campus_world, base, [u"user"], 1.0, jdump(cfg_space()),
         jdump({u"place": u"教学楼", u"since": (base - timedelta(minutes=30)).isoformat(),
                u"by": u"走路", u"player_place": u"便利店",
                u"player_since": (base - timedelta(minutes=12)).isoformat()})),
        (u"营业时间对不上（凌晨的食堂）", u"阿绫", campus_world, base.replace(hour=3, minute=10),
         [u"user"], 1.0, jdump(cfg_space()),
         jdump({u"place": u"食堂", u"since": base.replace(hour=3, minute=10).isoformat(),
                u"by": u"走路"})),
        (u"明清地图的茶肆（没写营业时间就不提醒）", u"阿绫", ming_world, base.replace(hour=3, minute=10),
         [u"user"], 1.0, jdump(cfg_space()),
         jdump({u"place": u"茶肆", u"since": base.replace(hour=3, minute=10).isoformat(),
                u"by": u"走路"})),
        (u"关掉空间层", u"阿绫", u"", base, [u"user"], 1.0, jdump(cfg_space(enabled=False)), u""),
        (u"预算很小要截断", u"阿绫", campus_world, base, [u"user"], 1.0,
         jdump(cfg_space(max_chars=100)), u""),
        (u"720× 时间", u"阿绫", u"", base, [u"user"], 720.0, jdump(cfg_space()),
         jdump({u"place": u"家", u"since": base.isoformat(), u"by": u"走路"})),
    ]


def cfg_space(**kw):
    d = dict(S.DEFAULTS)
    d.update(kw)
    return d


def gen_goldens_with_tmpdir():
    """空间层的注入/移动会写状态文件 —— 全部在临时目录里跑，别碰仓库里的 space/。"""
    tmp = tempfile.mkdtemp(prefix="dick_parity_")
    real_base = app_paths.get_base_dir
    old_cache = S._Cfg._cache
    app_paths.get_base_dir = lambda: tmp
    S._Cfg._cache = None
    try:
        return _gen_goldens()
    finally:
        app_paths.get_base_dir = real_base
        S._Cfg._cache = old_cache
        shutil.rmtree(tmp, ignore_errors=True)


def _gen_goldens():
    o = []
    o.append(HEADER)
    o.append(u"package com.dick.parity\n")
    o.append(u"/**")
    o.append(u" * 对拍基准：这些期望值是**电脑端算出来的**，手机端必须算出一样的。")
    o.append(u" *")
    o.append(u" * 菜单是确定性抽样（种子 = 角色｜世界第几天｜哪一餐），所以两端算出同一份菜单")
    o.append(u" * 是可以验证的；注入文本更是逐字比对 —— 差一个字都算漂。")
    o.append(u" *")
    o.append(u" * 组装格式（两端必须一致）：")
    o.append(u" *   菜单一行 = 「餐名|主食|菜1,菜2|喝的|做法1,做法2」")
    o.append(u" *   位置标签 = 「loc|地名|交通」或「ploc|地名|交通」")
    o.append(u" */")
    o.append(u"object Goldens {\n")

    o.append(u"    // ---------------- 生活层 ----------------")
    o.append(u"    data class EraCase(val label: String, val worldJson: String, val roleJson: String,")
    o.append(u"                     val lifeEra: String, val csEra: String, val csKind: String)")
    o.append(u"    data class MenuCase(val label: String, val roleJson: String, val worldJson: String,")
    o.append(u"                     val cfgJson: String, val lifeDay: Int, val meals: List<String>,")
    o.append(u"                     val dishes: List<String>)")
    o.append(u"    data class LifeInjectCase(val label: String, val roles: List<String>,")
    o.append(u"                     val stamps: List<String>, val scale: Double, val nowIso: String,")
    o.append(u"                     val roleJson: String, val worldJson: String, val cfgJson: String,")
    o.append(u"                     val expect: String)\n")

    o.append(u"    val eraCases: List<EraCase> = listOf(")
    for c in life_era_cases():
        o.append(u"        EraCase(label = %s, worldJson = %s, roleJson = %s, lifeEra = %s, csEra = %s,"
                 u" csKind = %s),"
                 % (kstr(c["label"]), kstr(c["worldJson"]), kstr(c["roleJson"]), kstr(c["lifeEra"]),
                    kstr(c["csEra"]), kstr(c["csKind"])))
    o.append(u"    )\n")

    o.append(u"    val menuCases: List<MenuCase> = listOf(")
    for c in life_menu_cases():
        o.append(u"        MenuCase(label = %s, roleJson = %s, worldJson = %s, cfgJson = %s,"
                 u" lifeDay = %s," % (kstr(c["label"]), kstr(c["roleJson"]), kstr(c["worldJson"]),
                                      kstr(c["cfgJson"]), kint(c["lifeDay"])))
        o.append(u"                 meals = %s," % kstrlist(c["meals"]))
        o.append(u"                 dishes = %s)," % kstrlist(c["dishes"]))
    o.append(u"    )\n")

    o.append(u"    val lifeInjectCases: List<LifeInjectCase> = listOf(")
    for c in life_inject_cases():
        o.append(u"        LifeInjectCase(label = %s," % kstr(c["label"]))
        o.append(u"                       roles = %s," % kstrlist(c["roles"]))
        o.append(u"                       stamps = %s," % kstrlist(c["stamps"]))
        o.append(u"                       scale = %s, nowIso = %s," % (kd(c["scale"]), kstr(c["nowIso"])))
        o.append(u"                       roleJson = %s, worldJson = %s, cfgJson = %s,"
                 % (kstr(c["roleJson"]), kstr(c["worldJson"]), kstr(c["cfgJson"])))
        o.append(u"                       expect = %s)," % kstr(c["expect"]))
    o.append(u"    )\n")

    o.append(u"    val lifeDescribeCases: List<LifeInjectCase> = listOf(")
    for c in life_describe_cases():
        o.append(u"        LifeInjectCase(label = %s," % kstr(c["label"]))
        o.append(u"                       roles = %s," % kstrlist(c["roles"]))
        o.append(u"                       stamps = %s," % kstrlist(c["stamps"]))
        o.append(u"                       scale = %s, nowIso = %s," % (kd(c["scale"]), kstr(c["nowIso"])))
        o.append(u"                       roleJson = %s, worldJson = %s, cfgJson = %s,"
                 % (kstr(c["roleJson"]), kstr(c["worldJson"]), kstr(c["cfgJson"])))
        o.append(u"                       expect = %s)," % kstr(c["expect"]))
    o.append(u"    )\n")

    o.append(u"    // ---------------- 空间层 ----------------")
    o.append(u"    data class MapCase(val label: String, val worldJson: String, val roleJson: String,")
    o.append(u"                     val era: String, val home: String,")
    o.append(u"                     val places: List<Triple<String, Double, Boolean>>,")
    o.append(u"                     val rooms: List<String>, val transport: List<Pair<String, Double>>,")
    o.append(u"                     val links: List<Pair<String, Double>>)")
    o.append(u"    data class TravelCase(val label: String, val worldJson: String, val era: String,")
    o.append(u"                     val a: String, val b: String, val by: String, val expect: Double)")
    o.append(u"    data class ReachCase(val label: String, val worldJson: String, val era: String,")
    o.append(u"                     val from: String, val minutes: Double, val limit: Int, val by: String,")
    o.append(u"                     val includeRooms: Boolean, val expect: List<Pair<String, Double>>)")
    o.append(u"    data class OpenCase(val label: String, val worldJson: String, val era: String,")
    o.append(u"                     val place: String, val hour: Int, val minute: Int,")
    o.append(u"                     val ok: Boolean, val why: String)")
    o.append(u"    data class TagCase(val label: String, val text: String, val moves: List<String>,")
    o.append(u"                     val stripped: String)")
    o.append(u"    data class SpaceInjectCase(val label: String, val roleName: String, val worldJson: String,")
    o.append(u"                     val stateJson: String, val roles: List<String>, val stamps: List<String>,")
    o.append(u"                     val scale: Double, val nowIso: String, val cfgJson: String,")
    o.append(u"                     val expect: String)\n")

    o.append(u"    val mapCases: List<MapCase> = listOf(")
    for c in space_map_cases():
        o.append(u"        MapCase(label = %s, worldJson = %s, roleJson = %s, era = %s, home = %s,"
                 % (kstr(c["label"]), kstr(c["worldJson"]), kstr(c["roleJson"]), kstr(c["era"]),
                    kstr(c["home"])))
        o.append(u"                places = %s," % kplace_triples(c["places"]))
        o.append(u"                rooms = %s, transport = %s, links = %s),"
                 % (kstrlist(c["rooms"]), kdblpairs(c["transport"]), kdblpairs(c["links"])))
    o.append(u"    )\n")

    o.append(u"    val travelCases: List<TravelCase> = listOf(")
    for c in space_travel_cases():
        o.append(u"        TravelCase(label = %s, worldJson = %s, era = %s, a = %s, b = %s, by = %s,"
                 u" expect = %s),"
                 % (kstr(c["label"]), kstr(c["worldJson"]), kstr(c["era"]), kstr(c["a"]), kstr(c["b"]),
                    kstr(c["by"]), kd(c["expect"])))
    o.append(u"    )\n")

    o.append(u"    val reachCases: List<ReachCase> = listOf(")
    for c in space_reach_cases():
        o.append(u"        ReachCase(label = %s, worldJson = %s, era = %s, from = %s, minutes = %s,"
                 u" limit = %s, by = %s, includeRooms = %s,"
                 % (kstr(c["label"]), kstr(c["worldJson"]), kstr(c["era"]), kstr(c["from"]),
                    kd(c["minutes"]), kint(c["limit"]), kstr(c["by"]), kbool(c["includeRooms"])))
        o.append(u"                 expect = %s)," % kdblpairs(c["expect"]))
    o.append(u"    )\n")

    o.append(u"    val openCases: List<OpenCase> = listOf(")
    for c in space_open_cases():
        o.append(u"        OpenCase(label = %s, worldJson = %s, era = %s, place = %s, hour = %s,"
                 u" minute = %s, ok = %s, why = %s),"
                 % (kstr(c["label"]), kstr(c["worldJson"]), kstr(c["era"]), kstr(c["place"]),
                    kint(c["hour"]), kint(c["minute"]), kbool(c["ok"]), kstr(c["why"])))
    o.append(u"    )\n")

    o.append(u"    val tagCases: List<TagCase> = listOf(")
    for c in tag_cases():
        o.append(u"        TagCase(label = %s, text = %s, moves = %s, stripped = %s),"
                 % (kstr(c["label"]), kstr(c["text"]), kstrlist(c["moves"]), kstr(c["stripped"])))
    o.append(u"    )\n")

    o.append(u"    val spaceInjectCases: List<SpaceInjectCase> = listOf(")
    for (label, role_name, world, now_dt, roles, scale, cfg, state) in space_inject_cases():
        cfg_d = json.loads(cfg)
        stamps = [now_dt - timedelta(minutes=7 * (len(roles) - 1 - i)) for i in range(len(roles))]
        # 把状态写进临时目录，再按电脑端的算法算一遍期望值
        sdir = os.path.join(app_paths.get_base_dir(), cfg_d.get("state_dir") or "space")
        if not os.path.isdir(sdir):
            os.makedirs(sdir)
        sp = os.path.join(sdir, S._safe(role_name) + ".json")
        if state:
            with io.open(sp, "w", encoding="utf-8") as f:
                f.write(state)
        elif os.path.isfile(sp):
            os.remove(sp)
        chain = [{"role": r, "timestamp": s.isoformat()} for r, s in zip(roles, stamps)]
        # 世界卡**必须传进去**：不传的话算出来的是默认（现代）地图的期望值，
        # 带 worldJson 的用例就白挂了 —— 手机端读的是世界卡里的地图，两边会对不上。
        world_obj = json.loads(world) if world else None
        expect = S.injection_text(None, world_obj, scale=scale, cfg=cfg_d, now=now_dt,
                                  name=role_name, chain=chain)
        o.append(u"        SpaceInjectCase(label = %s, roleName = %s," % (kstr(label), kstr(role_name)))
        o.append(u"                       worldJson = %s," % kstr(world))
        o.append(u"                       stateJson = %s," % kstr(state if state else u""))
        o.append(u"                       roles = %s, stamps = %s,"
                 % (kstrlist(roles), kstrlist([s.isoformat() for s in stamps])))
        o.append(u"                       scale = %s, nowIso = %s," % (kd(scale), kstr(now_dt.isoformat())))
        o.append(u"                       cfgJson = %s, expect = %s)," % (kstr(cfg), kstr(expect)))
    o.append(u"    )")
    o.append(u"}\n")
    return u"\n".join(o)


# ============================================================
#  四、写盘 / 检查
# ============================================================
def _mark(path, text):
    """生成物也带上仓库水印（`tests/test_seiki_mark.py` 会要求）。

    水印是零宽的、插入位置由 `seiki_mark` 决定 —— 所以比较"是不是最新"时先把它剥掉，
    否则每跑一次 `--check` 都会判过期（生成的是干净文本，磁盘那份带水印）。
    """
    try:
        import seiki_mark as SM
        styles = SM.COMMENT.get(os.path.splitext(path)[1].lower())
        if styles:
            text, _st, _why = SM.embed(text, None, styles, fmt="native")
    except Exception:
        pass
    return text


ZW = re.compile(u"[\u200b-\u200f\u2060\ufeff\u00ad]+")


def _clean(text):
    """剥掉水印（可见的 `<seiki>` 前缀 + 零宽负载）后再比内容。"""
    return ZW.sub(u"", text.replace(u"<seiki>", u""))


def write_or_check(path, text, check):
    old = None
    if os.path.isfile(path):
        with io.open(path, "r", encoding="utf-8") as f:
            old = f.read()
    if old is not None and _clean(old) == _clean(text):
        print(u"[ok] %s 已是最新" % os.path.relpath(path, ROOT))
        return True
    if check:
        print(u"[过期] %s 和 Python 端的表/逻辑不一致 —— 跑 python tools/gen_parity.py 重新生成"
              % os.path.relpath(path, ROOT))
        return False
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(_mark(path, text))
    print(u"[写] %s（%d 字符）" % (os.path.relpath(path, ROOT), len(text)))
    return True


def sync_assets_packs(check):
    """把 world_packs/*.json 同步进 APK 的 assets（逐字节相同）。"""
    ok = True
    names = sorted(f for f in os.listdir(PACKS_SRC) if f.endswith(".json")) \
        if os.path.isdir(PACKS_SRC) else []
    if not names:
        print(u"[warn] world_packs/ 里没有卡可同步")
        return True
    if not check and not os.path.isdir(ASSETS_PACKS):
        os.makedirs(ASSETS_PACKS)
    stale = []
    for fn in names:
        src = os.path.join(PACKS_SRC, fn)
        dst = os.path.join(ASSETS_PACKS, fn)
        with io.open(src, "rb") as f:
            want = f.read()
        have = None
        if os.path.isfile(dst):
            with io.open(dst, "rb") as f:
                have = f.read()
        if have == want:
            continue
        if check:
            stale.append(fn)
            continue
        with io.open(dst, "wb") as f:
            f.write(want)
        print(u"[写] DICK-Android\\app\\src\\main\\assets\\world_packs\\%s" % fn)
    # assets 里多出来的（源里已删）也算过期
    extra = []
    if os.path.isdir(ASSETS_PACKS):
        for fn in sorted(os.listdir(ASSETS_PACKS)):
            if fn.endswith(".json") and fn not in names:
                extra.append(fn)
                if not check:
                    os.remove(os.path.join(ASSETS_PACKS, fn))
    if check and (stale or extra):
        print(u"[过期] 世界卡库 assets 与 world_packs/ 不一致：缺/旧 %s 多余 %s"
              % (stale, extra))
        ok = False
    if ok:
        print(u"[ok] 世界卡库 assets 已是最新（%d 张）" % len(names))
    return ok


def main(argv):
    check = "--check" in argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ok1 = write_or_check(OUT_TABLES, gen_tables(), check)
    ok2 = write_or_check(OUT_GOLDENS, gen_goldens_with_tmpdir(), check)
    ok3 = sync_assets_packs(check)
    if check and not (ok1 and ok2 and ok3):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
