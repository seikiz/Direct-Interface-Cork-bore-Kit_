# -*- coding: utf-8 -*-
"""life_core.py —— 生活层（吃饭）：世界时钟 + 厨具历史库 + 食材/做法库

为什么做
--------
角色扮演里"AI 不像活人"的一大块是：**她没有日子**。今天代码里跟生活有关的全部内容，
是 `DICK_core.py` 里那 5 条祈使句（"食物/天气/活动不固定""聊过的饭要像真记得"）——
没有底料、没有时钟、没有记录，所以模型只能随机发挥：既单薄，又前后矛盾
（上次说海鲜过敏，下次端上来一盘虾）。

这个模块补三件事：

  ① **世界时钟**：把"那边现在几点"算出来（起点 = 系统时间，见下）
  ② **厨具历史库**：哪个年代有什么锅碗瓢盆 —— 它是**约束**，防止中世纪角色叮一下微波炉
  ③ **食材/做法库**：按 年代 × 地域 × 口味 × 忌口 抽样出一日三餐

世界时钟：系统时间就是 1× 起源
------------------------------
节点的 `timestamp` 本来就是系统本地时间（`DICK_core.py:150`），记忆衰老
（`salience.py`）也一直是"现实时间戳 × 倍率"，所以"系统时间 = 1× 起源"不是新发明 ——
缺的只是"那边现在几点"这个绝对标签：

    世界时刻 = 链首节点时刻 + Σ(链上相邻节点的现实间隔 × 倍率) + (现在 − 末节点时刻) × 倍率

两个必须写清的推论（不写清一定穿帮）：

  · **不能直接读系统时钟的钟点**：720× 下现实 1 分钟 = 那边 12 小时，读钟点会变成
    "那边的时间和现在永远一样"。必须用累加虚拟秒。
  · **三餐按"跨过了几个饭点"算**，不按"现在是不是饭点"：720× 下午饭会在几十秒内被跨过去，
    按点判不是漏饭就是连吃三顿。

**不写盘**：菜单是确定性抽样（种子 = 角色 | 世界第几天 | 哪一餐），所以重启、回档、
电脑端和手机端算出来都一样，不需要新增任何状态文件。想让她"记得上次吃了什么"，
用同一套种子重算即可 —— 这比存一份可能过期的状态可靠。

为什么不塞进提示词整库
----------------------
库是**检索源不是注入内容**：整库喂进去既花预算（记忆上限也才 30%），又会把模型带成
机械罗列菜名。所以这里每轮只输出一小段（默认 ≤240 字）：现在几点、今天吃了什么、
手边有什么家伙、口味与忌口。指令部分只留一句"自然带出，别报数值"。
"""
import json
import os
import random
import threading
from datetime import datetime, timedelta

import app_paths

# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
#  一、厨具历史库（用户点名要的：这是"约束"，不是装饰）
#     year = 该时代的代表年份（用来过滤食材与做法）
#     tools = 那个年代厨房里真有的家伙；做法要靠它才成立
# ============================================================
ERAS = [
    {"key": "史前", "name": "史前（火塘）", "year": -8000,
     "tools": ["篝火", "石烤板", "木棍", "贝壳锅", "石刀"],
     "note": "没有容器，煮靠烧热的石头，烤是主要做法"},
    {"key": "新石器", "name": "新石器–青铜", "year": -2000,
     "tools": ["陶罐", "陶鬲", "陶甑", "陶灶", "石磨盘", "陶碗", "骨刀", "篝火"],
     "note": "有陶器就能煮粥炖汤；陶甑是最早的蒸锅，石磨能磨粉"},
    {"key": "先秦汉", "name": "先秦–汉", "year": -100,
     "tools": ["青铜鼎", "甑", "釜", "漆碗", "风箱", "铁锅", "灶台", "菜刀"],
     "note": "甑=最早的蒸锅；铁锅刚出现，还很贵"},
    {"key": "唐宋", "name": "唐宋", "year": 1000,
     "tools": ["铁炒锅", "蒸笼", "瓷碗", "炭炉", "风箱", "菜刀", "砧板", "灶台"],
     "note": "薄铁锅普及 → 炒菜从此成为主流（这是中国菜的分水岭）"},
    {"key": "明清", "name": "明清", "year": 1700,
     "tools": ["柴火灶", "铁炒锅", "蒸屉", "砂锅", "擀面杖", "石磨", "菜刀", "砧板"],
     "note": "辣椒/番茄/土豆/玉米此时才传入，之前的年代吃不到"},
    {"key": "民国", "name": "民国", "year": 1935,
     "tools": ["煤球炉", "铁炒锅", "铝锅", "搪瓷盆", "铁勺", "菜刀", "砧板"],
     "note": "煤炉进了城里人家，铝器开始替代陶器"},
    {"key": "1950s", "name": "1950–70 年代", "year": 1965,
     "tools": ["煤炉", "铁锅", "铝锅", "铝饭盒", "高压锅", "菜刀", "砧板"],
     "note": "高压锅有了，但食材靠票证，家常菜翻来覆去就那几样"},
    {"key": "1980s", "name": "1980–90 年代", "year": 1988,
     "tools": ["煤气灶", "铁锅", "铝壶", "电饭锅", "冰箱", "菜刀", "砧板"],
     "note": "煤气灶 + 电饭锅：做饭这件事开始变快"},
    {"key": "2000s", "name": "2000 年代", "year": 2005,
     "tools": ["不粘锅", "微波炉", "烤箱", "电磁炉", "抽油烟机", "电饭锅", "菜刀"],
     "note": "不粘锅与微波炉普及，厨艺门槛下降"},
    {"key": "现代", "name": "现代", "year": 2025,
     "tools": ["不粘锅", "空气炸锅", "电压力锅", "电磁炉", "烤箱", "微波炉", "料理机", "洗碗机"],
     "note": "半成品与外卖也在这个年代里"},
]
ERA_BY_KEY = {e["key"]: e for e in ERAS}

