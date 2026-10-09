package com.dick.core

import java.io.File
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.Duration
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * SpaceCore —— 空间层（人不能瞬移）的手机端：`space_core.py` 的**逐条移植**。
 *
 * 为什么要有这一层
 * ----------------
 * 吃饭那层解决的是"她有日子"；这层解决的是"她不会瞬移"。没有空间约束时，上一轮她还在家，
 * 下一轮就能出现在外地 —— 不是模型笨，是**根本没人告诉它两地要多久**。
 *
 * 三件事：
 *   ① 地图：轮辐模型，家 = 圆心；`cost(家→X) = travel[X]`、`cost(A→B) = travel[A] + travel[B]`，
 *      精确两地耗时用 `links`（键 `"A|B"`）覆盖 —— 估得偏保守，比"随便给个相近值"安全。
 *   ② 位置：每轮把 `[loc:地名|骑车]` / `[ploc:地名]` 落成一个极小的状态文件
 *      （`space/<角色>.json`，字段名与电脑端完全一致，两端能互读）。
 *   ③ 判合理性：位置状态里存的是**现实时刻**，那边过了多少分钟 =（现在 − 到达时刻）× 倍率 / 60。
 *      这一跳要的时间 > 这段时间 → 记下新位置（文本都写出来了，不逆转），
 *      但下一轮注入里点名，最多念两次。
 *
 * 表从哪来：年代 → 地点/交通/屋里 由 `Commonsense`（`commonsense.py` 生成）给，
 * 交通系数只有一份真相（`Tables.kt` 由 `tools/gen_parity.py` 生成）。
 *
 * 故意照抄的电脑端口径（别"顺手修好"，两端要一模一样）
 * ------------------------------------------------
 *   · `travelMinutes` 的轮辐捷径比的是**字面量 `家`**，不是 `map.home` —— 卡把家改名成"宿舍"时
 *     仍然按 `家` 判（电脑端就是如此；改了两端就会算出不同的路费）。
 *   · `parseMove` 的交通方式**只认竖线** `|` / `｜`：斜线留给屋里路径（`[loc:家/厨房]`），
 *     逗号空格留给地名本身（"朝阳, 北京"）。
 *   · `openNow` 跨天营业：`start > end` 时按 `h >= start || h < end` 判（22:00–02:00）。
 *   · `reachable` 的 `limit` 为 0 / null = 不限条数；负数按 Python 的 `out[:n]` 切片（去掉末尾几项）。
 *   · `max_chars` 为 0 时按默认 240（电脑端 `cfg.get("max_chars") or 240`）。
 *   · `_scale`：显式传了非法值（0 / 负数 / NaN）→ 1.0，**不偷偷改用全局设置**。
 *
 * 与电脑端**有意不同**的地方（都写在这里，免得以后当成 bug 查）
 * ------------------------------------------------------
 *   · `scale == null` 时电脑端读 `time_scale.load()`（默认 720）。手机端的流速在
 *     `TimeScale.current` 里，但 selftest 的编译闭包不含 `TimeScale.kt`，所以这里留了一个钩子：
 *     接 UI 时写 `SpaceCore.scaleProvider = { TimeScale.current }`（生活层那边是调用方显式传的）。
 *     没人设、调用方也没传 → 按 1×（不加速），与 `LifeCore.scaleOf(null)` 口径一致。
 *   · 时间戳解析用契约里的 `parseLocal`（只认 ISO 本地时间）：电脑端 `datetime.fromisoformat`
 *     还认空格分隔、只有日期（当 0 点）、带时区偏移的写法；这里不认，认不出就当"没有时间戳"。
 *   · 配置里的值会按类型取（非布尔当默认），电脑端是 Python 的隐式真值（`"no"` 也算真）。
 *   · 状态文件里**认识的字段**才进 `SpaceState`；未知字段在改写时会保留（读写都走原始 JSON 对象），
 *     但用 `saveState(SpaceState)` 整体覆盖时会丢。落盘缩进 2 空格（电脑端 1 空格），解析无差别。
 *   · 整数浮点落盘：电脑端写 `1.0`，这里也按 `1.0` 写（`pyNum`），但 JSON 数字的极端写法
 *     （如 `1.0E10`）两端文本可能不同 —— 不影响解析。
 */
object SpaceCore {

    const val GUIDE: String =
        "（换地方要交代怎么去的、路上花了多久；来不及去的地方就别凭空出现 —— " +
                "可以用 [loc:地名] / [loc:地名|骑车] 标注她到了哪，[ploc:地名] 标你到哪；标注不会显示给玩家。）"

    // ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
    //  0. 小工具：跟 Python 的口径对齐（不然会差一个字）
    // ============================================================

    /**
     * 倍率来源：`scale == null` 时用它。
     *
     * 电脑端那一支读的是 `time_scale.load()`（默认 720×）。手机端接 UI 时设成
     * `{ TimeScale.current }` 就跟电脑端一模一样；没设就按 1×，不加速也不会算错方向。
     */
    @Volatile
    var scaleProvider: () -> Double = { 1.0 }

