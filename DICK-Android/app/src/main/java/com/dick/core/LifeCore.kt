package com.dick.core

import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * LifeCore —— 生活层（吃饭）的手机端：世界时钟 + 厨具历史库 + 食材/做法库。
 *
 * 与 `life_core.py` 一一对应，连"随机"都对得上（见 `PyRandom`）：菜单是确定性抽样，
 * 种子 = `角色｜世界第几天｜哪一餐`，所以同一份存档在电脑和手机上算出的是**同一顿饭**。
 *
 * 三件事：
 *   ① 世界时钟：系统时间 = 1× 起源；`世界时刻 = 链首时刻 + Σ(现实间隔 × 倍率)`
 *   ② 厨具历史库：哪个年代有什么家伙 —— 它是**约束**（唐宋不该用微波炉）
 *   ③ 食材/做法库：按 年代 × 地域 × 口味 × 忌口 抽出一日三餐
 *
 * 每轮只注入一小段（默认 ≤240 字，按优先级裁）：现在几点、今天吃了什么、手边有什么、
 * 口味与忌口。库是检索源，不是注入内容 —— 整库喂进去会把模型带成机械报菜名。
 */
object LifeCore {

    const val GUIDE: String =
        "（生活细节自然带出即可，不必每轮都提吃的；饿了/累了在语气里体现，不要报数值。）"

    private const val FALLBACK_ERA = "现代"
    private val HHMM: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm")

    // ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
    //  一、配置（自己的文件，自己的缓存；字段名与 life_config.json 一致）
    // ============================================================
    @Volatile
    private var cache: LifeConfig? = null

    fun configPath(): File = File(AppEnv.dataRoot, "life_config.json")

    fun resetConfigCache() {
        cache = null
    }

    fun parseConfig(json: String?): LifeConfig {
        val o = try {
            if (json.isNullOrBlank()) null else JsonS.parse(json) as? J.Obj
        } catch (_: Exception) {
            null
        } ?: return LifeTables.DEFAULTS
        val d = LifeTables.DEFAULTS
        fun bool(key: String, def: Boolean) = (o.fields[key] as? J.Bool)?.v ?: def
        fun txt(key: String, def: String): String {
            val v = o.fields[key]
            return when (v) {
                is J.Str -> v.v
                is J.Arr -> v.items.joinToString(",") { (it as? J.Str)?.v ?: "" }
                is J.Num -> v.raw.ifEmpty { v.v.toString() }
                else -> def
            }
        }
        fun num(key: String, def: Int) = ((o.fields[key] as? J.Num)?.v ?: def.toDouble()).toInt()
        return LifeConfig(
            enabled = bool("enabled", d.enabled),
            era = txt("era", d.era).ifEmpty { d.era },
            region = txt("region", d.region).ifEmpty { d.region },
            taste = txt("taste", d.taste),
            avoid = txt("avoid", d.avoid),
            showMeals = bool("show_meals", d.showMeals),
            maxChars = num("max_chars", d.maxChars).let { if (it > 0) it else d.maxChars },
            location = txt("location", d.location),
        )
    }

    fun loadConfig(): LifeConfig {
        cache?.let { return it }
        val c = try {
            val f = configPath()
            if (f.isFile) parseConfig(f.readText(Charsets.UTF_8)) else LifeTables.DEFAULTS
        } catch (_: Exception) {
            LifeTables.DEFAULTS
        }
        cache = c
        return c
    }

    fun saveConfig(cfg: LifeConfig): LifeConfig {
        cache = cfg
        try {
            val f = configPath()
            f.parentFile?.mkdirs()
            val tmp = File(f.parentFile, f.name + ".tmp")
            tmp.writeText(toJson(cfg), Charsets.UTF_8)
            if (!tmp.renameTo(f)) {
                f.delete()
                tmp.renameTo(f)
            }
        } catch (e: Exception) {
            println("[life] 配置保存失败: " + e.message)
        }
        return cfg
    }

