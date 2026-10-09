// ⚠ 生成物：由 tools/gen_parity.py 从 life_co<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌re.py / space_core.py / commonsense.py
//   生成。别手改 —— 手改会被 `python tools/gen_parity.py --check` 判为过期，
//   而且下一次生成就没了。要改表就改 Python 那边，然后重新生成。

package com.dick.core

/** 厨具历史库 + 食材/做法库 + 餐次/时段（来自 life_core.py）。 */
object LifeTables {

    val ERAS: List<LifeEra> = listOf(
        LifeEra(key = "史前", name = "史前（火塘）", year = -8000, tools = listOf("篝火", "石烤板", "木棍", "贝壳锅", "石刀"), note = "没有容器，煮靠烧热的石头，烤是主要做法"),
        LifeEra(key = "新石器", name = "新石器–青铜", year = -2000, tools = listOf("陶罐", "陶鬲", "陶甑", "陶灶", "石磨盘", "陶碗", "骨刀", "篝火"), note = "有陶器就能煮粥炖汤；陶甑是最早的蒸锅，石磨能磨粉"),
        LifeEra(key = "先秦汉", name = "先秦–汉", year = -100, tools = listOf("青铜鼎", "甑", "釜", "漆碗", "风箱", "铁锅", "灶台", "菜刀"), note = "甑=最早的蒸锅；铁锅刚出现，还很贵"),
        LifeEra(key = "唐宋", name = "唐宋", year = 1000, tools = listOf("铁炒锅", "蒸笼", "瓷碗", "炭炉", "风箱", "菜刀", "砧板", "灶台"), note = "薄铁锅普及 → 炒菜从此成为主流（这是中国菜的分水岭）"),
        LifeEra(key = "明清", name = "明清", year = 1700, tools = listOf("柴火灶", "铁炒锅", "蒸屉", "砂锅", "擀面杖", "石磨", "菜刀", "砧板"), note = "辣椒/番茄/土豆/玉米此时才传入，之前的年代吃不到"),
        LifeEra(key = "民国", name = "民国", year = 1935, tools = listOf("煤球炉", "铁炒锅", "铝锅", "搪瓷盆", "铁勺", "菜刀", "砧板"), note = "煤炉进了城里人家，铝器开始替代陶器"),
        LifeEra(key = "1950s", name = "1950–70 年代", year = 1965, tools = listOf("煤炉", "铁锅", "铝锅", "铝饭盒", "高压锅", "菜刀", "砧板"), note = "高压锅有了，但食材靠票证，家常菜翻来覆去就那几样"),
        LifeEra(key = "1980s", name = "1980–90 年代", year = 1988, tools = listOf("煤气灶", "铁锅", "铝壶", "电饭锅", "冰箱", "菜刀", "砧板"), note = "煤气灶 + 电饭锅：做饭这件事开始变快"),
        LifeEra(key = "2000s", name = "2000 年代", year = 2005, tools = listOf("不粘锅", "微波炉", "烤箱", "电磁炉", "抽油烟机", "电饭锅", "菜刀"), note = "不粘锅与微波炉普及，厨艺门槛下降"),
        LifeEra(key = "现代", name = "现代", year = 2025, tools = listOf("不粘锅", "空气炸锅", "电压力锅", "电磁炉", "烤箱", "微波炉", "料理机", "洗碗机"), note = "半成品与外卖也在这个年代里"),
    )
    val ERA_BY_KEY: Map<String, LifeEra> = ERAS.associateBy { it.key }

    /** 世界卡关键词 → 年代（越具体越优先，顺序就是优先级）。 */
    val ERA_HINTS: List<Pair<String, List<String>>> = listOf(
        "史前" to listOf("史前", "原始", "部落", "石器时代"),
        "新石器" to listOf("新石器", "青铜时代", "夏商", "商朝"),
        "先秦汉" to listOf("先秦", "春秋", "战国", "秦朝", "汉朝", "汉代", "三国"),
        "唐宋" to listOf("唐朝", "唐代", "宋朝", "宋代", "大唐", "大宋", "江湖", "武侠", "仙侠"),
        "明清" to listOf("明朝", "明代", "清朝", "清代", "大明", "大清", "民国前", "古代", "宫廷"),
        "民国" to listOf("民国", "军阀", "老上海", "三十年代"),
        "1950s" to listOf("1950", "1960", "1970", "文革", "知青", "公社", "票证"),
        "1980s" to listOf("1980", "1990", "八十年代", "九十年代", "工厂家属院", "下岗"),
        "2000s" to listOf("2000", "2005", "2010 前", "千禧"),
        "现代" to listOf("现代", "都市", "校园", "2020", "2025", "地铁", "手机"),
    )