    private val ISO_SEC: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.ROOT)

    /** Python 的 `"%.0f"`：**round-half-even**（0.5 → 0、2.5 → 2）。Java 的 `%f` 是 HALF_UP，差一个字。 */
    private fun f0(v: Double): String {
        if (v.isNaN() || v.isInfinite()) return v.toString()
        return BigDecimal(v).setScale(0, RoundingMode.HALF_EVEN).toPlainString()
    }

    /** Python 的 `len()`：数的是**码点**；Kotlin 的 `length` 数 UTF-16 单元（地名里可能有 emoji）。 */
    private fun pyLen(s: String): Int = s.codePointCount(0, s.length)

    private fun pyTake(s: String, n: Int): String {
        if (n <= 0) return ""
        if (n >= pyLen(s)) return s
        return s.substring(0, s.offsetByCodePoints(0, n))
    }

    /** Python 的 `"%-6s"` / `"%5.0f"`（按码点数补空格，不按显示宽度）。 */
    private fun padEndTo(s: String, w: Int): String =
        if (pyLen(s) >= w) s else s + " ".repeat(w - pyLen(s))

    private fun padStartTo(s: String, w: Int): String =
        if (pyLen(s) >= w) s else " ".repeat(w - pyLen(s)) + s

    /** Python 的 `"%02d"`。 */
    private fun p2(v: Int): String = v.toString().padStart(2, '0')

    /** Python 的 `datetime.isoformat()`：秒永远有；微秒为 0 时不带小数部分。 */
    fun isoOf(dt: LocalDateTime): String {
        val head = ISO_SEC.format(dt)
        val micro = dt.nano / 1000
        return if (micro == 0) head else head + "." + micro.toString().padStart(6, '0')
    }

    /** Python 的 `str(v)`：只用来拼文本（None → "None"、true → "True"）。容器只能给个近似。 */
    private fun pyStr(v: J?): String = when (v) {
        null, is J.Null -> "None"
        is J.Str -> v.v
        is J.Num -> if (v.raw.isNotEmpty()) v.raw else v.v.toString()
        is J.Bool -> if (v.v) "True" else "False"
        else -> JsonS.stringify(v)
    }

    /** Python 的 `str(v)`，字段整个缺失时也是 `None`（`"%s" % d.get(k)` 就是这个结果）。 */
    private fun pyStrOrNone(v: J?): String = if (v == null) "None" else pyStr(v)

    /** 落盘时按 Python `json.dump` 的写法保留 `.0`（整数浮点不写成整数）。 */
    private fun pyNum(v: Double): J.Num {
        val raw = when {
            v.isNaN() -> "NaN"
            v == Double.POSITIVE_INFINITY -> "Infinity"
            v == Double.NEGATIVE_INFINITY -> "-Infinity"
            v == v.toLong().toDouble() && kotlin.math.abs(v) < 1e16 -> v.toLong().toString() + ".0"
            else -> v.toString()
        }
        return J.Num(v, raw)
    }

    /** Python 的真值判断（`if spec.get("merge")` / `if meta.get("room")` 这类）。 */
    private fun truthy(v: J?): Boolean = when (v) {
        null, is J.Null -> false
        is J.Bool -> v.v
        is J.Num -> v.v != 0.0
        is J.Str -> v.v.isNotEmpty()
        is J.Arr -> v.items.isNotEmpty()
        is J.Obj -> v.fields.isNotEmpty()
    }

    /** Python 的 `float(v)`：认不出就是 null（调用点据此决定"跳过还是当 0"）。 */
    private fun numOf(v: J?): Double? = when (v) {
        is J.Num -> v.v
        is J.Str -> v.v.trim().toDoubleOrNull()
        is J.Bool -> if (v.v) 1.0 else 0.0
        else -> null
    }

    /** Python 的 `int(v)`（宽松版：认不出给 0，不炸；电脑端会抛 ValueError）。 */
    private fun intOf(v: J?): Int = when (v) {
        is J.Num -> v.v.toInt()
        is J.Str -> v.v.trim().toDoubleOrNull()?.toInt() ?: 0
        is J.Bool -> if (v.v) 1 else 0
        else -> 0
    }

    private fun intOfLoose(v: J?): Int? = when (v) {
        is J.Num -> v.v.toInt()
        is J.Str -> v.v.trim().toDoubleOrNull()?.toInt()
        is J.Bool -> if (v.v) 1 else 0
        else -> null
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

    /**
     * 文件名消毒（电脑端 `_safe`）：`re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "default"`。
     * 角色名里的斜杠会让状态文件跑到别的目录去，必须挡掉。
     */
    fun safe(name: String?): String {
        val raw = if (name.isNullOrEmpty()) "default" else name
        return raw.replace(Regex("[\\\\/:*?\"<>|]"), "_").trim().ifEmpty { "default" }
    }

    // ============================================================
    //  一、配置（自己的文件、自己的缓存；字段名与 space_config.json 一致）
    // ============================================================
    @Volatile
    private var cache: SpaceConfig? = null

    fun configPath(): File = File(AppEnv.dataRoot, "space_config.json")

    fun resetConfigCache() {
        cache = null
    }

    fun parseConfig(json: String?): SpaceConfig {
        val o = objOf(json) ?: return SpaceTables.DEFAULTS
        val d = SpaceTables.DEFAULTS
        fun bool(key: String, def: Boolean) = (o.fields[key] as? J.Bool)?.v ?: def
        fun num(key: String, def: Int): Int = when (val v = o.fields[key]) {
            is J.Num -> v.v.toInt()
            is J.Str -> v.v.trim().toDoubleOrNull()?.toInt() ?: def
            is J.Bool -> if (v.v) 1 else 0
            else -> def
        }
        fun txt(key: String, def: String) = (o.fields[key] as? J.Str)?.v ?: def
        return SpaceConfig(
            enabled = bool("enabled", d.enabled),
            maxChars = num("max_chars", d.maxChars),
            showReachable = bool("show_reachable", d.showReachable),
            reachableLimit = num("reachable_limit", d.reachableLimit),
            defaultTransport = txt("default_transport", d.defaultTransport),
            warnWhenImpossible = bool("warn_when_impossible", d.warnWhenImpossible),
            stateDir = txt("state_dir", d.stateDir).ifEmpty { d.stateDir },
        )
    }

    fun loadConfig(): SpaceConfig {
        cache?.let { return it }
        val c = try {
            val f = configPath()
            if (f.isFile) parseConfig(f.readText(Charsets.UTF_8)) else SpaceTables.DEFAULTS
        } catch (_: Exception) {
            SpaceTables.DEFAULTS
        }
        cache = c
        return c
    }

    fun saveConfig(cfg: SpaceConfig): SpaceConfig {
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
            println("[space] 配置保存失败: " + e.message)
        }
        return cfg
    }

    fun toJson(cfg: SpaceConfig): String {
        val o = J.Obj()
        o.fields["enabled"] = J.Bool(cfg.enabled)
        o.fields["max_chars"] = J.Num(cfg.maxChars.toDouble(), cfg.maxChars.toString())
        o.fields["show_reachable"] = J.Bool(cfg.showReachable)
        o.fields["reachable_limit"] = J.Num(cfg.reachableLimit.toDouble(), cfg.reachableLimit.toString())
        o.fields["default_transport"] = J.Str(cfg.defaultTransport)
        o.fields["warn_when_impossible"] = J.Bool(cfg.warnWhenImpossible)
        o.fields["state_dir"] = J.Str(cfg.stateDir)
        return JsonS.stringify(o, pretty = true)
    }

    fun enabled(): Boolean = try {
        loadConfig().enabled
    } catch (_: Exception) {
        false
    }

    // ============================================================
    //  二、状态：她此刻在哪（一个角色一个文件，只记必要字段）
    // ============================================================
    fun statePath(role: String?, cfg: SpaceConfig? = null): File {
        val c = cfg ?: loadConfig()
        val dir = if (c.stateDir.isNotEmpty()) c.stateDir else "space"
        return File(File(AppEnv.dataRoot, dir), safe(role) + ".json")
    }

    /**
     * 读原始 JSON 对象（不是 `SpaceState`）。
     *
     * 为什么要留原始对象：电脑端的状态是个 dict —— `note_move` 会把新位置**并进**原 dict，
     * 里面本来有什么就留着什么（未来的字段、手动加的注记都不会被抹掉）。用 data class 覆盖写
     * 会把这些丢掉，所以写入路径一律走原始对象。
     */
    fun loadStateRaw(role: String?, cfg: SpaceConfig? = null): J.Obj {
        val f = statePath(role, cfg)
        return try {
            if (f.isFile) (JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj) ?: J.Obj() else J.Obj()
        } catch (_: Exception) {
            J.Obj()
        }
    }

    fun stateFrom(o: J.Obj): SpaceState {
        fun s(k: String): String = (o.fields[k] as? J.Str)?.v ?: ""
        val v = o.fields["violation"] as? J.Obj
        return SpaceState(
            place = s("place"),
            since = s("since"),
            prev = s("prev"),
            by = s("by"),
            scale = (o.fields["scale"] as? J.Num)?.v ?: 1.0,
            playerPlace = s("player_place"),
            playerSince = s("player_since"),
            playerPrev = s("player_prev"),
            offmap = s("offmap"),
            violation = if (v == null) null else Violation(
                from = (v.fields["from"] as? J.Str)?.v ?: "",
                to = (v.fields["to"] as? J.Str)?.v ?: "",
                need = (v.fields["need"] as? J.Num)?.v ?: 0.0,
                have = (v.fields["have"] as? J.Num)?.v,
                at = (v.fields["at"] as? J.Str)?.v ?: "",
                why = (v.fields["why"] as? J.Str)?.v ?: "",
                warned = intOf(v.fields["warned"]),
            ),
        )
    }

    /** `SpaceState` → JSON（只写非空字段，跟电脑端 dict 的"有什么写什么"对齐）。 */
    fun stateToJson(st: SpaceState): J.Obj {
        val o = J.Obj()
        if (st.place.isNotEmpty()) o.fields["place"] = J.Str(st.place)
        if (st.since.isNotEmpty()) o.fields["since"] = J.Str(st.since)
        if (st.prev.isNotEmpty()) o.fields["prev"] = J.Str(st.prev)
        if (st.by.isNotEmpty()) o.fields["by"] = J.Str(st.by)
        o.fields["scale"] = pyNum(st.scale)
        if (st.playerPlace.isNotEmpty()) o.fields["player_place"] = J.Str(st.playerPlace)
        if (st.playerSince.isNotEmpty()) o.fields["player_since"] = J.Str(st.playerSince)
        if (st.playerPrev.isNotEmpty()) o.fields["player_prev"] = J.Str(st.playerPrev)
        if (st.offmap.isNotEmpty()) o.fields["offmap"] = J.Str(st.offmap)
        val v = st.violation
        if (v != null) {
            val vo = J.Obj()
            vo.fields["from"] = J.Str(v.from)
            vo.fields["to"] = J.Str(v.to)
            vo.fields["need"] = pyNum(v.need)
            vo.fields["have"] = if (v.have == null) J.Null else pyNum(v.have)
            vo.fields["at"] = J.Str(v.at)
            vo.fields["why"] = J.Str(v.why)
            vo.fields["warned"] = J.Num(v.warned.toDouble(), v.warned.toString())
            o.fields["violation"] = vo
        }
        return o
    }

    fun loadState(role: String?, cfg: SpaceConfig? = null): SpaceState = stateFrom(loadStateRaw(role, cfg))

    /** 原子写：先写 `.tmp` 再改名（跟存档一个待遇，别写出半个 json）。 */
    fun saveStateRaw(role: String?, raw: J.Obj, cfg: SpaceConfig? = null): File {
        val p = statePath(role, cfg)
        try {
            p.parentFile?.mkdirs()
            val tmp = File(p.parentFile, p.name + ".tmp")
            tmp.writeText(JsonS.stringify(raw, pretty = true), Charsets.UTF_8)
            if (!tmp.renameTo(p)) {
                p.delete()
                tmp.renameTo(p)
            }
        } catch (e: Exception) {
            println("[space] 位置状态保存失败: " + e.message)
        }
        return p
    }

    fun saveState(role: String?, st: SpaceState, cfg: SpaceConfig? = null): File =
        saveStateRaw(role, stateToJson(st), cfg)

    // ============================================================
    //  三、时间：现实时刻 → 那边过了多少分钟（系统时间 = 1× 起源）
    // ============================================================
    /**
     * 倍率：null = 走 [scaleProvider]（电脑端读 time_scale）；显式给了但非法 → 当 1 倍。
     *
     * 为什么非法值不退回应用设置：调用方明确传了个坏值时，"不加速"比"偷偷用另一个来源的倍率"
     * 更容易解释 —— 否则测试与调用点都会意外受全局设置影响。
     */
    fun scaleOf(scale: Double?): Double {
        if (scale == null) {
            val v = try {
                scaleProvider()
            } catch (_: Exception) {
                1.0
            }
            return if (v.isNaN() || v <= 0.0) 1.0 else v
        }
        return if (scale.isNaN() || scale <= 0.0) 1.0 else scale
    }

    fun worldMinutesSince(ts: String?, scale: Double? = null, now: LocalDateTime? = null): Double? {
        val d = parseLocal(ts) ?: return null
        val end = now ?: LocalDateTime.now()
        val dur = Duration.between(d, end)
        val real = maxOf(0.0, dur.seconds.toDouble() + dur.nano / 1_000_000_000.0)
        return real * scaleOf(scale) / 60.0
    }

    private fun plusWorldMinutes(dt: LocalDateTime, minutes: Double): LocalDateTime {
        val sec = minutes * 60.0
        val whole = sec.toLong()
        return dt.plusSeconds(whole).plusNanos(((sec - whole) * 1_000_000_000.0).toLong())
    }

    /**
     * 上一轮对话到现在的世界分钟数（"下一幕之前她有多少时间可用"）。
     *
     * 与生活层的时间纸带同源：节点时间戳是系统本地时间，现实间隔 × 倍率 = 那边过了多久。
     * 没有链（开局第一轮）或链上没有可用时间戳 → null（那就退回"她在这个地方已经待了多久"）。
     */
    fun lastGapMinutes(chain: List<MessageNode>?, scale: Double? = null,
                       now: LocalDateTime? = null): Double? {
        if (chain.isNullOrEmpty()) return null
        var last: LocalDateTime? = null
        for (m in chain) {
            if (m.role == "system") continue
            val d = parseLocal(m.timestamp) ?: continue
            val prev = last
            if (prev == null || d.isAfter(prev)) last = d
        }
        val l = last ?: return null
        return worldMinutesSince(isoOf(l), scale, now)
    }

    // ============================================================
    //  四、地图：地点 / 路费 / 开门时间
    // ============================================================
    /**
     * 地图 = 年代常识（默认）+ 世界卡 `space` 覆盖 + 角色卡 `advanced.space` 覆盖。
     *
     * 年代：卡里显式写 `era` → 世界卡关键词（复用生活层的表）→ 现代；仙侠/末世这类
     * "设定类型"优先于年代（它们的地图差别更大）。
     *
     * 卡里的写法（`world.params.space` 或 `role.advanced.space`，两种等价）：
     * ```
     * {"places": [{"name": "学校", "minutes": 20},
     *             {"name": "码头", "minutes": 45, "open": [6, 20]}],
     *  "links":  {"学校|码头": 30},          // 精确两地耗时，覆盖估算
     *  "transport": {"骑车": 0.4},
     *  "rooms":  ["卧房", "灶房"],           // 只覆盖屋里格局也行
     *  "home":   "宿舍"}                     // 给"家"改个名字（圆心）
     * ```
     *
     * `cfg` 在电脑端也是收下不用的（签名对拍用），这里保持一致。
     */
    fun mapFor(roleJson: String? = null, worldJson: String? = null,
               @Suppress("UNUSED_PARAMETER") cfg: SpaceConfig? = null,
               era: String? = null): SpaceMap {
        val eraKey = if (era.isNullOrEmpty()) Commonsense.effectiveEra(worldJson, roleJson) else era

        val places = LinkedHashMap<String, SpacePlace>()
        val links = LinkedHashMap<String, Double>()
        val transport = LinkedHashMap<String, Double>()
        var home = SpaceTables.HUB

        // 交通方式以**年代**为准：唐宋不该有地铁/高铁。
        // 模块级的 TRANSPORT 只当"认不出名字时的通用系数"用（见 factor），不并进这张表。
        for ((k, v) in Commonsense.transports(eraKey)) transport[k] = v
        if (!transport.containsKey("走路")) transport["走路"] = 1.0
        if (!transport.containsKey("步行")) transport["步行"] = 1.0

        for (p in Commonsense.places(eraKey)) {
            places[p.name] = SpacePlace(name = p.name, minutes = p.minutes)
        }
        if (!places.containsKey(SpaceTables.HUB)) {
            places[SpaceTables.HUB] = SpacePlace(SpaceTables.HUB, 0.0)
        }
        places[SpaceTables.HUB] = places[SpaceTables.HUB]!!.copy(minutes = 0.0)
        // 屋里：都从家门口算（ROOM_MINUTES），并打上 room 标记 ——
        // 这样"够去哪"的列表不会被子分钟的卧室/厨房挤满（它们在屋里，本来就走得到）
        var rooms = Commonsense.rooms(eraKey).toMutableList()

        /**
         * 把卡里的 `space` 并进地图。
         *
         * `replace=true`（**世界卡默认**）：卡里给了 places/transport/rooms 就整张换掉年代默认 ——
         *   世界卡定义的是"一个设定"，不该被别的年代的地点混进来。想叠加就写 `"merge": true`。
         * `replace=false`（**角色卡默认**）：只叠加（她自己的几个地方/一间屋），不动大格局。
         */
        fun merge(spec: J?, replace: Boolean) {
            val o = spec as? J.Obj ?: return
            if (replace) {
                val sp = o.fields["places"]
                if (sp is J.Arr && sp.items.isNotEmpty()) {
                    places.clear()
                    places[SpaceTables.HUB] = SpacePlace(SpaceTables.HUB, 0.0)
                }
                val st = o.fields["transport"]
                if (st is J.Obj && st.fields.isNotEmpty()) {
                    transport.clear()
                    transport["走路"] = 1.0
                    transport["步行"] = 1.0
                }
            }
            // 卡可以给"家"起自己的名字（圆心是谁由卡说了算）：
            // 省得地图里同时躺着"家"和卡起的名字两个 0 分钟的点，读起来像两个地方。
            val h = (o.fields["home"] as? J.Str)?.v ?: ""
            if (h.trim().isNotEmpty()) home = h.trim()
            val ps = o.fields["places"]
            if (ps is J.Arr) {
                for (p in ps.items) {
                    val po = p as? J.Obj ?: continue
                    val nm = (po.fields["name"] as? J.Str)?.v ?: ""
                    if (nm.isEmpty()) continue                 // Python: `if p.get("name")` 为真才算
                    places[nm] = placeFrom(po)
                }
            }
            val lk = o.fields["links"]
            if (lk is J.Obj) for ((k, v) in lk.fields) numOf(v)?.let { links[k] = it }
            val tr = o.fields["transport"]
            if (tr is J.Obj) for ((k, v) in tr.fields) numOf(v)?.let { transport[k] = it }
            val rm = o.fields["rooms"]
            if (rm is J.Arr) {
                rooms = rm.items.map { pyStr(it) }.filter { it.trim().isNotEmpty() }.toMutableList()
            }
        }

        // 世界卡：params.space 里放 JSON 字符串，或直接放 dict
        val w = objOf(worldJson)
        if (w != null) {
            val spRaw = w.fields["space"]
            val spAny: J? = if (spRaw == null || spRaw is J.Null) {
                (w.fields["params"] as? J.Obj)?.fields?.get("space")
            } else {
                spRaw
            }
            val sp: J? = if (spAny is J.Str) {
                try {
                    JsonS.parse(spAny.v)
                } catch (_: Exception) {
                    null
                }
            } else {
                spAny
            }
            if (sp is J.Obj) merge(sp, replace = !truthy(sp.fields["merge"]))
        }
        val r = objOf(roleJson)
        if (r != null) {
            val adv = r.fields["advanced"] as? J.Obj
            if (adv != null) merge(adv.fields["space"], replace = false)
        }

        // 卡自己起的"家"，若没在 places 里就补一个 0 分钟的点；原来的合成"家"删掉，
        // 免得地图里同时有两个"住在哪儿"的点。
        if (home != SpaceTables.HUB) {
            if (!places.containsKey(home)) places[home] = SpacePlace(home, 0.0)
            places[home] = places[home]!!.copy(minutes = 0.0)
            places.remove(SpaceTables.HUB)
        } else {
            if (!places.containsKey(SpaceTables.HUB)) {
                places[SpaceTables.HUB] = SpacePlace(SpaceTables.HUB, 0.0)
            }
            places[SpaceTables.HUB] = places[SpaceTables.HUB]!!.copy(minutes = 0.0)
        }
        for (rm in rooms) {
            if (rm.isNotEmpty() && rm != home && !places.containsKey(rm)) {
                places[rm] = SpacePlace(name = rm, minutes = SpaceTables.ROOM_MINUTES,
                    room = true, parent = home)
            }
        }
        return SpaceMap(places = places, links = links, transport = transport, era = eraKey,
            home = home, rooms = rooms.filter { places.containsKey(it) })
    }

    private fun placeFrom(po: J.Obj): SpacePlace = SpacePlace(
        name = (po.fields["name"] as? J.Str)?.v ?: "",
        minutes = numOf(po.fields["minutes"]) ?: 0.0,
        open = openFrom(po.fields["open"]),
        room = truthy(po.fields["room"]),
        parent = (po.fields["parent"] as? J.Str)?.v ?: "",
    )

    /** 卡里的 `"open": [6, 20]` → (6, 20)；不是长度 2 的数组 / 认不出数字 → null（视为一直开）。 */
    private fun openFrom(v: J?): Pair<Int, Int>? {
        val a = v as? J.Arr ?: return null
        if (a.items.size != 2) return null
        val s = intOfLoose(a.items[0]) ?: return null
        val e = intOfLoose(a.items[1]) ?: return null
        return s to e
    }

    /**
     * 交通方式 → 耗时系数。
     *
     * 先查这张地图的（年代）表；表里没有就退回模块级通用表（打车/高铁…这类跨年代写法）。
     * 两边都没有 → 1.0（按走路算，宁慢不快）。
     */
    fun factor(transport: Map<String, Double>?, by: String?): Double {
        if (by.isNullOrEmpty()) return 1.0
        val name = by.trim()
        val inMap = transport?.get(name)
        if (inMap != null) return if (inMap == 0.0) 1.0 else inMap
        val g = SpaceTables.TRANSPORT[name] ?: 1.0
        return if (g == 0.0) 1.0 else g
    }

    /**
     * 这张地图（这个年代）可选的交通方式 → [(名字, 系数)]，快的在前。
     *
     * 给别人看的列表要用这个，不要用模块级的 `SpaceTables.TRANSPORT` —— 那是"跨年代通用写法"，
     * 列出来会让唐宋看上去像有地铁。
     */
    fun transportOptions(mp: SpaceMap?): List<Pair<String, Double>> {
        val t = mp?.transport ?: emptyMap()
        return t.entries.map { it.key to it.value }.sortedWith(compareBy({ it.second }, { it.first }))
    }

    /**
     * a → b 要多少分钟。a、b 都不是家时按"经过家"估（偏保守），`links` 可精确覆盖。
     *
     * ⚠ 轮辐捷径比的是**字面量 `家`**（电脑端就是 `HUB`），不是 `map.home`：卡把家改名成
     * "宿舍"之后，从宿舍出发去别处仍按 `travel[宿舍] + travel[乙地]` 算（两边都不是字面量"家"），
     * 结果一样；但若卡片把某个地点也命名为"家"，行为就跟 `home` 无关了。照抄，不"修好"。
     */
    fun travelMinutes(mp: SpaceMap, a: String, b: String, by: String? = null): Double {
        if (a.isEmpty() || b.isEmpty() || a == b) return 0.0
        for (key in listOf(a + "|" + b, b + "|" + a)) {
            val v = mp.links[key]
            if (v != null) return maxOf(0.0, v * factor(mp.transport, by))
        }
        val ta = mp.places[a]?.minutes ?: 0.0
        val tb = mp.places[b]?.minutes ?: 0.0
        val raw = if (a == SpaceTables.HUB) tb else (if (b == SpaceTables.HUB) ta else ta + tb)
        return maxOf(0.0, raw * factor(mp.transport, by))
    }

    /**
     * 这段时间从 `frm` 能到哪些地方（按耗时升序，同耗时按名字）。
     *
     * 默认**不列屋里**：卧室/厨房只有 0.5 分钟，会把"够去哪"的列表挤满 ——
     * 而它们本来就走得到（同一间屋子），不需要列出来提醒。
     * `limit`：null / 0 = 不限条数；负数按 Python 的 `out[:n]` 切片（去掉末尾几项）。
     */
    fun reachable(mp: SpaceMap, frm: String, minutes: Double?, limit: Int? = null,
                  by: String? = null, includeRooms: Boolean = false): List<Pair<String, Double>> {
        val out = ArrayList<Pair<String, Double>>()
        if (minutes == null) return out
        for ((name, meta) in mp.places) {
            if (name == frm) continue
            if (!includeRooms && meta.room) continue
            val need = travelMinutes(mp, frm, name, by)
            if (need <= minutes) out.add(name to need)
        }
        out.sortWith(compareBy({ it.second }, { it.first }))
        if (limit == null || limit == 0) return out
        if (limit > 0) return out.take(limit)
        return out.take(maxOf(0, out.size + limit))
    }

    /**
     * 把标签里的地名落到地图上的一个地点。
     *
     * 支持三种写法：`学校` 直接命中；`家/厨房` 走斜线取尾巴；`厨房` 命中屋里那一间。
     * 认不出就返回原名（当"编外地点"处理：照记，但提醒里会说明地图上没有它）。
     */
    fun resolvePlace(mp: SpaceMap, name: String?): String {
        val n = (name ?: "").trim()
        if (n.isEmpty()) return n
        if (mp.places.containsKey(n)) return n
        if (n.contains('/') || n.contains('／')) {
            val tail = n.split('/', '／').last().trim()
            if (mp.places.containsKey(tail)) return tail
        }
        for (cand in mp.places.keys) {
            if (cand != n && (cand.contains(n) || n.contains(cand))) return cand
        }
        return n
    }

    /** 地点此刻开不开门（没写 `open` 视为一直开）。跨天营业（22:00–02:00）在电脑端就是这么判的。 */
    fun openNow(meta: SpacePlace?, worldDt: LocalDateTime): Pair<Boolean, String> {
        val o = meta?.open ?: return true to ""
        val start = o.first
        val end = o.second
        val h = worldDt.hour + worldDt.minute / 60.0
        val ok = if (start <= end) (h >= start && h < end) else (h >= start || h < end)
        if (ok) return true to ""
        val nm = if (meta.name.isNotEmpty()) meta.name else "那儿"
        return false to (nm + " 的营业时间是 " + p2(start) + ":00–" + p2(end) + ":00")
    }

    // ============================================================
    //  五、移动：记位置 + 判合理性
    // ============================================================

    /**
     * 位置标签。`\s` 在 Java 里只有 ASCII 空白，Python 的 `\s` 认全角空格，所以显式补上 U+3000。
     */
    private const val WS = "[\\s\\u3000]"

    private val MOVE_TAG = Regex(
        "\\[" + WS + "*(loc|ploc|位置|地点)" + WS + "*[:：]" + WS + "*([^\\[\\]]+?)" + WS + "*\\]",
        RegexOption.IGNORE_CASE,
    )

    /**
     * 从回复里抽出位置标签 → `[MoveTag]`
     *
     * 交通方式**只用竖线**分隔（`[loc:学校|骑车]`）：斜线留给屋里路径（`[loc:家/厨房]`），
     * 逗号和空格留给地名本身（"朝阳, 北京"）。这个约定写在说明书 §8.6.3 里。
     */
    fun parseMove(text: String?): List<MoveTag> {
        val out = ArrayList<MoveTag>()
        for (m in MOVE_TAG.findAll(text ?: "")) {
            val key = m.groupValues[1].lowercase()
            var body = m.groupValues[2].trim()
            var by = ""
            for (sep in listOf("|", "｜")) {
                val i = body.indexOf(sep)
                if (i >= 0) {
                    val tail = body.substring(i + 1)
                    if (tail.trim().isNotEmpty()) {
                        by = tail.trim()
                        body = body.substring(0, i).trim()
                    }
                    break
                }
            }
            out.add(MoveTag(player = key == "ploc", place = body, by = by))
        }
        return out
    }

    /** 把位置标签从显示文本里剥掉（和 `[aff:+3]` 一个规矩）。 */
    fun stripMoveTags(text: String): String = MOVE_TAG.replace(text, "")

    /**
     * 记下"谁在哪"。返回 `(状态, 判定)`：
     *
     * `verdict.ok == false` 表示这一跳时间不够（**照样记下新位置**，只在下一轮注入里点名要求补交代）。
     * `player=true` 时写的是 `player_place / player_since / player_prev` 那一组。
     */
    fun noteMove(role: String?, place: String, by: String = "", scale: Double? = null,
                 now: LocalDateTime? = null, mp: SpaceMap? = null, player: Boolean = false,
                 cfg: SpaceConfig? = null): Pair<SpaceState, MoveVerdict> {
        val c = cfg ?: loadConfig()
        val st = loadStateRaw(role, c)
        val nowDt = now ?: LocalDateTime.now()
        val key: String
        val sinceKey: String
        val prevKey: String
        if (player) {
            key = "player_place"; sinceKey = "player_since"; prevKey = "player_prev"
        } else {
            key = "place"; sinceKey = "since"; prevKey = "prev"
        }
        val map = mp ?: mapFor(null, null, c)
        fun strOf(k: String) = (st.fields[k] as? J.Str)?.v ?: ""

        // 地名落到地图上（家/厨房 → 厨房；认不出就按原名当"编外地点"）
        val to = resolvePlace(map, place)
        var from = strOf(key)
        if (from.isEmpty()) from = if (player) "" else map.home.ifEmpty { SpaceTables.HUB }
        if (from.isNotEmpty()) from = resolvePlace(map, from)

        val sinceTxt = strOf(sinceKey)
        val have = if (sinceTxt.isNotEmpty()) worldMinutesSince(sinceTxt, scale, nowDt) else null
        val byUse = if (by.isNotEmpty()) by else c.defaultTransport
        val need = if (from.isNotEmpty()) travelMinutes(map, from, to, byUse) else 0.0

        var ok = true
        var why = ""
        if (from.isNotEmpty() && from != to && have != null) {
            if (need > minOf(have, SpaceTables.MAX_MINUTES) + 1e-6) {
                ok = false
                why = "从" + from + "到" + to + "要 " + f0(need) + " 分钟，这段时间只过了 " + f0(have) + " 分钟"
            }
        } else if (from.isNotEmpty() && from != to && have == null) {
            why = "不知道上次是什么时候到的" + from + "（没有时间戳），按「能到」处理"
        }

        if (!map.places.containsKey(to)) {
            st.fields["offmap"] = J.Str(to)          // 地图上没有这个地方：记住，并在注入里提一句
        } else {
            st.fields.remove("offmap")
        }
        st.fields[prevKey] = J.Str(from)
        st.fields[key] = J.Str(to)
        st.fields[sinceKey] = J.Str(isoOf(nowDt))
        st.fields["scale"] = pyNum(scaleOf(scale))
        st.fields["by"] = J.Str(byUse)
        if (!ok && c.warnWhenImpossible) {
            val v = J.Obj()
            v.fields["from"] = J.Str(from)
            v.fields["to"] = J.Str(to)
            v.fields["need"] = pyNum(need)
            v.fields["have"] = if (have == null) J.Null else pyNum(have)
            v.fields["at"] = J.Str(isoOf(nowDt))
            v.fields["why"] = J.Str(why)
            st.fields["violation"] = v
        } else if (ok) {
            st.fields.remove("violation")
        }
        saveStateRaw(role, st, c)
        return stateFrom(st) to MoveVerdict(ok = ok, need = need, have = have, from = from, why = why)
    }

    fun notePlayerMove(role: String?, place: String, by: String = "", scale: Double? = null,
                       now: LocalDateTime? = null, mp: SpaceMap? = null,
                       cfg: SpaceConfig? = null): Pair<SpaceState, MoveVerdict> =
        noteMove(role, place, by = by, scale = scale, now = now, mp = mp, player = true, cfg = cfg)

    // ============================================================
    //  六、给模型的那一小段
    // ============================================================

    private fun whoOf(roleJson: String?, name: String?): String {
        if (!name.isNullOrEmpty()) return name
        val r = objOf(roleJson) ?: return "她"
        val n = r.fields["name"]
        if (n == null || n is J.Null) return "她"
        val s = pyStr(n)
        return s.ifEmpty { "她" }
    }

    /** 每轮注入的【空间】。关掉 / 算不出 → 返回 ""。 */
    fun injectionText(roleJson: String? = null, worldJson: String? = null, scale: Double? = null,
                      cfg: SpaceConfig? = null, now: LocalDateTime? = null, name: String? = null,
                      chain: List<MessageNode>? = null): String {
        val c = cfg ?: loadConfig()
        if (!c.enabled) return ""
        val nowDt = now ?: LocalDateTime.now()
        val who = whoOf(roleJson, name)
        val mp = mapFor(roleJson, worldJson, c)
        val raw = loadStateRaw(who, c)
        val st = stateFrom(raw)

        val sinceTxt = st.since
        var worldDt: LocalDateTime? = null
        if (sinceTxt.isNotEmpty()) {
            worldDt = try {
                // 用到达时刻 + 世界流逝推断"那边现在"（与 life_core 同一模型：现实 × 倍率）
                val wm = worldMinutesSince(sinceTxt, scale, nowDt) ?: 0.0
                val d = parseLocal(sinceTxt)
                if (d == null) null else plusWorldMinutes(d, wm)
            } catch (_: Exception) {
                null
            }
        }

        val places = mp.places
        val home = mp.home.ifEmpty { SpaceTables.HUB }
        val place = if (st.place.isNotEmpty()) st.place else home
        val have = if (sinceTxt.isNotEmpty()) worldMinutesSince(sinceTxt, scale, nowDt) else null
        val meta = places[place]
        val lines = ArrayList<String>()

        var head = "【空间】" + who + " 现在：" + place
        if (meta?.room == true) head += "（在家里）"
        if (have != null) {
            head += "（" + f0(have) + " 分钟前到，" +
                    (if (st.by.isNotEmpty()) st.by else c.defaultTransport) + "）"
        }
        lines.add(head)

        // 屋里格局：她在家时给一句"有哪些屋"（同屋走动 1 分钟内，不算赶路）。不在家就不提，省字数。
        val rooms = mp.rooms.filter { it != place }
        val atHome = place == home || meta?.room == true
        if (atHome && rooms.isNotEmpty()) {
            lines.add("屋里：" + rooms.joinToString("、") + "（都在 1 分钟内）")
        }
        if (st.offmap.isNotEmpty()) {
            lines.add("⚠ " + st.offmap + " 不在地图上 —— 按你说的记下了，但这地方之后要算路费就只能按邻近代估。")
        }
        if (worldDt != null) {
            val (open, why) = openNow(meta, worldDt)
            if (!open) lines.add("⚠ " + why + " —— 这个点她不该在那儿，给个由头或换个地方。")
        }

        // "够去哪"用**这一轮之前过了多久**做预算（下一幕可用时间），而不是"她已经待了多久"。
        // 待了多久只说明她有机会走（但没走）；过了多久才是下一幕的预算。
        val gap = lastGapMinutes(chain, scale, nowDt)
        val budget = gap ?: have
        if (c.showReachable && budget != null) {
            val by = c.defaultTransport
            val near = reachable(mp, place, budget, c.reachableLimit, by)
            if (near.isNotEmpty()) {
                lines.add("这" + f0(budget) + "分钟够去：" +
                        near.joinToString("、") { it.first + "(" + f0(it.second) + "分)" })
            } else if (budget >= 1) {
                val nearest = places.keys
                    .filter { it != place && places[it]?.room != true }
                    .map { travelMinutes(mp, place, it, by) }
                    .minOrNull() ?: 0.0
                lines.add("这" + f0(budget) + "分钟哪儿都去不了（最近的也要 " + f0(nearest) + " 分钟）")
            }
        }

        val pplace = if (st.playerPlace.isNotEmpty()) resolvePlace(mp, st.playerPlace) else ""
        if (pplace.isNotEmpty()) {
            val need = travelMinutes(mp, pplace, place, c.defaultTransport)
            lines.add("你在" + pplace + "，到这儿要 " + f0(need) + " 分钟")
        }

        // 穿帮提醒：最多提醒两次（免得每轮都念同一句），之后留着记录但不再注入
        val vObj = raw.fields["violation"] as? J.Obj
        if (c.warnWhenImpossible && vObj != null) {
            val warned = intOf(vObj.fields["warned"])
            if (warned < 2) {
                vObj.fields["warned"] = J.Num((warned + 1).toDouble(), (warned + 1).toString())
                try {
                    saveStateRaw(who, raw, c)
                } catch (_: Exception) {
                    // 提醒念不出来也不该让这一轮崩（与电脑端同一态度）
                }
                val v = st.violation
                lines.add("⚠ 上一轮她 " + f0(v?.have ?: 0.0) + " 分钟前还在" + pyStrOrNone(vObj.fields["from"]) +
                        "，现在写到" + pyStrOrNone(vObj.fields["to"]) + "：" + pyStrOrNone(vObj.fields["why"]) +
                        " —— 要么补一句路上/交通方式，要么把她拉回原处。")
            }
        }

        var text = lines.joinToString("\n")
        val room = if (c.maxChars != 0) c.maxChars else SpaceTables.DEFAULTS.maxChars
        // 截断的算术要连"换行 + 省略号"一起算进去，否则会差一个字（电脑端测试逮到过：241 > 240）
        if (pyLen(text) + 1 + pyLen(GUIDE) > room) {
            val keep = maxOf(0, room - pyLen(GUIDE) - 2)
            text = pyTake(text, keep).trimEnd('、', '，', '。', ' ') + "…"
        }
        return text + "\n" + GUIDE
    }

    /** 给 `/在哪` 看的完整状态（比注入详细）。 */
    fun describe(roleJson: String? = null, worldJson: String? = null, scale: Double? = null,
                 cfg: SpaceConfig? = null, now: LocalDateTime? = null,
                 name: String? = null): String {
        val c = cfg ?: loadConfig()
        val nowDt = now ?: LocalDateTime.now()
        val mp = mapFor(roleJson, worldJson, c)
        val who = whoOf(roleJson, name)
        val st = loadState(who, c)
        val home = mp.home.ifEmpty { SpaceTables.HUB }
        val out = ArrayList<String>()

        out.add("空间层：" + (if (c.enabled) "开" else "关"))
        val place = if (st.place.isNotEmpty()) st.place else home
        val have = if (st.since.isNotEmpty()) worldMinutesSince(st.since, scale, nowDt) else null
        out.add(who + " 现在：" + place + (
                if (have != null) {
                    "（" + f0(have) + " 分钟前到，" + (if (st.by.isNotEmpty()) st.by else "走路") + "）"
                } else {
                    "（还没记过位置，按" + home + "算）"
                }))
        if (st.playerPlace.isNotEmpty()) out.add("你 现在：" + st.playerPlace)
        st.violation?.let { v ->
            out.add("⚠ 上次跳得不合理：" + v.from + "→" + v.to + "（要 " + f0(v.need) +
                    " 分钟，只过了 " + f0(v.have ?: 0.0) + " 分钟）")
        }
        out.add("地图（" + mp.places.size + " 个地点，下面是从「" + place + "」出发的耗时）：")
        // Python 的 sorted 是稳定排序：同一耗时的地点按"地图里的先后"排（屋里那几间都一样）。
        for ((nm, meta) in mp.places.entries.sortedBy { it.value.minutes }) {
            if (nm == place) continue
            val need = travelMinutes(mp, place, nm, c.defaultTransport)
            val open = meta.open
            val o = if (open == null) "" else
                "　营业 " + p2(open.first) + ":00–" + p2(open.second) + ":00"
            out.add("  " + padEndTo(nm, 6) + " " + padStartTo(f0(need), 5) + " 分钟" + o)
        }
        out.add("改法：/在哪 <地点> ｜ /在哪 <地点>|骑车 ｜ /在哪 我=<地点> ｜ /空间 关 ｜ /空间 交通 打车")
        return out.joinToString("\n")
    }
}