    /** 落盘格式与电脑端同一套键名（`show_meals` / `max_chars`…），两端能互读。 */
    fun toJson(cfg: LifeConfig): String {
        val o = J.Obj()
        o.fields["enabled"] = J.Bool(cfg.enabled)
        o.fields["era"] = J.Str(cfg.era)
        o.fields["region"] = J.Str(cfg.region)
        o.fields["taste"] = J.Str(cfg.taste)
        o.fields["avoid"] = J.Str(cfg.avoid)
        o.fields["show_meals"] = J.Bool(cfg.showMeals)
        o.fields["max_chars"] = J.Num(cfg.maxChars.toDouble(), cfg.maxChars.toString())
        o.fields["location"] = J.Str(cfg.location)
        return JsonS.stringify(o, pretty = true)
    }

    fun enabled(): Boolean = try {
        loadConfig().enabled
    } catch (_: Exception) {
        false
    }

    // ============================================================
    //  二、世界时钟（系统时间 = 1× 起源）
    // ============================================================
    fun scaleOf(scale: Double?): Double {
        var sc = scale ?: 1.0
        if (sc == 0.0) sc = 1.0
        if (sc.isNaN() || sc <= 0.0) sc = 1.0
        return sc
    }

    /** 那边现在几点。链里没有可用时间戳就返回 null（不注入，也不猜）。 */
    fun worldClock(nodes: List<MessageNode>, scale: Double? = null,
                   now: LocalDateTime = LocalDateTime.now()): WorldClock? {
        val sc = scaleOf(scale)
        val stamps = ArrayList<LocalDateTime>()
        for (n in nodes) {
            if (n.role == "system") continue
            parseLocal(n.timestamp)?.let { stamps.add(it) }
        }
        if (stamps.isEmpty()) return null
        val origin = stamps[0]
        var elapsed = 0.0
        for (i in 1 until stamps.size) {
            val gap = ChronoUnit.SECONDS.between(stamps[i - 1], stamps[i]).toDouble()
            elapsed += max(0.0, gap)                 // 时钟回拨/脏数据当 0，不让世界倒退
        }
        elapsed += max(0.0, ChronoUnit.SECONDS.between(stamps.last(), now).toDouble())
        val worldSec = elapsed * sc
        val world = origin.plusNanos((worldSec * 1_000_000_000.0).toLong())
        val lifeDay: LocalDate = world.minusHours(LifeTables.LIFE_DAY_START_HOUR.toLong()).toLocalDate()
        val originLifeDay: LocalDate =
            origin.minusHours(LifeTables.LIFE_DAY_START_HOUR.toLong()).toLocalDate()
        return WorldClock(
            originIso = origin.toString(),
            worldIso = world.toString(),
            day = (ChronoUnit.DAYS.between(originLifeDay, lifeDay) + 1).toInt(),
            // Python 用的是 date.toordinal()（0001-01-01 = 1）—— 种子字符串里就是它，不能换算法
            lifeDayOrdinal = lifeDay.toEpochDay() + 719163L,
            hhmm = world.format(HHMM),
            phase = phaseOf(world.hour),
            elapsedReal = elapsed,
            elapsedWorld = worldSec,
            mealsToday = mealsPassed(world),
        )
    }

    /** 时段：给模型一个「现在该干什么」的常识锚。 */
    fun phaseOf(hour: Int): String {
        val h = ((hour % 24) + 24) % 24
        for ((end, name) in LifeTables.PHASES) if (h < end) return name
        return "深夜"
    }

    /** 这一天已经过了哪些饭点（按饭点**开始时刻**判，不看窗口结束）。 */
    fun mealsPassed(worldDt: LocalDateTime): List<Pair<String, String>> {
        val out = ArrayList<Pair<String, String>>()
        val minutes = worldDt.hour * 60 + worldDt.minute
        for ((key, label, startHour) in LifeTables.MEALS) {
            if (minutes >= (startHour * 60).toInt()) out.add(key to label)
        }
        return out
    }

    // ============================================================
    //  三、资料过滤：年代 / 地域 / 忌口 / 厨具
    // ============================================================
    fun toolsFor(eraKey: String): List<String> {
        val e = LifeTables.ERA_BY_KEY[eraKey] ?: LifeTables.ERA_BY_KEY[FALLBACK_ERA]
        return e?.tools ?: emptyList()
    }