# 世界卡里出现这些词时自动认年代（按"越具体越优先"排）
ERA_HINTS = [
    ("史前", ("史前", "原始", "部落", "石器时代")),
    ("新石器", ("新石器", "青铜时代", "夏商", "商朝")),
    ("先秦汉", ("先秦", "春秋", "战国", "秦朝", "汉朝", "汉代", "三国")),
    ("唐宋", ("唐朝", "唐代", "宋朝", "宋代", "大唐", "大宋", "江湖", "武侠", "仙侠")),
    ("明清", ("明朝", "明代", "清朝", "清代", "大明", "大清", "民国前", "古代", "宫廷")),
    ("民国", ("民国", "军阀", "老上海", "三十年代")),
    ("1950s", ("1950", "1960", "1970", "文革", "知青", "公社", "票证")),
    ("1980s", ("1980", "1990", "八十年代", "九十年代", "工厂家属院", "下岗")),
    ("2000s", ("2000", "2005", "2010 前", "千禧")),
    ("现代", ("现代", "都市", "校园", "2020", "2025", "地铁", "手机")),
]

# 做法 → 需要什么家伙才做得了（关键词宽松匹配；空 = 什么年代都能做）
METHOD_NEEDS = {
    "煮": (),
    "炖": ("锅", "鼎", "鬲", "釜", "罐", "砂锅"),
    "蒸": ("蒸", "甑", "笼", "屉"),
    "炒": ("炒锅", "铁锅", "鼎", "锅"),
    "煎": ("锅", "鏊"),
    "烤": ("烤", "炉", "篝火", "烤箱", "炸"),
    "炸": ("锅", "炸锅"),
    "拌": (),
    "腌": (),
    "泡": (),
}
METHOD_SINCE = {"炒": 1000, "煎": 1000, "炸": 1000, "蒸": -2000, "煮": -8000,
                "炖": -2000, "烤": -8000, "拌": 600, "腌": -3000, "泡": -3000}

# ---------- 主食 / 菜 / 喝的 ----------
#   name 名字｜since 起始年（负数=公元前）｜until 到哪年为止（不写=至今）
#   regions 地域（"通用"=哪儿都有）｜meals 适合哪几餐｜method 做法（菜才有，用来查厨具）
#   ingredients 主要食材（忌口按它匹配）
BK, LU, DI, NI = "breakfast", "lunch", "dinner", "night"
ALL_MEALS = (BK, LU, DI, NI)

STAPLES = [
    {"name": "小米粥", "since": -8000, "regions": ("北方", "通用"), "meals": (BK, NI)},
    {"name": "糙米饭", "since": -6000, "regions": ("通用",), "meals": (LU, DI)},
    {"name": "白米饭", "since": -2000, "regions": ("江南", "粤", "川渝", "通用"), "meals": (LU, DI)},
    {"name": "麦饭", "since": -2000, "regions": ("北方",), "meals": (LU, DI)},
    {"name": "面条", "since": -200, "regions": ("北方", "通用"), "meals": (LU, NI)},
    {"name": "烙饼", "since": -200, "regions": ("北方",), "meals": (BK, LU, NI)},
    {"name": "馒头", "since": 200, "regions": ("北方",), "meals": (BK, LU, NI)},
    {"name": "饺子", "since": 200, "regions": ("北方", "通用"), "meals": (LU, DI, NI)},
    {"name": "馄饨", "since": 600, "regions": ("江南",), "meals": (BK, LU, NI)},
    {"name": "米粉", "since": 600, "regions": ("江南", "粤"), "meals": (BK, LU, NI)},
    {"name": "包子", "since": 1000, "regions": ("通用",), "meals": (BK, LU, NI)},
    {"name": "米线", "since": 1000, "regions": ("川渝",), "meals": (BK, LU, NI)},
    {"name": "泡馍", "since": 1000, "regions": ("西北",), "meals": (LU, NI)},
    {"name": "手抓饭", "since": 1000, "regions": ("西北",), "meals": (LU, DI)},
    {"name": "玉米糊糊", "since": 1550, "regions": ("北方",), "meals": (BK, LU)},
    {"name": "烤土豆", "since": 1600, "regions": ("北方", "西北"), "meals": (LU, NI)},
    {"name": "炸酱面", "since": 1700, "regions": ("北方",), "meals": (LU, DI)},
    {"name": "煲仔饭", "since": 1900, "regions": ("粤",), "meals": (LU, DI)},
    {"name": "肠粉", "since": 1900, "regions": ("粤",), "meals": (BK, LU)},
    {"name": "三明治", "since": 1900, "regions": ("通用",), "meals": (BK, LU, NI)},
    {"name": "方便面", "since": 1970, "regions": ("通用",), "meals": (LU, NI)},
    {"name": "速冻水饺", "since": 1990, "regions": ("通用",), "meals": (LU, DI, NI)},
]

