package com.dick.core

import java.time.LocalDateTime

/**
 * 生活层 / 空间层的**数据契约**（手写，不许生成器改）。
 *
 * 电脑端已经有两层（`life_core.py` 吃饭、`space_core.py` 不能瞬移）+ 常识库
 * （`commonsense.py` 年代 → 地点/交通/屋里）。手机端一直没有 —— 于是同一个角色
 * 在电脑上"今天是唐宋的江南，早上吃了小米粥"，换手机就变成没有日子、能瞬移。
 *
 * 这里的类型是**两端共用的一张纸**：
 *   · 表（年代 / 厨具 / 食材 / 地点 / 交通 / 屋里）由 `tools/gen_parity.py`
 *     从 Python 那几张表生成到 `Tables.kt`，所以只有一份真相；
 *   · 对拍基准（`selftest/ParityGoldens.kt`）同样由那个脚本生成，
 *     Kotlin 侧算出来的东西必须和 Python 一模一样，否则手机与电脑会算出两套餐。
 *
 * 字段名与电脑端的 JSON 完全一致（`life_config.json` / `space_config.json` /
 * `space/<角色>.json`），所以同一份数据目录在两端之间可以互相读。
 */

// ============================ 生活层<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（吃饭） ============================

/** 一个年代：厨具历史库的一行（`life_core.ERAS`）。 */
data class LifeEra(
    val key: String,
    val name: String,
    val year: Int,
    val tools: List<String>,
    val note: String,
)

/**
 * 主食 / 菜 / 喝的共用一行。
 *
 * `since`/`until` 是历史窗口（负数=公元前，`until=null` 表示至今），
 * `method`/`ingredients` 只有菜才有（主食与喝的留空）。
 */
data class LifeItem(
    val name: String,
    val since: Int,
    val until: Int?,
    val regions: List<String>,
    val meals: List<String>,
    val method: String,
    val ingredients: List<String>,
)

/** 生活层配置：字段名与 `life_config.json` 一致（默认值来自 `life_core.DEFAULTS`）。 */
data class LifeConfig(
    val enabled: Boolean = true,
    val era: String = "auto",
    val region: String = "auto",
    val taste: String = "",
    val avoid: String = "",
    val showMeals: Boolean = true,
    val maxChars: Int = 240,
    val location: String = "家",
)

/** `profile_for()` 的结果：这一轮她按哪个年代、什么口味、避开什么来吃。 */
data class LifeProfile(
    val role: String,
    val era: String,
    val eraFrom: String,
    val eraYear: Int,
    val tools: List<String>,
    val region: String,
    val regionFrom: String,
    val taste: String,
    val avoid: List<String>,
    val skill: String,
    val location: String,
    val showMeals: Boolean,
    val maxChars: Int,
)

/** 一餐的抽样结果（`sample_meal`）。 */
data class Meal(
    val meal: String,
    val key: String,
    val dish: String,
    val staple: String,
    val dishes: List<String>,
    val methods: List<String>,
    val drink: String,
    val tools: List<String>,
    val used: List<String>,
)

/** 世界时钟（`world_clock`）：那边现在几点。 */
data class WorldClock(
    val originIso: String,
    val worldIso: String,
    val day: Int,
    val lifeDayOrdinal: Long,
    val hhmm: String,
    val phase: String,
    val elapsedReal: Double,
    val elapsedWorld: Double,
    val mealsToday: List<Pair<String, String>>,
)

// ============================ 常识库（年代 → 地点/交通/屋里） ============================

/** 从"家"出发的单程分钟数。 */
data class CsPlace(
    val name: String,
    val minutes: Double,
)

/** 一个年代的地理常识：有哪些地方、怎么走、屋里长什么样。 */
data class CsEra(
    val places: List<CsPlace>,
    val transports: Map<String, Double>,
    val rooms: List<String>,
    val notes: String,
)

// ============================ 空间层（不能瞬移） ============================

/** 空间层配置：字段名与 `space_config.json` 一致。 */
data class SpaceConfig(
    val enabled: Boolean = true,
    val maxChars: Int = 240,
    val showReachable: Boolean = true,
    val reachableLimit: Int = 4,
    val defaultTransport: String = "走路",
    val warnWhenImpossible: Boolean = true,
    val stateDir: String = "space",
)

/** 地图上的一个地点（`map_for` 里 places 的值）。 */
data class SpacePlace(
    val name: String,
    val minutes: Double,
    val open: Pair<Int, Int>? = null,
    val room: Boolean = false,
    val parent: String = "",
)

/**
 * 一张地图：以 `home` 为圆心的轮辐模型 —— `cost(A→B) = travel[A] + travel[B]`，
 * 精确两地耗时写 `links`（键 "A|B"）。
 */
data class SpaceMap(
    val places: LinkedHashMap<String, SpacePlace>,
    val links: Map<String, Double>,
    val transport: Map<String, Double>,
    val era: String,
    val home: String,
    val rooms: List<String>,
)

/** 位置标签：`[loc:学校|骑车]` / `[ploc:家/厨房]`。 */
data class MoveTag(
    val player: Boolean,
    val place: String,
    val by: String,
)

/** 跳得合不合理（时间够不够）。 */
data class MoveVerdict(
    val ok: Boolean,
    val need: Double,
    val have: Double?,
    val from: String,
    val why: String,
)

/** 穿帮记录：她"瞬移"过一次，注入里提醒最多两次。 */
data class Violation(
    val from: String,
    val to: String,
    val need: Double,
    val have: Double?,
    val at: String,
    val why: String,
    val warned: Int = 0,
)

/** 一个角色此刻在哪（字段名与 `space/<角色>.json` 一致）。 */
data class SpaceState(
    val place: String = "",
    val since: String = "",
    val prev: String = "",
    val by: String = "",
    val scale: Double = 1.0,
    val playerPlace: String = "",
    val playerSince: String = "",
    val playerPrev: String = "",
    val offmap: String = "",
    val violation: Violation? = null,
)

/** 世界层能提供的时间戳解析（生活层与空间层同一套）。 */
internal fun parseLocal(ts: String?): LocalDateTime? {
    if (ts.isNullOrBlank()) return null
    return try {
        LocalDateTime.parse(ts)
    } catch (_: Exception) {
        try {
            LocalDateTime.parse(ts.trimEnd('Z'))
        } catch (_: Exception) {
            null
        }
    }
}