    fun eraOf(eraKey: String): LifeEra? = LifeTables.ERA_BY_KEY[eraKey] ?: LifeTables.ERA_BY_KEY[FALLBACK_ERA]

    /** 厨具历史库的用处：这个年代有没有做这道菜的家伙。 */
    fun methodOk(method: String, tools: List<String>, eraYear: Int): Boolean {
        val since = LifeTables.METHOD_SINCE[method] ?: -100000
        if (eraYear < since) return false
        val needs = LifeTables.METHOD_NEEDS[method] ?: emptyList()
        if (needs.isEmpty()) return true
        val blob = tools.joinToString("")
        return needs.any { blob.contains(it) }
    }

    private fun sinceOk(since: Int, eraYear: Int): Boolean = since <= eraYear

    private fun untilOk(until: Int?, eraYear: Int): Boolean = until == null || eraYear <= until

    private fun regionOk(regions: List<String>, region: String): Boolean {
        if (region.isEmpty() || region == "auto") return true
        return regions.contains("通用") || regions.contains(region)
    }

    private fun mealOk(meals: List<String>, mealKey: String): Boolean =
        meals.isEmpty() || meals.contains(mealKey)

    private fun avoidHit(name: String, ingredients: List<String>, avoid: List<String>): Boolean {
        for (bad in avoid) {
            if (bad.isEmpty()) continue
            if (name.contains(bad)) return true
            for (ing in ingredients) if (ing.contains(bad)) return true
        }
        return false
    }

    /**
     * 从世界卡认年代；认不出就现代（不猜错比猜洋气重要）。
     *
     * 顺序：卡里**显式写**的 `params.era` / `params.era_kind` 最优先（世界卡包就靠这个），
     * 其次才按关键词猜 —— 显式写的东西不该被关键词盖掉。
     */
    fun detectEra(worldJson: String?): String {
        val raw = worldJson?.trim() ?: ""
        var text = ""
        val parsed: J? = if (raw.isEmpty()) null else try {
            JsonS.parse(raw)
        } catch (_: Exception) {
            null
        }
        when (parsed) {
            is J.Obj -> {
                val params = parsed.fields["params"] as? J.Obj
                if (params != null) {
                    val explicit = strOf(params.fields["era_kind"]).ifEmpty { strOf(params.fields["era"]) }.trim()
                    if (LifeTables.ERA_BY_KEY.containsKey(explicit)) return explicit
                    if (explicit.isNotEmpty()) text += explicit
                    text += params.fields.values.joinToString(" ") { scalar(it) }
                }
                for (k in listOf("name", "description", "rules")) {
                    val v = parsed.fields[k]
                    if (v is J.Str) text += v.v
                }
            }
            is J.Str -> text = parsed.v
            else -> text = raw
        }
        for ((key, hints) in LifeTables.ERA_HINTS) {
            for (h in hints) if (text.contains(h)) return key
        }
        return FALLBACK_ERA
    }

    private fun strOf(v: J?): String = (v as? J.Str)?.v ?: ""

    /** Python 的 `str(v)`（只用于拼关键词文本）。 */
    private fun scalar(v: J): String = when (v) {
        is J.Str -> v.v
        is J.Num -> v.raw.ifEmpty { v.v.toString() }
        is J.Bool -> v.v.toString()
        else -> JsonS.stringify(v)
    }

    private fun objOf(json: String?): J.Obj? {
        val t = json?.trim()
        if (t.isNullOrEmpty() || t == "null") return null
        return try {
            JsonS.parse(t) as? J.Obj
        } catch (_: Exception) {
            null
        }
    }

    private fun asList(v: J?): List<String> {
        when (v) {
            is J.Arr -> return v.items.map { scalar(it).trim() }.filter { it.isNotEmpty() }
            is J.Str -> {
                var s = v.v
                for (sep in listOf("，", ",", "、", ";", "；", " ")) s = s.replace(sep, "|")
                return s.split("|").map { it.trim() }.filter { it.isNotEmpty() }
            }
            else -> return emptyList()
        }
    }

