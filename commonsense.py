# -*- coding: utf-8 -*-
"""commonsense.py —— 常识库：年代 → 地点 / 交通 / 屋里格局

为什么要有它
------------
空间层（`space_core`）的内置地图是**现代都市**口径：便利店、地铁站、咖啡馆。
把它套到"大明万历年间"或"仙侠宗门"上，就会出现"她坐地铁去码头"这种穿帮 ——
换汤不换药的另一种瞬移。生活层（`life_core`）也有同一个问题（厨具/食材），
它已经有一张年代表 + 一张"从世界卡认年代"的关键词表。

所以这个模块只做一件事：**把两张表对齐到同一年代口径**，并给空间层提供
「那个年代有哪些地方、怎么走、屋里长什么样」。年代 key 与 `life_core.ERAS` 完全一致
（`tests/test_space_core.py` 会断言两张表不许漂移）。

约定
----
  · places：从"家"出发的单程分钟数（与 space_core 的轮辐模型一致）
  · transports：耗时系数，乘在分钟数上（越小越快）
  · rooms：家里/住处内部的空间，从家门口算 **1 分钟以内**（同屋走动不构成"赶路"）
  · far：那个年代的"出远门"（跨城/跨州），单独标出来，免得和邻里地点混在一起
"""
import re

# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  一、年代常识表（key 必须与 life_core.ERAS 的 key 一致）
# ============================================================
ERAS = {
    "史前": {
        "places": [("洞窟", 0), ("营地", 2), ("溪边", 5), ("林子", 12), ("石场", 20),
                   ("别的部落", 90)],
        "transports": {"步行": 1.0, "小跑": 0.6, "独木舟": 0.5},
        "rooms": ["洞窟内", "火塘边", "睡铺"],
        "notes": "没有路，只有兽径；「出远门」= 走上一天",
    },
    "新石器": {
        "places": [("自家土屋", 0), ("村口", 3), ("水井", 5), ("田地", 15), ("集市", 25),
                   ("邻村", 60)],
        "transports": {"步行": 1.0, "小跑": 0.65, "牛车": 0.5, "独木舟": 0.5},
        "rooms": ["堂屋", "灶间", "睡房", "院子", "柴棚"],
        "notes": "村落尺度；出远门靠走或牛车",
    },
    "先秦汉": {
        "places": [("自家宅院", 0), ("里巷口", 3), ("水井", 5), ("市集", 20), ("官署", 30),
                   ("祠庙", 25), ("渡口", 35), ("田埂", 40), ("邻县", 240)],
        "transports": {"步行": 1.0, "快走": 0.75, "牛车": 0.5, "马车": 0.35, "骑马": 0.25,
                       "渡船": 0.4},
        "rooms": ["正房", "厢房", "灶房", "院子", "柴房", "马厩"],
        "notes": "里坊制，夜里可能宵禁；远行要带干粮",
    },
    "唐宋": {
        "places": [("自家宅院", 0), ("巷口", 3), ("茶肆", 10), ("坊市", 20), ("衙门", 30),
                   ("寺庙", 30), ("书院", 35), ("码头", 40), ("瓦舍", 35), ("州城", 300)],
        "transports": {"步行": 1.0, "快走": 0.75, "轿子": 0.45, "马车": 0.35, "骑马": 0.25,
                       "渡船": 0.4},
        "rooms": ["正房", "厢房", "灶房", "堂屋", "院子", "书房", "柴房"],
        "notes": "坊市有营业时辰；文人常去茶肆书院，夜里坊门会关",
    },
    "明清": {
        "places": [("自家宅院", 0), ("巷口", 3), ("茶馆", 12), ("集市", 20), ("县衙", 30),
                   ("当铺", 25), ("庙会", 35), ("码头", 40), ("书院", 35), ("府城", 360)],
        "transports": {"步行": 1.0, "快走": 0.75, "轿子": 0.45, "马车": 0.35, "骑马": 0.25,
                       "渡船": 0.4},
        "rooms": ["正房", "厢房", "灶房", "堂屋", "院子", "书房", "柴房", "绣楼"],
        "notes": "辣椒番茄明末才传入 —— 与 life_core 的年代食材表同源",
    },
    "民国": {
        "places": [("自家住处", 0), ("弄堂口", 2), ("老虎灶", 6), ("街市", 15), ("警察局", 30),
                   ("报馆", 35), ("电影院", 30), ("码头", 45), ("教堂", 30), ("省城", 300)],
        "transports": {"步行": 1.0, "黄包车": 0.3, "电车": 0.2, "渡船": 0.4, "汽车": 0.25,
                       "火车": 0.15},
        "rooms": ["前厅", "卧房", "灶披间", "天井", "亭子间"],
        "notes": "黄包车与电车并存；报纸、电影院开始进日常",
    },
    "1950s": {
        "places": [("自家", 0), ("院门口", 2), ("供销社", 12), ("邮电局", 25), ("粮站", 20),
                   ("卫生所", 25), ("大食堂", 8), ("公社", 40), ("县城", 200)],
        "transports": {"步行": 1.0, "自行车": 0.35, "公共汽车": 0.4, "火车": 0.15},
        "rooms": ["里屋", "外屋", "厨房", "院子", "储藏间"],
        "notes": "票证时代，买东西要票；大食堂是集体吃饭的地方",
    },
    "1980s": {
        "places": [("自家", 0), ("楼下", 2), ("国营商店", 12), ("菜场", 10), ("邮电局", 20),
                   ("电影院", 25), ("录像厅", 25), ("厂区", 35), ("火车站", 45)],
        "transports": {"步行": 1.0, "自行车": 0.35, "公交": 0.5, "火车": 0.15},
        "rooms": ["里屋", "外屋", "厨房", "阳台", "储藏间"],
        "notes": "自行车是主力；录像厅、厂区是这一代的社交场",
    },
    "2000s": {
        "places": [("自家", 0), ("楼下", 2), ("便利店", 6), ("网吧", 15), ("书店", 20),
                   ("公交站", 8), ("公园", 15), ("医院", 20), ("学校", 25), ("火车站", 40)],
        "transports": {"走路": 1.0, "骑车": 0.4, "公交": 0.5, "出租车": 0.35, "火车": 0.15},
        "rooms": ["卧室", "客厅", "厨房", "卫生间", "阳台"],
        "notes": "网吧与公交卡的时代",
    },
    "现代": {
        "places": [("家", 0), ("楼下", 2), ("小区门口", 3), ("便利店", 6), ("公交站", 8),
                   ("菜市场", 10), ("超市", 12), ("公园", 15), ("餐厅", 15), ("咖啡馆", 18),
                   ("医院", 20), ("学校", 25), ("朋友家", 25), ("电影院", 30), ("公司", 35),
                   ("火车站", 40), ("邻近城市", 180), ("远方（省外）", 600)],
        "transports": {"走路": 1.0, "步行": 1.0, "骑车": 0.4, "公交": 0.5, "地铁": 0.45,
                       "打车": 0.35, "开车": 0.3, "高铁": 0.06, "飞机": 0.05},
        "rooms": ["卧室", "客厅", "厨房", "卫生间", "阳台", "书房", "玄关"],
        "notes": "默认口径（地铁/打车/外卖）",
    },
    # 架空年代：不指年份，指"设定类型"，由世界卡显式指定
    "仙侠": {
        "places": [("洞府", 0), ("山门", 15), ("练功场", 10), ("膳堂", 8), ("藏经阁", 25),
                   ("坊市", 60), ("秘境入口", 180), ("宗门大殿", 30)],
        "transports": {"步行": 1.0, "轻功": 0.4, "御剑": 0.08, "传送阵": 0.05},
        "rooms": ["静室", "丹房", "卧房", "院子", "灵田"],
        "notes": "御剑/传送阵让「远」变近 —— 但要有修为设定撑住",
    },
    "末世": {
        "places": [("据点", 0), ("楼下废墟", 5), ("补给点", 30), ("加油站", 45),
                   ("避难所", 120), ("辐射区", 200), ("别的据点", 300)],
        "transports": {"步行": 1.0, "小跑": 0.7, "自行车": 0.4, "改装车": 0.25},
        "rooms": ["睡铺", "库房", "灶间", "瞭望位"],
        "notes": "路断了、油要省；弹药与净水是硬通货",
    },
}