# ---------- 菜：名字 / 做法 / 起始年 / 地域 / 主要食材 / 适合哪几餐 ----------
#  · since/until 是**历史约束**（辣椒番茄土豆明末才来，石煮鱼汤只在没有陶器的时候）
#  · meals 是**餐次约束**：东坡肉不该出现在早饭，油条不该出现在夜宵
DISHES = [
    # ---- 史前：只有火与石头 ----
    {"name": "烤野菜", "method": "烤", "since": -8000, "until": 1000,
     "regions": ("通用",), "ingredients": ("野菜",), "meals": (LU, DI)},
    {"name": "石煮鱼汤", "method": "煮", "since": -8000, "until": -1000,
     "regions": ("通用",), "ingredients": ("鱼",), "meals": (LU, DI)},
    {"name": "野菜粥", "method": "煮", "since": -6000, "until": 1950,
     "regions": ("通用",), "ingredients": ("野菜", "米"), "meals": (BK, LU)},
    {"name": "烤野味", "method": "烤", "since": -8000, "until": 600,
     "regions": ("通用",), "ingredients": ("野味",), "meals": (LU, DI)},
    # ---- 陶器–青铜：能煮、能炖、能蒸 ----
    {"name": "炖羊肉", "method": "炖", "since": -2000, "regions": ("北方", "西北"),
     "ingredients": ("羊肉",), "meals": (LU, DI)},
    {"name": "蒸野菜团", "method": "蒸", "since": -2000, "until": 1950,
     "regions": ("通用",), "ingredients": ("野菜", "面"), "meals": (BK, LU)},
    {"name": "腌菜", "method": "腌", "since": -2000, "regions": ("北方", "通用"),
     "ingredients": ("白菜", "萝卜"), "meals": (BK, LU, DI)},
    {"name": "煮豆羹", "method": "煮", "since": -1000, "until": 1950,
     "regions": ("通用",), "ingredients": ("豆",), "meals": (BK, LU)},
    {"name": "清蒸鱼", "method": "蒸", "since": -1000, "regions": ("江南", "粤"),
     "ingredients": ("鱼",), "meals": (LU, DI)},
    {"name": "鸡汤", "method": "炖", "since": -1000, "regions": ("通用",),
     "ingredients": ("鸡",), "meals": (LU, DI, NI)},
    {"name": "羊肉汤", "method": "炖", "since": -200, "regions": ("西北",),
     "ingredients": ("羊肉",), "meals": (LU, DI, NI)},
    {"name": "豆腐", "method": "煮", "since": 100, "regions": ("通用",),
     "ingredients": ("黄豆",), "meals": (LU, DI)},
    # ---- 唐宋：薄铁锅普及，炒成为主流（中国菜的分水岭）----
    {"name": "白切鸡", "method": "煮", "since": 600, "regions": ("粤",),
     "ingredients": ("鸡",), "meals": (LU, DI)},
    {"name": "凉拌黄瓜", "method": "拌", "since": 600, "regions": ("北方", "通用"),
     "ingredients": ("黄瓜", "蒜"), "meals": (LU, DI)},
    {"name": "咸鸭蛋", "method": "腌", "since": 600, "regions": ("江南",),
     "ingredients": ("鸭蛋",), "meals": (BK, LU)},
    {"name": "炒青菜", "method": "炒", "since": 1000, "regions": ("江南", "通用"),
     "ingredients": ("青菜",), "meals": (LU, DI)},
    {"name": "红烧肉", "method": "炖", "since": 1000, "regions": ("江南",),
     "ingredients": ("猪肉",), "meals": (LU, DI)},
    {"name": "蒜蓉菠菜", "method": "炒", "since": 1000, "regions": ("通用",),
     "ingredients": ("菠菜", "蒜"), "meals": (LU, DI)},
    {"name": "醋溜白菜", "method": "炒", "since": 1000, "regions": ("北方",),
     "ingredients": ("白菜", "醋"), "meals": (LU, DI)},
    {"name": "萝卜炖排骨", "method": "炖", "since": 1000, "regions": ("通用",),
     "ingredients": ("萝卜", "排骨"), "meals": (LU, DI)},
    {"name": "蛋花汤", "method": "煮", "since": 1000, "regions": ("通用",),
     "ingredients": ("鸡蛋",), "meals": (LU, DI, NI)},
    {"name": "煎蛋", "method": "煎", "since": 1000, "regions": ("通用",),
     "ingredients": ("鸡蛋",), "meals": (BK, LU, NI)},
    {"name": "东坡肉", "method": "炖", "since": 1080, "regions": ("江南",),
     "ingredients": ("猪肉",), "meals": (LU, DI)},
    {"name": "油条", "method": "炸", "since": 1142, "regions": ("北方", "通用"),
     "ingredients": ("面",), "meals": (BK,)},
    {"name": "叫花鸡", "method": "烤", "since": 1000, "regions": ("江南",),
     "ingredients": ("鸡",), "meals": (DI,)},
    {"name": "皮蛋", "method": "腌", "since": 1500, "regions": ("江南",),
     "ingredients": ("鸭蛋",), "meals": (BK, LU)},
    # ---- 明清：辣椒 / 番茄 / 土豆 / 玉米 此时才传入 ----
    {"name": "辣椒炒肉", "method": "炒", "since": 1650, "regions": ("川渝", "江南"),
     "ingredients": ("辣椒", "猪肉"), "meals": (LU, DI)},
    {"name": "麻婆豆腐", "method": "炒", "since": 1862, "regions": ("川渝",),
     "ingredients": ("豆腐", "辣椒", "花椒", "牛肉"), "meals": (LU, DI)},
    {"name": "水煮鱼", "method": "煮", "since": 1900, "regions": ("川渝",),
     "ingredients": ("鱼", "辣椒"), "meals": (LU, DI)},
    {"name": "宫保鸡丁", "method": "炒", "since": 1900, "regions": ("川渝",),
     "ingredients": ("鸡", "花生", "辣椒"), "meals": (LU, DI)},
    {"name": "回锅肉", "method": "炒", "since": 1900, "regions": ("川渝",),
     "ingredients": ("猪肉", "蒜苗"), "meals": (LU, DI)},
    {"name": "番茄炒蛋", "method": "炒", "since": 1900, "regions": ("通用",),
     "ingredients": ("番茄", "鸡蛋"), "meals": (LU, DI)},
    {"name": "青椒肉丝", "method": "炒", "since": 1900, "regions": ("通用",),
     "ingredients": ("青椒", "猪肉"), "meals": (LU, DI)},
    {"name": "紫菜蛋花汤", "method": "煮", "since": 1900, "regions": ("通用",),
     "ingredients": ("紫菜", "鸡蛋"), "meals": (LU, DI, NI)},
    {"name": "云吞面", "method": "煮", "since": 1900, "regions": ("粤",),
     "ingredients": ("面", "虾"), "meals": (BK, LU, NI)},
    {"name": "粉蒸肉", "method": "蒸", "since": 1900, "regions": ("川渝", "江南"),
     "ingredients": ("猪肉", "米粉"), "meals": (LU, DI)},
    {"name": "锅包肉", "method": "炸", "since": 1907, "regions": ("北方",),
     "ingredients": ("猪肉",), "meals": (LU, DI)},
    {"name": "西红柿鸡蛋面", "method": "煮", "since": 1900, "regions": ("北方", "通用"),
     "ingredients": ("番茄", "鸡蛋", "面"), "meals": (BK, LU, NI)},
    {"name": "兰州牛肉面", "method": "煮", "since": 1915, "regions": ("西北",),
     "ingredients": ("牛肉", "面"), "meals": (BK, LU, NI)},
    {"name": "豆浆油条", "method": "炸", "since": 1900, "regions": ("北方", "通用"),
     "ingredients": ("黄豆", "面"), "meals": (BK,)},
    # ---- 近现代 ----
    {"name": "红烧带鱼", "method": "炖", "since": 1950, "regions": ("通用",),
     "ingredients": ("带鱼",), "meals": (LU, DI)},
    {"name": "醋溜土豆丝", "method": "炒", "since": 1950, "regions": ("北方", "通用"),
     "ingredients": ("土豆", "醋"), "meals": (LU, DI)},
    {"name": "西红柿炒菜花", "method": "炒", "since": 1980, "regions": ("通用",),
     "ingredients": ("番茄", "菜花"), "meals": (LU, DI)},
    {"name": "方便面加蛋", "method": "煮", "since": 1970, "regions": ("通用",),
     "ingredients": ("面", "鸡蛋"), "meals": (LU, NI)},
    {"name": "烤串", "method": "烤", "since": 1980, "regions": ("北方", "川渝", "通用"),
     "ingredients": ("羊肉", "孜然"), "meals": (NI,)},
    {"name": "烤翅", "method": "烤", "since": 2000, "regions": ("通用",),
     "ingredients": ("鸡翅",), "meals": (LU, NI)},
    {"name": "沙拉", "method": "拌", "since": 2000, "regions": ("通用",),
     "ingredients": ("生菜", "番茄"), "meals": (BK, LU)},
    {"name": "空气炸鸡块", "method": "炸", "since": 2015, "regions": ("通用",),
     "ingredients": ("鸡",), "meals": (LU, NI)},
]