    /**
     * 角色卡 `advanced.life` 优先 > 全局配置 > 默认；年代能 auto 认出来。
     *
     * 带 `*From` 字段说明这份设置是哪来的 —— 命令面板上要讲清楚，
     * 否则会出现"我在设置里改了年代怎么没生效"（角色卡把它盖掉了）。
     */
    fun profileFor(roleJson: String? = null, cfg: LifeConfig = loadConfig(),
                   worldJson: String? = null): LifeProfile {
        val role = objOf(roleJson)
        val adv = role?.fields?.get("advanced") as? J.Obj
        val life = adv?.fields?.get("life") as? J.Obj
        fun lifeStr(key: String): String = strOf(life?.fields?.get(key))
        val roleName = strOf(role?.fields?.get("name")).ifEmpty { "她" }

        var era = lifeStr("era").ifEmpty { cfg.era }.ifEmpty { "auto" }
        var eraFrom = when {
            lifeStr("era").isNotEmpty() -> "角色卡"
            cfg.era.isNotEmpty() && cfg.era != "auto" -> "全局"
            else -> "自动"
        }
        if (era == "auto" || !LifeTables.ERA_BY_KEY.containsKey(era)) {
            era = detectEra(worldJson)
            if (eraFrom != "角色卡") eraFrom = "自动认出"
        }
        var region = lifeStr("region").ifEmpty { cfg.region }.ifEmpty { "auto" }
        val regionFrom = if (lifeStr("region").isNotEmpty()) "角色卡" else "全局"
        if (!LifeTables.REGIONS.contains(region)) region = "auto"
        val avoid = asList(life?.fields?.get("avoid")).ifEmpty { asList(J.Str(cfg.avoid)) }
        val era0 = eraOf(era)
        return LifeProfile(
            role = roleName,
            era = era,
            eraFrom = eraFrom,
            eraYear = era0?.year ?: 2025,
            tools = era0?.tools ?: emptyList(),
            region = region,
            regionFrom = regionFrom,
            taste = lifeStr("taste").ifEmpty { cfg.taste },
            avoid = avoid,
            skill = lifeStr("skill"),
            location = lifeStr("location").ifEmpty { cfg.location }.ifEmpty { "家" },
            showMeals = cfg.showMeals,
            maxChars = if (cfg.maxChars > 0) cfg.maxChars else 240,
        )
    }

    // ============================================================
    //  四、确定性抽样：同一角色同一天同一餐，永远同一份菜单
    // ============================================================
    /** 口味只是加权，不硬过滤 —— 清淡的人偶尔也想吃顿重口的。 */
    private fun tasteBias(name: String, taste: String): Double {
        if (taste.isEmpty()) return 1.0
        val light = listOf("清淡", "素", "少油", "养生")
        val heavy = listOf("重口", "嗜辣", "无辣不欢", "重油")
        val mild = listOf("炖", "煮", "蒸", "拌")
        val strong = listOf("炒", "炸", "烤")
        for (w in light) if (taste.contains(w)) {
            return if (mild.contains(name)) 2.5 else if (strong.contains(name)) 0.4 else 1.0
        }
        for (w in heavy) if (taste.contains(w)) {
            return if (strong.contains(name)) 2.5 else if (mild.contains(name)) 0.5 else 1.0
        }
        return 1.0
    }

    /** 按口味权重抽一个做法（权重放大成整数，避免浮点误差）。 */
    private fun weighted(rng: PyRandom, names: List<String>, taste: String): String? {
        val pool = ArrayList<String>()
        for (n in names) {
            val w = max(1, tasteBias(n, taste).times(10).roundToInt())
            repeat(w) { pool.add(n) }
        }
        return rng.pick(pool)
    }