    /** 做法 → 需要什么家伙才做得了（关键词宽松匹配）。 */
    val METHOD_NEEDS: Map<String, List<String>> = linkedMapOf(
        "煮" to emptyList(),
        "炖" to listOf("锅", "鼎", "鬲", "釜", "罐", "砂锅"),
        "蒸" to listOf("蒸", "甑", "笼", "屉"),
        "炒" to listOf("炒锅", "铁锅", "鼎", "锅"),
        "煎" to listOf("锅", "鏊"),
        "烤" to listOf("烤", "炉", "篝火", "烤箱", "炸"),
        "炸" to listOf("锅", "炸锅"),
        "拌" to emptyList(),
        "腌" to emptyList(),
        "泡" to emptyList(),
    )
    val METHOD_SINCE: Map<String, Int> = linkedMapOf(
        "炒" to 1000,
        "煎" to 1000,
        "炸" to 1000,
        "蒸" to -2000,
        "煮" to -8000,
        "炖" to -2000,
        "烤" to -8000,
        "拌" to 600,
        "腌" to -3000,
        "泡" to -3000,
    )

    val STAPLES: List<LifeItem> = listOf(
        LifeItem(name = "小米粥", since = -8000, until = null, regions = listOf("北方", "通用"), meals = listOf("breakfast", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "糙米饭", since = -6000, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "白米饭", since = -2000, until = null, regions = listOf("江南", "粤", "川渝", "通用"), meals = listOf("lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "麦饭", since = -2000, until = null, regions = listOf("北方"), meals = listOf("lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "面条", since = -200, until = null, regions = listOf("北方", "通用"), meals = listOf("lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "烙饼", since = -200, until = null, regions = listOf("北方"), meals = listOf("breakfast", "lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "馒头", since = 200, until = null, regions = listOf("北方"), meals = listOf("breakfast", "lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "饺子", since = 200, until = null, regions = listOf("北方", "通用"), meals = listOf("lunch", "dinner", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "馄饨", since = 600, until = null, regions = listOf("江南"), meals = listOf("breakfast", "lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "米粉", since = 600, until = null, regions = listOf("江南", "粤"), meals = listOf("breakfast", "lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "包子", since = 1000, until = null, regions = listOf("通用"), meals = listOf("breakfast", "lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "米线", since = 1000, until = null, regions = listOf("川渝"), meals = listOf("breakfast", "lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "泡馍", since = 1000, until = null, regions = listOf("西北"), meals = listOf("lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "手抓饭", since = 1000, until = null, regions = listOf("西北"), meals = listOf("lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "玉米糊糊", since = 1550, until = null, regions = listOf("北方"), meals = listOf("breakfast", "lunch"), method = "", ingredients = emptyList()),
        LifeItem(name = "烤土豆", since = 1600, until = null, regions = listOf("北方", "西北"), meals = listOf("lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "炸酱面", since = 1700, until = null, regions = listOf("北方"), meals = listOf("lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "煲仔饭", since = 1900, until = null, regions = listOf("粤"), meals = listOf("lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "肠粉", since = 1900, until = null, regions = listOf("粤"), meals = listOf("breakfast", "lunch"), method = "", ingredients = emptyList()),
        LifeItem(name = "三明治", since = 1900, until = null, regions = listOf("通用"), meals = listOf("breakfast", "lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "方便面", since = 1970, until = null, regions = listOf("通用"), meals = listOf("lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "速冻水饺", since = 1990, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner", "night"), method = "", ingredients = emptyList()),
    )

    val DISHES: List<LifeItem> = listOf(
        LifeItem(name = "烤野菜", since = -8000, until = 1000, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "烤", ingredients = listOf("野菜")),
        LifeItem(name = "石煮鱼汤", since = -8000, until = -1000, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "煮", ingredients = listOf("鱼")),
        LifeItem(name = "野菜粥", since = -6000, until = 1950, regions = listOf("通用"), meals = listOf("breakfast", "lunch"), method = "煮", ingredients = listOf("野菜", "米")),
        LifeItem(name = "烤野味", since = -8000, until = 600, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "烤", ingredients = listOf("野味")),
        LifeItem(name = "炖羊肉", since = -2000, until = null, regions = listOf("北方", "西北"), meals = listOf("lunch", "dinner"), method = "炖", ingredients = listOf("羊肉")),
        LifeItem(name = "蒸野菜团", since = -2000, until = 1950, regions = listOf("通用"), meals = listOf("breakfast", "lunch"), method = "蒸", ingredients = listOf("野菜", "面")),
        LifeItem(name = "腌菜", since = -2000, until = null, regions = listOf("北方", "通用"), meals = listOf("breakfast", "lunch", "dinner"), method = "腌", ingredients = listOf("白菜", "萝卜")),
        LifeItem(name = "煮豆羹", since = -1000, until = 1950, regions = listOf("通用"), meals = listOf("breakfast", "lunch"), method = "煮", ingredients = listOf("豆")),
        LifeItem(name = "清蒸鱼", since = -1000, until = null, regions = listOf("江南", "粤"), meals = listOf("lunch", "dinner"), method = "蒸", ingredients = listOf("鱼")),
        LifeItem(name = "鸡汤", since = -1000, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner", "night"), method = "炖", ingredients = listOf("鸡")),
        LifeItem(name = "羊肉汤", since = -200, until = null, regions = listOf("西北"), meals = listOf("lunch", "dinner", "night"), method = "炖", ingredients = listOf("羊肉")),
        LifeItem(name = "豆腐", since = 100, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "煮", ingredients = listOf("黄豆")),
        LifeItem(name = "白切鸡", since = 600, until = null, regions = listOf("粤"), meals = listOf("lunch", "dinner"), method = "煮", ingredients = listOf("鸡")),
        LifeItem(name = "凉拌黄瓜", since = 600, until = null, regions = listOf("北方", "通用"), meals = listOf("lunch", "dinner"), method = "拌", ingredients = listOf("黄瓜", "蒜")),
        LifeItem(name = "咸鸭蛋", since = 600, until = null, regions = listOf("江南"), meals = listOf("breakfast", "lunch"), method = "腌", ingredients = listOf("鸭蛋")),
        LifeItem(name = "炒青菜", since = 1000, until = null, regions = listOf("江南", "通用"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("青菜")),
        LifeItem(name = "红烧肉", since = 1000, until = null, regions = listOf("江南"), meals = listOf("lunch", "dinner"), method = "炖", ingredients = listOf("猪肉")),
        LifeItem(name = "蒜蓉菠菜", since = 1000, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("菠菜", "蒜")),
        LifeItem(name = "醋溜白菜", since = 1000, until = null, regions = listOf("北方"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("白菜", "醋")),
        LifeItem(name = "萝卜炖排骨", since = 1000, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "炖", ingredients = listOf("萝卜", "排骨")),
        LifeItem(name = "蛋花汤", since = 1000, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner", "night"), method = "煮", ingredients = listOf("鸡蛋")),
        LifeItem(name = "煎蛋", since = 1000, until = null, regions = listOf("通用"), meals = listOf("breakfast", "lunch", "night"), method = "煎", ingredients = listOf("鸡蛋")),
        LifeItem(name = "东坡肉", since = 1080, until = null, regions = listOf("江南"), meals = listOf("lunch", "dinner"), method = "炖", ingredients = listOf("猪肉")),
        LifeItem(name = "油条", since = 1142, until = null, regions = listOf("北方", "通用"), meals = listOf("breakfast"), method = "炸", ingredients = listOf("面")),
        LifeItem(name = "叫花鸡", since = 1000, until = null, regions = listOf("江南"), meals = listOf("dinner"), method = "烤", ingredients = listOf("鸡")),
        LifeItem(name = "皮蛋", since = 1500, until = null, regions = listOf("江南"), meals = listOf("breakfast", "lunch"), method = "腌", ingredients = listOf("鸭蛋")),
        LifeItem(name = "辣椒炒肉", since = 1650, until = null, regions = listOf("川渝", "江南"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("辣椒", "猪肉")),
        LifeItem(name = "麻婆豆腐", since = 1862, until = null, regions = listOf("川渝"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("豆腐", "辣椒", "花椒", "牛肉")),
        LifeItem(name = "水煮鱼", since = 1900, until = null, regions = listOf("川渝"), meals = listOf("lunch", "dinner"), method = "煮", ingredients = listOf("鱼", "辣椒")),
        LifeItem(name = "宫保鸡丁", since = 1900, until = null, regions = listOf("川渝"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("鸡", "花生", "辣椒")),
        LifeItem(name = "回锅肉", since = 1900, until = null, regions = listOf("川渝"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("猪肉", "蒜苗")),
        LifeItem(name = "番茄炒蛋", since = 1900, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("番茄", "鸡蛋")),
        LifeItem(name = "青椒肉丝", since = 1900, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("青椒", "猪肉")),
        LifeItem(name = "紫菜蛋花汤", since = 1900, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner", "night"), method = "煮", ingredients = listOf("紫菜", "鸡蛋")),
        LifeItem(name = "云吞面", since = 1900, until = null, regions = listOf("粤"), meals = listOf("breakfast", "lunch", "night"), method = "煮", ingredients = listOf("面", "虾")),
        LifeItem(name = "粉蒸肉", since = 1900, until = null, regions = listOf("川渝", "江南"), meals = listOf("lunch", "dinner"), method = "蒸", ingredients = listOf("猪肉", "米粉")),
        LifeItem(name = "锅包肉", since = 1907, until = null, regions = listOf("北方"), meals = listOf("lunch", "dinner"), method = "炸", ingredients = listOf("猪肉")),
        LifeItem(name = "西红柿鸡蛋面", since = 1900, until = null, regions = listOf("北方", "通用"), meals = listOf("breakfast", "lunch", "night"), method = "煮", ingredients = listOf("番茄", "鸡蛋", "面")),
        LifeItem(name = "兰州牛肉面", since = 1915, until = null, regions = listOf("西北"), meals = listOf("breakfast", "lunch", "night"), method = "煮", ingredients = listOf("牛肉", "面")),
        LifeItem(name = "豆浆油条", since = 1900, until = null, regions = listOf("北方", "通用"), meals = listOf("breakfast"), method = "炸", ingredients = listOf("黄豆", "面")),
        LifeItem(name = "红烧带鱼", since = 1950, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "炖", ingredients = listOf("带鱼")),
        LifeItem(name = "醋溜土豆丝", since = 1950, until = null, regions = listOf("北方", "通用"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("土豆", "醋")),
        LifeItem(name = "西红柿炒菜花", since = 1980, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "炒", ingredients = listOf("番茄", "菜花")),
        LifeItem(name = "方便面加蛋", since = 1970, until = null, regions = listOf("通用"), meals = listOf("lunch", "night"), method = "煮", ingredients = listOf("面", "鸡蛋")),
        LifeItem(name = "烤串", since = 1980, until = null, regions = listOf("北方", "川渝", "通用"), meals = listOf("night"), method = "烤", ingredients = listOf("羊肉", "孜然")),
        LifeItem(name = "烤翅", since = 2000, until = null, regions = listOf("通用"), meals = listOf("lunch", "night"), method = "烤", ingredients = listOf("鸡翅")),
        LifeItem(name = "沙拉", since = 2000, until = null, regions = listOf("通用"), meals = listOf("breakfast", "lunch"), method = "拌", ingredients = listOf("生菜", "番茄")),
        LifeItem(name = "空气炸鸡块", since = 2015, until = null, regions = listOf("通用"), meals = listOf("lunch", "night"), method = "炸", ingredients = listOf("鸡")),
    )

    val DRINKS: List<LifeItem> = listOf(
        LifeItem(name = "凉水", since = -8000, until = null, regions = listOf("通用"), meals = listOf("breakfast", "lunch", "dinner", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "米汤", since = -6000, until = null, regions = listOf("通用"), meals = listOf("breakfast", "lunch"), method = "", ingredients = emptyList()),
        LifeItem(name = "茶", since = -100, until = null, regions = listOf("通用"), meals = listOf("breakfast", "lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "豆浆", since = 100, until = null, regions = listOf("通用"), meals = listOf("breakfast"), method = "", ingredients = emptyList()),
        LifeItem(name = "酸梅汤", since = 1000, until = null, regions = listOf("北方", "通用"), meals = listOf("lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "黄酒", since = -200, until = null, regions = listOf("江南"), meals = listOf("dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "汽水", since = 1900, until = null, regions = listOf("通用"), meals = listOf("lunch", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "啤酒", since = 1900, until = null, regions = listOf("通用"), meals = listOf("night", "dinner"), method = "", ingredients = emptyList()),
        LifeItem(name = "可乐", since = 1980, until = null, regions = listOf("通用"), meals = listOf("lunch", "night"), method = "", ingredients = emptyList()),
        LifeItem(name = "奶茶", since = 2000, until = null, regions = listOf("通用"), meals = listOf("lunch"), method = "", ingredients = emptyList()),
        LifeItem(name = "咖啡", since = 1900, until = null, regions = listOf("通用"), meals = listOf("breakfast", "lunch"), method = "", ingredients = emptyList()),
    )

    /** 时段（给模型一个「现在该干什么」的常识锚）。 */
    val PHASES: List<Pair<Int, String>> = listOf(4 to "深夜", 9 to "清晨", 11 to "上午", 13 to "中午", 17 to "午后", 19 to "傍晚", 23 to "夜里", 24 to "深夜")
    const val LIFE_DAY_START_HOUR: Int = 4
    /** (key, 名字, 饭点开始小时) */
    val MEALS: List<Triple<String, String, Double>> = listOf(Triple("breakfast", "早饭", 6.5), Triple("lunch", "午饭", 11.5), Triple("dinner", "晚饭", 17.5), Triple("night", "夜宵", 21.5))
    val MEAL_LABELS: List<Pair<String, String>> = listOf("breakfast" to "早饭", "lunch" to "午饭", "dinner" to "晚饭", "night" to "夜宵")
    val REGIONS: List<String> = listOf("auto", "北方", "江南", "川渝", "粤", "西北")
    val DEFAULTS: LifeConfig = LifeConfig(enabled = true, era = "auto", region = "auto", taste = "", avoid = "", showMeals = true, maxChars = 240, location = "家")
}

/** 年代 → 地点 / 交通 / 屋里（来自 commonsense.py）。 */
object CommonsenseTables {

    val ERAS: Map<String, CsEra> = linkedMapOf(
        "史前" to CsEra(places = listOf(CsPlace("洞窟", 0.0), CsPlace("营地", 2.0), CsPlace("溪边", 5.0), CsPlace("林子", 12.0), CsPlace("石场", 20.0), CsPlace("别的部落", 90.0)), transports = linkedMapOf("步行" to 1.0, "小跑" to 0.6, "独木舟" to 0.5), rooms = listOf("洞窟内", "火塘边", "睡铺"), notes = "没有路，只有兽径；「出远门」= 走上一天"),
        "新石器" to CsEra(places = listOf(CsPlace("自家土屋", 0.0), CsPlace("村口", 3.0), CsPlace("水井", 5.0), CsPlace("田地", 15.0), CsPlace("集市", 25.0), CsPlace("邻村", 60.0)), transports = linkedMapOf("步行" to 1.0, "小跑" to 0.65, "牛车" to 0.5, "独木舟" to 0.5), rooms = listOf("堂屋", "灶间", "睡房", "院子", "柴棚"), notes = "村落尺度；出远门靠走或牛车"),
        "先秦汉" to CsEra(places = listOf(CsPlace("自家宅院", 0.0), CsPlace("里巷口", 3.0), CsPlace("水井", 5.0), CsPlace("市集", 20.0), CsPlace("官署", 30.0), CsPlace("祠庙", 25.0), CsPlace("渡口", 35.0), CsPlace("田埂", 40.0), CsPlace("邻县", 240.0)), transports = linkedMapOf("步行" to 1.0, "快走" to 0.75, "牛车" to 0.5, "马车" to 0.35, "骑马" to 0.25, "渡船" to 0.4), rooms = listOf("正房", "厢房", "灶房", "院子", "柴房", "马厩"), notes = "里坊制，夜里可能宵禁；远行要带干粮"),
        "唐宋" to CsEra(places = listOf(CsPlace("自家宅院", 0.0), CsPlace("巷口", 3.0), CsPlace("茶肆", 10.0), CsPlace("坊市", 20.0), CsPlace("衙门", 30.0), CsPlace("寺庙", 30.0), CsPlace("书院", 35.0), CsPlace("码头", 40.0), CsPlace("瓦舍", 35.0), CsPlace("州城", 300.0)), transports = linkedMapOf("步行" to 1.0, "快走" to 0.75, "轿子" to 0.45, "马车" to 0.35, "骑马" to 0.25, "渡船" to 0.4), rooms = listOf("正房", "厢房", "灶房", "堂屋", "院子", "书房", "柴房"), notes = "坊市有营业时辰；文人常去茶肆书院，夜里坊门会关"),
        "明清" to CsEra(places = listOf(CsPlace("自家宅院", 0.0), CsPlace("巷口", 3.0), CsPlace("茶馆", 12.0), CsPlace("集市", 20.0), CsPlace("县衙", 30.0), CsPlace("当铺", 25.0), CsPlace("庙会", 35.0), CsPlace("码头", 40.0), CsPlace("书院", 35.0), CsPlace("府城", 360.0)), transports = linkedMapOf("步行" to 1.0, "快走" to 0.75, "轿子" to 0.45, "马车" to 0.35, "骑马" to 0.25, "渡船" to 0.4), rooms = listOf("正房", "厢房", "灶房", "堂屋", "院子", "书房", "柴房", "绣楼"), notes = "辣椒番茄明末才传入 —— 与 life_core 的年代食材表同源"),
        "民国" to CsEra(places = listOf(CsPlace("自家住处", 0.0), CsPlace("弄堂口", 2.0), CsPlace("老虎灶", 6.0), CsPlace("街市", 15.0), CsPlace("警察局", 30.0), CsPlace("报馆", 35.0), CsPlace("电影院", 30.0), CsPlace("码头", 45.0), CsPlace("教堂", 30.0), CsPlace("省城", 300.0)), transports = linkedMapOf("步行" to 1.0, "黄包车" to 0.3, "电车" to 0.2, "渡船" to 0.4, "汽车" to 0.25, "火车" to 0.15), rooms = listOf("前厅", "卧房", "灶披间", "天井", "亭子间"), notes = "黄包车与电车并存；报纸、电影院开始进日常"),
        "1950s" to CsEra(places = listOf(CsPlace("自家", 0.0), CsPlace("院门口", 2.0), CsPlace("供销社", 12.0), CsPlace("邮电局", 25.0), CsPlace("粮站", 20.0), CsPlace("卫生所", 25.0), CsPlace("大食堂", 8.0), CsPlace("公社", 40.0), CsPlace("县城", 200.0)), transports = linkedMapOf("步行" to 1.0, "自行车" to 0.35, "公共汽车" to 0.4, "火车" to 0.15), rooms = listOf("里屋", "外屋", "厨房", "院子", "储藏间"), notes = "票证时代，买东西要票；大食堂是集体吃饭的地方"),
        "1980s" to CsEra(places = listOf(CsPlace("自家", 0.0), CsPlace("楼下", 2.0), CsPlace("国营商店", 12.0), CsPlace("菜场", 10.0), CsPlace("邮电局", 20.0), CsPlace("电影院", 25.0), CsPlace("录像厅", 25.0), CsPlace("厂区", 35.0), CsPlace("火车站", 45.0)), transports = linkedMapOf("步行" to 1.0, "自行车" to 0.35, "公交" to 0.5, "火车" to 0.15), rooms = listOf("里屋", "外屋", "厨房", "阳台", "储藏间"), notes = "自行车是主力；录像厅、厂区是这一代的社交场"),
        "2000s" to CsEra(places = listOf(CsPlace("自家", 0.0), CsPlace("楼下", 2.0), CsPlace("便利店", 6.0), CsPlace("网吧", 15.0), CsPlace("书店", 20.0), CsPlace("公交站", 8.0), CsPlace("公园", 15.0), CsPlace("医院", 20.0), CsPlace("学校", 25.0), CsPlace("火车站", 40.0)), transports = linkedMapOf("走路" to 1.0, "骑车" to 0.4, "公交" to 0.5, "出租车" to 0.35, "火车" to 0.15), rooms = listOf("卧室", "客厅", "厨房", "卫生间", "阳台"), notes = "网吧与公交卡的时代"),
        "现代" to CsEra(places = listOf(CsPlace("家", 0.0), CsPlace("楼下", 2.0), CsPlace("小区门口", 3.0), CsPlace("便利店", 6.0), CsPlace("公交站", 8.0), CsPlace("菜市场", 10.0), CsPlace("超市", 12.0), CsPlace("公园", 15.0), CsPlace("餐厅", 15.0), CsPlace("咖啡馆", 18.0), CsPlace("医院", 20.0), CsPlace("学校", 25.0), CsPlace("朋友家", 25.0), CsPlace("电影院", 30.0), CsPlace("公司", 35.0), CsPlace("火车站", 40.0), CsPlace("邻近城市", 180.0), CsPlace("远方（省外）", 600.0)), transports = linkedMapOf("走路" to 1.0, "步行" to 1.0, "骑车" to 0.4, "公交" to 0.5, "地铁" to 0.45, "打车" to 0.35, "开车" to 0.3, "高铁" to 0.06, "飞机" to 0.05), rooms = listOf("卧室", "客厅", "厨房", "卫生间", "阳台", "书房", "玄关"), notes = "默认口径（地铁/打车/外卖）"),
        "仙侠" to CsEra(places = listOf(CsPlace("洞府", 0.0), CsPlace("山门", 15.0), CsPlace("练功场", 10.0), CsPlace("膳堂", 8.0), CsPlace("藏经阁", 25.0), CsPlace("坊市", 60.0), CsPlace("秘境入口", 180.0), CsPlace("宗门大殿", 30.0)), transports = linkedMapOf("步行" to 1.0, "轻功" to 0.4, "御剑" to 0.08, "传送阵" to 0.05), rooms = listOf("静室", "丹房", "卧房", "院子", "灵田"), notes = "御剑/传送阵让「远」变近 —— 但要有修为设定撑住"),
        "末世" to CsEra(places = listOf(CsPlace("据点", 0.0), CsPlace("楼下废墟", 5.0), CsPlace("补给点", 30.0), CsPlace("加油站", 45.0), CsPlace("避难所", 120.0), CsPlace("辐射区", 200.0), CsPlace("别的据点", 300.0)), transports = linkedMapOf("步行" to 1.0, "小跑" to 0.7, "自行车" to 0.4, "改装车" to 0.25), rooms = listOf("睡铺", "库房", "灶间", "瞭望位"), notes = "路断了、油要省；弹药与净水是硬通货"),
    )
    const val DEFAULT_ERA: String = "现代"
    val KINDS: List<String> = listOf("仙侠", "末世")
}

/** 交通系数与默认值（来自 space_core.py；交通**以年代表为准**，这里只是认不出名字时的兜底）。 */
object SpaceTables {

    const val HUB: String = "家"
    const val DEFAULT_TRANSPORT: String = "走路"
    const val DEFAULT_ERA_FALLBACK: String = "现代"
    const val MAX_MINUTES: Double = 43200.0
    const val ROOM_MINUTES: Double = 0.5
    /** 跨年代通用写法（打车/高铁…）：只当系数兜底，不并进地图。 */
    val TRANSPORT: Map<String, Double> = linkedMapOf("走路" to 1.0, "步行" to 1.0, "骑车" to 0.4, "自行车" to 0.4, "公交" to 0.5, "地铁" to 0.45, "打车" to 0.35, "开车" to 0.3, "自驾" to 0.3, "高铁" to 0.06, "飞机" to 0.05)
    val DEFAULTS: SpaceConfig = SpaceConfig(enabled = true, maxChars = 240, showReachable = true, reachableLimit = 4, defaultTransport = "走路", warnWhenImpossible = true, stateDir = "space")
}