# ---------- 喝的 ----------
DRINKS = [
    {"name": "凉水", "since": -8000, "regions": ("通用",), "meals": ALL_MEALS},
    {"name": "米汤", "since": -6000, "regions": ("通用",), "meals": (BK, LU)},
    {"name": "茶", "since": -100, "regions": ("通用",), "meals": (BK, LU, DI)},
    {"name": "豆浆", "since": 100, "regions": ("通用",), "meals": (BK,)},
    {"name": "酸梅汤", "since": 1000, "regions": ("北方", "通用"), "meals": (LU, DI)},
    {"name": "黄酒", "since": -200, "regions": ("江南",), "meals": (DI,)},
    {"name": "汽水", "since": 1900, "regions": ("通用",), "meals": (LU, DI)},
    {"name": "啤酒", "since": 1900, "regions": ("通用",), "meals": (NI, DI)},
    {"name": "可乐", "since": 1980, "regions": ("通用",), "meals": (LU, NI)},
    {"name": "奶茶", "since": 2000, "regions": ("通用",), "meals": (LU,)},
    {"name": "咖啡", "since": 1900, "regions": ("通用",), "meals": (BK, LU)},
]

PHASES = ((4, "深夜"), (9, "清晨"), (11, "上午"), (13, "中午"),
          (17, "午后"), (19, "傍晚"), (23, "夜里"), (24, "深夜"))

