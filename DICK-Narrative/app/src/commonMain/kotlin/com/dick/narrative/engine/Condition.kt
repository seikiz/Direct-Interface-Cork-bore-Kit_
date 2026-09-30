package com.dick.narrative.engine

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

/**
 * 运行时状态：好感度 + 状态字段 + 标记。
 * 与 DICK 机制卡（affection / status / flags）对齐，所以同一份条件能在两端复用。
 */
data class NarrState(
    var affection: Int = 50,
    val status: MutableMap<String, String> = mutableMapOf(),
    val flags: MutableMap<String, Boolean> = mutableMapOf(),
) {
    fun toJson(): JsonObject = JsonObject(
        mapOf(
            "affection" to JsonPrimitive(affection),
            "status" to JsonObject(status.mapValues { JsonPrimitive(it.value) }),
            "flags" to JsonObject(flags.mapValues { JsonPrimitive(it.value) }),
        )
    )
}

/**
 * 条件求值 —— 与 DICK 的 evaluate_condition 语义一致：
 *   {"aff": ">=85"} / {"aff": 85}        好感度（字符串可带比较符）
 *   {"status": {"心情": "开心"}}          状态字段精确匹配
 *   {"flags": ["x", "!y"]}               存在 / 缺失（! 前缀 = 必须缺失）
 *   {"all": [c1, c2]} / {"any": [c1, c2]} 组合
 * 空条件恒真。
 */
object Cond {

    fun eval(st: NarrState, cond: JsonElement?): Boolean {
        if (cond == null) return true
        val o = cond as? JsonObject ?: return true
        if (o.isEmpty()) return true

        (o["all"] as? JsonArray)?.let { list ->
            return list.all { eval(st, it) }
        }
        (o["any"] as? JsonArray)?.let { list ->
            return list.any { eval(st, it) }
        }

        o["aff"]?.let { target ->
            val cmp = parseCmp(target) ?: return true
            return cmp.op(st.affection.toDouble(), cmp.num)
        }

        (o["status"] as? JsonObject)?.let { want ->
            return want.all { (k, v) ->
                val have = st.status[k]
                val target = (v as? JsonPrimitive)?.content
                if (have == null || target == null) false else have == target
            }
        }

        (o["flags"] as? JsonArray)?.let { list ->
            for (f in list) {
                val s = (f as? JsonPrimitive)?.content ?: continue
                val neg = s.startsWith("!")
                val key = if (neg) s.substring(1) else s
                val present = st.flags[key] == true
                if (present == neg) return false   // 要求缺失却存在 / 要求存在却缺失
            }
            return true
        }

        return true
    }

    private data class Cmp(val op: (Double, Double) -> Boolean, val num: Double)

    private fun parseCmp(target: JsonElement): Cmp? {
        if (target !is JsonPrimitive) return null
        val s = target.content.trim()
        val m = Regex("^(>=|<=|>|<|!=|==|=)?\\s*(-?\\d+(?:\\.\\d+)?)$").find(s)
        if (m != null) {
            val opStr = m.groupValues[1].ifBlank { "==" }
            val num = m.groupValues[2].toDoubleOrNull() ?: return null
            return Cmp(opOf(opStr), num)
        }
        val n = target.doubleOrNull ?: return null
        return Cmp(opOf("=="), n)
    }

    private fun opOf(op: String): (Double, Double) -> Boolean = when (op) {
        ">=" -> { a, b -> a >= b }
        ">" -> { a, b -> a > b }
        "<=" -> { a, b -> a <= b }
        "<" -> { a, b -> a < b }
        "!=" -> { a, b -> a != b }
        else -> { a, b -> a == b }
    }

    /** flags 条件里的布尔<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌写法（供外部读 spec 用） */
    fun boolOf(e: JsonElement?): Boolean? = (e as? JsonPrimitive)?.booleanOrNull
}