DEFAULT_ERA = "现代"


def era_keys():
    return list(ERAS)


def get(era, key, default=None):
    e = ERAS.get(str(era or "").strip()) or {}
    return e.get(key, default)


def places(era):
    """[(名字, 从家多少分钟), ...]"""
    got = get(era, "places")
    if got:
        return [(str(n), float(m)) for n, m in got]
    return [(str(n), float(m)) for n, m in ERAS[DEFAULT_ERA]["places"]]


def transports(era):
    got = get(era, "transports") or {}
    return dict(got) if got else dict(ERAS[DEFAULT_ERA]["transports"])


def rooms(era):
    got = get(era, "rooms") or []
    return list(got) if got else list(ERAS[DEFAULT_ERA]["rooms"])


def notes(era):
    return str(get(era, "notes") or "")


# ============================================================
#  二、认年代：关键词表只有一份（在 life_core 里），这里只做转交
# ============================================================
#  世界卡里可以显式写类型（params.era_kind），例如 era=明清 但 kind=仙侠：
#  年代决定食材厨具，类型决定地图与交通 —— 两者不冲突（"明朝背景的仙侠"是常见需求）。
KINDS = ("仙侠", "末世")


def detect_era(world=None, role=None):
    """优先：卡里显式写 → 世界卡关键词（复用 life_core 的表）→ 现代"""
    for src in (role, world):
        if isinstance(src, dict):
            adv = src.get("advanced") if isinstance(src.get("advanced"), dict) else {}
            life = adv.get("life") if isinstance(adv.get("life"), dict) else {}
            for probe in (life.get("era"), src.get("era"),
                          (src.get("params") or {}).get("era") if isinstance(src.get("params"), dict) else None):
                if probe and str(probe) in ERAS:
                    return str(probe)
    try:
        import life_core as _life
        key = _life.detect_era(world)
        if key in ERAS:
            return key
    except Exception as e:
        print("[commonsense] 认年代失败（退回现代）: %s" % e)
    return DEFAULT_ERA


def detect_kind(world=None, role=None):
    """设定类型（仙侠/末世…）：卡里显式写 kind，或世界卡里出现关键词"""
    for src in (role, world):
        if isinstance(src, dict):
            adv = src.get("advanced") if isinstance(src.get("advanced"), dict) else {}
            life = adv.get("life") if isinstance(adv.get("life"), dict) else {}
            for probe in (life.get("kind"), src.get("kind"),
                          (src.get("params") or {}).get("era_kind") if isinstance(src.get("params"), dict) else None):
                if probe and str(probe) in KINDS:
                    return str(probe)
    text = ""
    if isinstance(world, dict):
        for k in ("name", "description", "rules"):
            if isinstance(world.get(k), str):
                text += world[k]
    for kind, hints in (("仙侠", ("仙侠", "修真", "御剑", "宗门", "灵气", "金丹")),
                        ("末世", ("末世", "废土", "丧尸", "辐射", "末日"))):
        for h in hints:
            if h in text:
                return kind
    return ""


def effective_era(world=None, role=None):
    """空间层该用哪张地图：类型（仙侠/末世）优先于年代 —— 它们的地图差别更大"""
    kind = detect_kind(world, role)
    if kind:
        return kind
    return detect_era(world, role)