# 一天从凌晨 4 点算起：夜宵（21:30 起）跟晚饭算同一天
LIFE_DAY_START_HOUR = 4
MEALS = (("breakfast", "早饭", 6.5), ("lunch", "午饭", 11.5),
         ("dinner", "晚饭", 17.5), ("night", "夜宵", 21.5))
# (key, label) 视图：day_menu / 外部只想"有哪几餐"时用这个，免得每次三拆二
MEAL_LABELS = tuple((k, label) for k, label, _ in MEALS)
REGIONS = ("auto", "北方", "江南", "川渝", "粤", "西北")

DEFAULTS = {
    "enabled": True,
    "era": "auto",          # auto 或 ERAS 里的 key
    "region": "auto",
    "taste": "",            # 清淡 / 重口 / 嗜甜 …（角色卡 advanced.life.taste 优先）
    "avoid": "",            # 忌口，逗号分隔：香菜,海鲜
    "show_meals": True,     # 注入里带"今天吃了什么"
    "max_chars": 240,       # 注入长度上限
    "location": "家",       # 在哪儿做/吃：家 / 出租屋 / 宿舍 / 野外 …
}

_lock = threading.Lock()
_cache = None


# ============================================================
#  二、配置（跟 time_scale.json 一个规矩：自己的文件，自己的缓存）
# ============================================================
def config_path():
    try:
        base = app_paths.get_base_dir()
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "life_config.json")


def load_config():
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
    data = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            got = json.load(f)
        if isinstance(got, dict):
            for k in DEFAULTS:
                if k in got:
                    data[k] = got[k]
    except Exception:
        pass
    with _lock:
        _cache = dict(data)
    return data


def save_config(cfg):
    global _cache
    data = dict(DEFAULTS)
    data.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    with _lock:
        _cache = dict(data)
    try:
        p = config_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except Exception as e:
        print("[life] 配置保存失败: %s" % e)
    return data


def enabled():
    try:
        return bool(load_config().get("enabled"))
    except Exception:
        return False


# ============================================================
#  三、世界时钟（系统时间 = 1× 起源）
# ============================================================
def _parse_ts(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts))
    except (ValueError, TypeError):
        return None
    if d.tzinfo is not None:
        d = d.astimezone().replace(tzinfo=None)
    return d