    /**
     * 一餐 = 主食 + 1~2 个菜 + 一杯喝的。
     *
     * 过滤链：年代窗口 → 地域 → 忌口 → 餐次 → 厨具 → 当天去重。
     * 种子 = `角色|世界第几天|哪一餐`，与电脑端逐位一致（`PyRandom`）。
     */
    fun sampleMeal(profile: LifeProfile, lifeDay: Int, mealKey: String, mealLabel: String,
                   used: Set<String> = emptySet()): Meal {
        val eraYear = profile.eraYear
        val tools = profile.tools
        val region = profile.region
        val avoid = profile.avoid

        fun ok(item: LifeItem): Boolean =
            sinceOk(item.since, eraYear) && untilOk(item.until, eraYear) &&
                    regionOk(item.regions, region) && mealOk(item.meals, mealKey) &&
                    !avoidHit(item.name, item.ingredients, avoid)

        val staples = LifeTables.STAPLES.filter { ok(it) }
        val dishes = LifeTables.DISHES.filter { ok(it) && methodOk(it.method, tools, eraYear) }
        val drinks = LifeTables.DRINKS.filter { ok(it) }

        val freshStaples = staples.filter { !used.contains(it.name) }.ifEmpty { staples }
        val freshDishes = dishes.filter { !used.contains(it.name) }.ifEmpty { dishes }

        val rng = PyRandom.fromString(profile.role + "|" + lifeDay + "|" + mealKey)
        val staple = rng.pick(freshStaples)
        val picked = ArrayList<LifeItem>()
        if (freshDishes.isNotEmpty()) {
            val methods = freshDishes.map { it.method }.distinct().sorted()
            val method = weighted(rng, methods, profile.taste)
            val same = freshDishes.filter { it.method == method }
            val first: LifeItem? = if (same.isNotEmpty()) rng.pick(same) else rng.pick(freshDishes)
            if (first != null) picked.add(first)
            val rest = freshDishes.filter { it !== first }
            if (rest.isNotEmpty() && rng.nextDouble() < 0.55) rng.pick(rest)?.let { picked.add(it) }
        }
        val freshDrinks = drinks.filter { !used.contains(it.name) }.ifEmpty { drinks }
        val drink = if (rng.nextDouble() < 0.5) rng.pick(freshDrinks) else null

        val parts = ArrayList<String>()
        staple?.let { parts.add(it.name) }
        picked.forEach { parts.add(it.name) }
        val usedHere = ArrayList<String>()
        staple?.let { usedHere.add(it.name) }
        picked.forEach { usedHere.add(it.name) }
        drink?.let { usedHere.add(it.name) }
        return Meal(
            meal = mealLabel,
            key = mealKey,
            dish = if (parts.isNotEmpty()) parts.joinToString(" + ") else "随便对付一口",
            staple = staple?.name ?: "",
            dishes = picked.map { it.name },
            methods = picked.map { it.method },
            drink = drink?.name ?: "",
            tools = tools,
            used = usedHere,
        )
    }

    /** 这一天已经过了的饭点各吃什么（确定性；同一天里尽量不重样）。 */
    fun dayMenu(profile: LifeProfile, lifeDay: Int,
                meals: List<Pair<String, String>>): List<Meal> {
        val out = ArrayList<Meal>()
        val used = HashSet<String>()
        for ((key, label) in meals) {
            val m = sampleMeal(profile, lifeDay, key, label, used)
            used.addAll(m.used)
            out.add(m)
        }
        return out
    }

