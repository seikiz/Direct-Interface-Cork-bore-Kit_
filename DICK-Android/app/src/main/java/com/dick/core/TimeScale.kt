package com.dick.core

import java.io.File
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.pow
import kotlin.math.roundToInt

/**
 * TimeScale —— 软件时间流速：世界那边过得比现实快多少倍。
 *
 * 为什么要这个：AI 恋人要有时间感，但靠用户一条条输入去推进时间太麻烦。
 * 所以用【倍率】把现实流逝放大：现实过 1 秒，那边过 N 秒。
 *
 * 倍率的实际含义（按"一轮约现实 30 秒"折算，只用于人话描述）：
 *   720    → 一轮约 6 小时（默认）
 *   3600   → 一轮约 1 天
 *   86400  → 一轮约 1 个月
 *
 * 表盘为什么用【对数】刻度：MIN=10、MAX=1000万，跨 6 个数量级。
 * 线性表盘 98% 的行程都挤在最前几档上，指针一动就是几百万倍，没法用。
 * 对数下每转一格 = ×10，而人对量级的感知本来也是对数的。
 *
 * 与 PC 端 time_scale.py 的参数必须保持一致（同一套预设、同样的折算口径），
 * 否则两端表盘显示会对不上。
 */
object TimeScale {

    const val MIN_SCALE = 10.0
    const val MAX_SCALE = 10_000_000.0
    const val DEFAULT_SCALE = 720.0
    const val ROUND_SECONDS = 30.0

    /** (倍率, 名称)。名称是给用户看的，必须和 PC 端同一套说法。 */
    val PRESETS: List<Pair<Double, String>> = listOf(
        10.0 to "10倍 · 缓慢",
        60.0 to "60倍 · 一轮约 30 分钟",
        720.0 to "720倍 · 一轮约 6 小时",
        3600.0 to "3600倍 · 一轮约 1 天",
        21600.0 to "21600倍 · 一轮约 1 周",
        86400.0 to "86400倍 · 一轮约 1 个月",
        604800.0 to "604800倍 · 一轮约 7 个月",
    )

    /** 当前流速（进程内缓存；真正的存储在 config.json） */
    @Volatile
    var current: Double = DEFAULT_SCALE

    fun clamp(scale: Double): Double {
        if (scale.isNaN()) return DEFAULT_SCALE
        return scale.coerceIn(MIN_SCALE, MAX_SCALE)
    }

    /** 从 config.json 读。读不到就保持当前值。 */
    fun loadFrom(configFile: File) {
        try {
            if (!configFile.exists()) return
            val v = JsonS.parse(configFile.readText(Charsets.UTF_8)) as? J.Obj ?: return
            v.fields["time_scale"]?.let { current = clamp(it.dbl()) }
        } catch (_: Exception) {
            // 读不出来就用默认值，不<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌能因为一个设置把启动搞挂
        }
    }

    // ------------------------------------------------ 表盘换算
    private fun lo() = log10(MIN_SCALE)
    private fun hi() = log10(MAX_SCALE)

    /** 倍率 → 表盘位置 [0,1]（对数刻度） */
    fun posOf(scale: Double): Double {
        val span = hi() - lo()
        if (span <= 0.0) return 0.0
        val v = log10(clamp(scale))
        return ((v - lo()) / span).coerceIn(0.0, 1.0)
    }

    /** 表盘位置 [0,1] → 倍率（纯对数换算，不吸附） */
    fun scaleAt(pos: Double): Double {
        val p = if (pos.isNaN()) 0.0 else pos.coerceIn(0.0, 1.0)
        val span = hi() - lo()
        return clamp(10.0.pow(lo() + span * p))
    }

    /** 离哪个预设最近（对数距离容差）。不在任何预设附近返回 null。 */
    fun nearestPreset(scale: Double, tolerance: Double = 0.05): Double? {
        val s = clamp(scale)
        var best: Double? = null
        var bd = Double.MAX_VALUE
        for ((mul, _) in PRESETS) {
            val d = abs(log10(s) - log10(mul))
            if (d < bd) { bd = d; best = mul }
        }
        return if (bd <= tolerance) best else null
    }

    fun presetName(scale: Double): String? =
        nearestPreset(scale)?.let { m -> PRESETS.first { it.first == m }.second }

    /** 这个倍率下，一轮对话大约推进多少世界时间。表盘中央显示用。 */
    fun perRoundText(scale: Double = current): String {
        val sec = clamp(scale) * ROUND_SECONDS
        return when {
            sec < 60 -> "一轮约 ${sec.roundToInt()} 秒"
            sec < 3600 -> "一轮约 ${(sec / 60).roundToInt()} 分钟"
            sec < 86400 -> "一轮约 ${fmt1(sec / 3600)} 小时"
            sec / 86400 < 30 -> "一轮约 ${fmt1(sec / 86400)} 天"
            sec / 86400 / 30 < 24 -> "一轮约 ${fmt1(sec / 86400 / 30)} 个月"
            else -> "一轮约 ${fmt1(sec / 86400 / 30 / 12)} 年"
        }
    }

    /** 给界面/日志看的一句话 */
    fun describe(scale: Double = current): String {
        presetName(scale)?.let { return it }
        return "${fmtG(clamp(scale))} 倍 · ${perRoundText(scale)}"
    }

    /** 现实流逝了多少秒 → 那边过了多少秒 */
    fun virtualAgeSeconds(realSeconds: Double, scale: Double = current): Double {
        val r = if (realSeconds.isNaN()) 0.0 else realSeconds
        return r.coerceAtLeast(0.0) * clamp(scale)
    }

    private fun fmt1(v: Double): String {
        val r = (v * 10).roundToInt() / 10.0
        return if (r == r.toLong().toDouble()) r.toLong().toString() else r.toString()
    }

    private fun fmtG(v: Double): String = when {
        v >= 1_000_000 -> fmt1(v / 1_000_000) + "M"
        v >= 10_000 -> (v / 1000).roundToInt().toString() + "K"
        else -> v.roundToInt().toString()
    }
}