def world_clock(chain, scale=None, now=None):
    """把"那边现在几点"算出来。链里没有可用时间戳就返回 None。

    返回：{origin, world_dt, day, hhmm, phase, elapsed_real, elapsed_world,
           elapsed_days, life_day, meals_today, source}
    """
    try:
        sc = float(scale) if scale else 1.0
    except (TypeError, ValueError):
        sc = 1.0
    if sc <= 0 or sc != sc:
        sc = 1.0
    stamps = []
    for m in chain or []:
        if not isinstance(m, dict) or m.get("role") == "system":
            continue
        d = _parse_ts(m.get("timestamp"))
        if d is not None:
            stamps.append(d)
    if not stamps:
        return None
    end = now if isinstance(now, datetime) else datetime.now()
    origin = stamps[0]
    elapsed = 0.0
    for i in range(1, len(stamps)):
        gap = (stamps[i] - stamps[i - 1]).total_seconds()
        elapsed += max(0.0, gap)          # 时钟回拨/脏数据当 0，不让世界倒退
    elapsed += max(0.0, (end - stamps[-1]).total_seconds())
    world_sec = elapsed * sc
    world_dt = origin + timedelta(seconds=world_sec)
    life_day = (world_dt - timedelta(hours=LIFE_DAY_START_HOUR)).date()
    origin_life_day = (origin - timedelta(hours=LIFE_DAY_START_HOUR)).date()
    return {
        "origin": origin,
        "world_dt": world_dt,
        "day": (life_day - origin_life_day).days + 1,
        "life_day": life_day,
        "hhmm": world_dt.strftime("%H:%M"),
        "phase": phase_of(world_dt.hour),
        "elapsed_real": elapsed,
        "elapsed_world": world_sec,
        "elapsed_days": elapsed / 86400.0,
        "meals_today": meals_passed(world_dt),
        "source": "chain",
    }


def phase_of(hour):
    """时段：给模型一个"现在该干什么"的常识锚"""
    h = int(hour) % 24
    for end, name in PHASES:
        if h < end:
            return name
    return "深夜"


def meals_passed(world_dt):
    """这一天已经过了哪些饭点（按饭点【开始时刻】判，不看窗口结束）"""
    out = []
    minutes = world_dt.hour * 60 + world_dt.minute
    for key, label, start_hour in MEALS:
        if minutes >= int(start_hour * 60):
            out.append((key, label))
    return out


# ============================================================
#  四、资料过滤：年代 / 地域 / 忌口
# ============================================================
def _regions_of(item_regions):
    return tuple(item_regions or ())


def _region_ok(item_regions, region):
    if region in (None, "", "auto"):
        return True
    rs = _regions_of(item_regions)
    return ("通用" in rs) or (region in rs)


def _since_ok(since, era_year):
    try:
        return int(since) <= int(era_year)
    except (TypeError, ValueError):
        return True


def _until_ok(until, era_year):
    """历史窗口的另一半：石煮鱼汤在没有陶器的年代之后就不该再出现"""
    if until is None:
        return True
    try:
        return int(era_year) <= int(until)
    except (TypeError, ValueError):
        return True


def _meal_ok(item, meal_key):
    meals = item.get("meals")
    return (not meals) or (meal_key in meals)


def _avoid_hit(name, ingredients, avoid):
    if not avoid:
        return False
    for bad in avoid:
        if not bad:
            continue
        if bad in (name or ""):
            return True
        for ing in ingredients or ():
            if bad in str(ing):
                return True
    return False


def tools_for(era_key):
    era = ERA_BY_KEY.get(era_key) or ERA_BY_KEY["现代"]
    return list(era["tools"])


def method_ok(method, tools, era_year):
    """厨具历史库的用处：这个年代有没有做这道菜的家伙"""
    try:
        if int(era_year) < int(METHOD_SINCE.get(method, -100000)):
            return False
    except (TypeError, ValueError):
        pass
    needs = METHOD_NEEDS.get(method, ())
    if not needs:
        return True
    blob = "".join(str(t) for t in tools)
    return any(k in blob for k in needs)


def detect_era(world):
    """从世界卡里认年代；认不出就现代（不猜错比猜洋气重要）"""
    text = ""
    if isinstance(world, dict):
        parts = [world.get("name"), world.get("description"), world.get("rules")]
        for p in parts:
            if isinstance(p, str):
                text += p
        params = world.get("params")
        if isinstance(params, dict):
            text += " ".join(str(v) for v in params.values())
    elif isinstance(world, str):
        text = world
    for key, hints in ERA_HINTS:
        for h in hints:
            if h in text:
                return key
    return "现代"


def _as_list(v):
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        for sep in ("，", ",", "、", ";", "；", " "):
            v = v.replace(sep, "|")
        return [x.strip() for x in v.split("|") if x.strip()]
    return []