    // ============================================================
    //  五、给模型的那一小段（严格限长）
    // ============================================================
    /**
     * 每轮注入的【生活·那边】。没有可用时间戳 / 关掉了 / 算不出，都返回 ""。
     *
     * 长度按**优先级**吃预算：时间 → 今天吃了什么 → 忌口 → 家伙 → 口味 → 在哪儿。
     * 截断了至少还是"那边几点、她今天吃了什么"。
     */
    fun injectionText(nodes: List<MessageNode> = emptyList(), scale: Double? = null,
                      roleJson: String? = null, worldJson: String? = null,
                      cfg: LifeConfig? = null,
                      now: LocalDateTime = LocalDateTime.now()): String {
        val c = cfg ?: loadConfig()
        if (!c.enabled) return ""
        val clock = worldClock(nodes, scale, now) ?: return ""
        val profile = profileFor(roleJson, c, worldJson)
        val menu = if (profile.showMeals)
            dayMenu(profile, clock.lifeDayOrdinal.toInt(), clock.mealsToday) else emptyList()

        // 第几天只在开局头几天有意义：720× 下现实 2 分钟 = 那边 1 天，
        // 报"第 21 天"对模型没用，反而会把"过了多久"说乱（那件事时间层已经在做）。
        val dayTxt = if (clock.day <= 3) "第 " + clock.day + " 天 " else ""
        var head = "【生活·那边】" + dayTxt + clock.hhmm + "（" + clock.phase + "）"
        if (clock.phase == "深夜") head += "｜夜已深，她该睡了（若还醒着，给个合理的由头）"

        val items = ArrayList<Pair<String, Boolean>>()
        if (menu.isNotEmpty()) {
            items.add(("今天： " + menu.joinToString("｜") { m ->
                m.meal + " " + m.dish + (if (m.drink.isNotEmpty()) "，" + m.drink else "")
            }) to true)
        }
        if (profile.avoid.isNotEmpty()) items.add(("不吃" + profile.avoid.joinToString("、")) to true)
        items.add(("手边家伙：" + profile.tools.take(6).joinToString("、")) to false)
        if (profile.taste.isNotEmpty()) items.add(("口味" + profile.taste) to false)
        if (profile.location.isNotEmpty()) items.add(("在" + profile.location) to false)

        val room = max(60, profile.maxChars - head.length - GUIDE.length - 2)
        val kept = ArrayList<String>()
        for ((text, must) in items) {
            val piece = text + (if (kept.isNotEmpty() || must) "。" else "")
            if (kept.isNotEmpty() && kept.joinToString("").length + piece.length > room && !must) continue
            kept.add(piece)
        }
        val tail = kept.joinToString("")
        val out = head + (if (tail.isNotEmpty()) "\n" + tail else "")
        return out + "\n" + GUIDE
    }

    /**
     * Python `"%.4g"` 的等价物：Java 的 `%g` 会留一堆尾零（1.0 → "1.000"，Python 给 "1"），
     * 而这句话是要给人看的（`/生活` 面板），照抄 Python 的输出更好读也更不容易对不上。
     */
    private fun g4(v: Double): String {
        var s = String.format(Locale.ROOT, "%.4g", v)
        if (s.contains('.') && !s.contains('e') && !s.contains('E')) {
            s = s.trimEnd('0').trimEnd('.')
        }
        return s
    }

    /** 给 `/生活` 命令看的完整状态（比注入详细）。 */    fun describe(nodes: List<MessageNode> = emptyList(), scale: Double? = null,
                 roleJson: String? = null, worldJson: String? = null,
                 cfg: LifeConfig? = null,
                 now: LocalDateTime = LocalDateTime.now()): String {
        val c = cfg ?: loadConfig()
        val clock = worldClock(nodes, scale, now)
        val profile = profileFor(roleJson, c, worldJson)
        val lines = ArrayList<String>()
        lines.add("生活层：" + (if (c.enabled) "开" else "关"))
        if (clock == null) {
            lines.add("世界时钟：算不出（这条链里没有节点时间戳 —— 新开一局、还没说过话就会这样）")
        } else {
            lines.add(String.format(Locale.ROOT,
                "世界时钟：第 %d 天 %s（%s）｜那边已过 %.1f 天（现实 %.1f 分钟 × %s 倍）",
                clock.day, clock.hhmm, clock.phase, clock.elapsedWorld / 86400.0,
                clock.elapsedReal / 60.0, g4(scale ?: 1.0)))
        }
        lines.add("年代：" + profile.era + "（来自" + profile.eraFrom + "）" +
                (eraOf(profile.era)?.note ?: ""))
        lines.add("手边家伙：" + profile.tools.joinToString("、"))
        if (profile.region != "auto") lines.add("地域：" + profile.region + "（来自" + profile.regionFrom + "）")
        if (profile.taste.isNotEmpty()) lines.add("口味：" + profile.taste)
        if (profile.avoid.isNotEmpty()) lines.add("忌口：" + profile.avoid.joinToString("、"))
        if (clock != null) {
            val menu = dayMenu(profile, clock.lifeDayOrdinal.toInt(), clock.mealsToday)
            if (menu.isNotEmpty()) {
                lines.add("今天吃过：")
                for (m in menu) {
                    lines.add("  " + m.meal + "：" + m.dish + (if (m.drink.isNotEmpty()) "｜" + m.drink else ""))
                }
            } else {
                lines.add("今天还没吃饭点（那边刚天亮）")
            }
        }
        return lines.joinToString("\n")
    }
}