def profile_for(role=None, cfg=None, world=None):
    """角色卡 advanced.life 优先 > life_config > 默认；年代能 auto 认出来。

    带 *_from 字段说明这份设置是哪来的 —— 命令面板上要讲清楚，
    否则会出现"我在 /生活 里改了年代怎么没生效"（角色卡把它盖掉了）。
    """
    cfg = dict(DEFAULTS, **(cfg or {}))
    role = role if isinstance(role, dict) else {}
    adv = role.get("advanced")
    life = adv.get("life") if isinstance(adv, dict) and isinstance(adv.get("life"), dict) else {}
    era = str(life.get("era") or cfg.get("era") or "auto")
    era_from = "角色卡" if life.get("era") else ("全局" if cfg.get("era") not in (None, "auto") else "自动")
    if era == "auto" or era not in ERA_BY_KEY:
        era = detect_era(world)
        era_from = "自动认出" if era_from != "角色卡" else era_from
    region = str(life.get("region") or cfg.get("region") or "auto")
    region_from = "角色卡" if life.get("region") else "全局"
    if region not in REGIONS:
        region = "auto"
    return {
        "role": str(role.get("name") or "她"),
        "era": era,
        "era_from": era_from,
        "era_year": ERA_BY_KEY.get(era, ERA_BY_KEY["现代"])["year"],
        "tools": tools_for(era),
        "region": region,
        "region_from": region_from,
        "taste": str(life.get("taste") or cfg.get("taste") or ""),
        "avoid": _as_list(life.get("avoid")) or _as_list(cfg.get("avoid")),
        "skill": str(life.get("skill") or ""),
        "location": str(life.get("location") or cfg.get("location") or "家"),
        "show_meals": bool(cfg.get("show_meals")),
        "max_chars": int(cfg.get("max_chars") or DEFAULTS["max_chars"]),
    }


# ============================================================
#  五、确定性抽样：同一角色同一天同一餐，永远同一份菜单
# ============================================================
def _pick(rng, pool):
    return pool[rng.randrange(len(pool))] if pool else None


def _taste_bias(name, taste):
    """口味只是加权，不硬过滤 —— 清淡的人偶尔也想吃顿重口的"""
    if not taste:
        return 1.0
    light = ("清淡", "素", "少油", "养生")
    heavy = ("重口", "嗜辣", "无辣不欢", "重油")
    mild = ("炖", "煮", "蒸", "拌")
    strong = ("炒", "炸", "烤")
    for w in light:
        if w in taste:
            return 2.5 if name in mild else (0.4 if name in strong else 1.0)
    for w in heavy:
        if w in taste:
            return 2.5 if name in strong else (0.5 if name in mild else 1.0)
    return 1.0


def _weighted(rng, names, taste):
    """按口味权重抽一个做法（名字），权重用整数放大避免浮点误差"""
    pool = []
    for n in names:
        w = int(round(_taste_bias(n, taste) * 10))
        pool.extend([n] * max(1, w))
    return _pick(rng, pool)


def sample_meal(profile, life_day, meal_key, meal_label, used=None):
    """一餐 = 主食 + 1~2 个菜 + 一杯喝的。

    过滤链：年代窗口 → 地域 → 忌口 → 餐次（早饭不吃东坡肉）→ 厨具（这个年代做不做得了）
    → 当天去重（同一天里别三顿都吃同一道）。
    全部确定性：种子 = 角色 | 世界第几天 | 哪一餐。
    """
    used = set(used or ())
    rng = random.Random("%s|%s|%s" % (profile["role"], life_day, meal_key))
    era_year = profile["era_year"]
    tools = profile["tools"]
    region = profile["region"]
    avoid = profile["avoid"]

    def ok(item):
        return (_since_ok(item.get("since"), era_year)
                and _until_ok(item.get("until"), era_year)
                and _region_ok(item.get("regions"), region)
                and _meal_ok(item, meal_key)
                and not _avoid_hit(item.get("name"), item.get("ingredients"), avoid))

    staples = [s for s in STAPLES if ok(s)]
    dishes = [d for d in DISHES if ok(d) and method_ok(d.get("method"), tools, era_year)]
    drinks = [d for d in DRINKS if ok(d)]

    fresh_staples = [s for s in staples if s["name"] not in used] or staples
    fresh_dishes = [d for d in dishes if d["name"] not in used] or dishes

    staple = _pick(rng, fresh_staples)
    picked = []
    if fresh_dishes:
        methods = _weighted(rng, sorted(set(d.get("method", "") for d in fresh_dishes)),
                            profile["taste"])
        same = [d for d in fresh_dishes if d.get("method") == methods]
        first = _pick(rng, same) or _pick(rng, fresh_dishes)
        if first:
            picked.append(first)
        rest = [d for d in fresh_dishes if d is not first]
        if rest and rng.random() < 0.55:
            picked.append(_pick(rng, rest))
    fresh_drinks = [d for d in drinks if d["name"] not in used] or drinks
    drink = _pick(rng, fresh_drinks) if rng.random() < 0.5 else None

    parts = []
    if staple:
        parts.append(staple["name"])
    parts.extend(d["name"] for d in picked)
    used_here = [x["name"] for x in ([staple] if staple else []) + picked] + \
                ([drink["name"]] if drink else [])
    return {
        "meal": meal_label,
        "key": meal_key,
        "dish": " + ".join(parts) if parts else "随便对付一口",
        "staple": staple["name"] if staple else "",
        "dishes": [d["name"] for d in picked],
        "methods": [d.get("method", "") for d in picked],
        "drink": drink["name"] if drink else "",
        "tools": tools,
        "used": used_here,
    }


def day_menu(profile, life_day, meals):
    """这一天已经过了的饭点各吃什么（确定性；同一天里尽量不重样）"""
    out = []
    used = set()
    for key, label in meals:
        m = sample_meal(profile, life_day, key, label, used=used)
        used.update(m.get("used") or ())
        out.append(m)
    return out


# ============================================================
#  六、给模型的那一小段（严格限长）
# ============================================================
GUIDE = "（生活细节自然带出即可，不必每轮都提吃的；饿了/累了在语气里体现，不要报数值。）"


def injection_text(chain, scale=None, role=None, world=None, cfg=None, now=None):
    """每轮注入的【生活·那边】。没有可用时间戳 / 关掉了 / 算不出，都返回 ""。

    长度按**优先级**吃预算（而不是从尾巴硬截）：时间 → 今天吃了什么 → 忌口 → 家伙 →
    口味 → 在哪儿 → 使用说明。截断了至少还是"那边几点、她今天吃了什么"。
    """
    cfg = load_config() if cfg is None else dict(DEFAULTS, **cfg)
    if not cfg.get("enabled"):
        return ""
    clock = world_clock(chain, scale, now=now)
    if clock is None:
        return ""
    profile = profile_for(role, cfg, world)
    menu = day_menu(profile, clock["life_day"].toordinal(), clock["meals_today"]) \
        if profile["show_meals"] else []

    # 第几天只在开局头几天有意义：倍率 720 时现实 2 分钟 = 那边 1 天，
    # 报"第 21 天"对模型没有任何用处，反而会把"过了多久"说乱（那件事 time_context 已经在做）。
    day_txt = ("第 %d 天 " % clock["day"]) if clock["day"] <= 3 else ""
    head = "【生活·那边】%s%s（%s）" % (day_txt, clock["hhmm"], clock["phase"])
    if clock["phase"] == "深夜":
        head += "｜夜已深，她该睡了（若还醒着，给个合理的由头）"

    # 优先级队列：(文本, 是否必须)。必须的项即使超预算也保留，否则整段没用。
    items = []
    if menu:
        items.append(("今天： " + "｜".join(
            "%s %s" % (m["meal"], m["dish"] + ("，" + m["drink"] if m["drink"] else ""))
            for m in menu), True))
    if profile["avoid"]:
        items.append(("不吃" + "、".join(profile["avoid"]), True))
    items.append(("手边家伙：" + "、".join(profile["tools"][:6]), False))
    if profile["taste"]:
        items.append(("口味" + profile["taste"], False))
    if profile["location"]:
        items.append(("在" + profile["location"], False))

    room = max(60, int(profile["max_chars"]) - len(head) - len(GUIDE) - 2)
    kept = []
    for text, must in items:
        piece = text + ("。" if kept or must else "")
        if kept and len("".join(kept)) + len(piece) > room and not must:
            continue
        kept.append(piece)
    tail = "".join(kept)
    out = head + (("\n" + tail) if tail else "")
    return out + "\n" + GUIDE


def describe(chain, scale=None, role=None, world=None, cfg=None, now=None):
    """给 /生活 命令看的完整状态（比注入详细）"""
    cfg = load_config() if cfg is None else dict(DEFAULTS, **cfg)
    clock = world_clock(chain, scale, now=now)
    profile = profile_for(role, cfg, world)
    lines = ["生活层：%s" % ("开" if cfg.get("enabled") else "关")]
    if clock is None:
        lines.append("世界时钟：算不出（这条链里没有节点时间戳 —— 新开一局、还没说过话就会这样）")
    else:
        lines.append("世界时钟：第 %d 天 %s（%s）｜那边已过 %.1f 天（现实 %.1f 分钟 × %.4g 倍）"
                     % (clock["day"], clock["hhmm"], clock["phase"], clock["elapsed_world"] / 86400.0,
                        clock["elapsed_real"] / 60.0, scale or 1))
    lines.append("年代：%s（来自%s）%s" % (profile["era"], profile["era_from"],
                                        ERA_BY_KEY.get(profile["era"], {}).get("note", "")))
    lines.append("手边家伙：" + "、".join(profile["tools"]))
    if profile["region"] != "auto":
        lines.append("地域：%s（来自%s）" % (profile["region"], profile["region_from"]))
    if profile["taste"]:
        lines.append("口味：" + profile["taste"])
    if profile["avoid"]:
        lines.append("忌口：" + "、".join(profile["avoid"]))
    if clock is not None:
        menu = day_menu(profile, clock["life_day"].toordinal(), clock["meals_today"])
        if menu:
            lines.append("今天吃过：")
            for m in menu:
                lines.append("  %s：%s%s" % (m["meal"], m["dish"],
                                             ("｜" + m["drink"]) if m["drink"] else ""))
        else:
            lines.append("今天还没吃饭点（那边刚天亮）")
    return "\n".join(lines)
