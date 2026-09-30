package com.dick.core

import java.time.LocalDateTime
import java.time.Duration
import kotlin.math.roundToInt

/**
 * TimeContext —— 把历史链的【时间间隔】压成一段给模型看的话。
 *
 * 为什么要做这件事：MessageNode.timestamp 从第一天就一直在存，
 * 但代码里【没有任何地方读它】（只有存和序列化）。所以模型看到的对话是
 * "没有时间的一袋字" —— 不知道那些事是昨天还是上个月发生的。
 * 打点计时器能读出东西不是因为它记了字，是因为纸带匀速走、点距=时间。
 *
 * 参数与 PC 端 DICK_core.py 的 time_context_for 保持一致，否则两端行为会漂：
 *   现实间隔 < 30 分钟不吭声；最多报 3 段；单位按"那边"的时间算（乘流速）。
 */
object TimeContext {

    const val GAP_NOTICE_SECONDS = 30 * 60
    const val GAP_MAX_MARKS = 3
    const val DAY_NOTICE_HOURS = 20

    /** 解析节点时间戳。解析不了返回 null（调用方跳过）。 */
    fun parse(ts: String?): LocalDateTime? {
        if (ts.isNullOrBlank()) return null
        return try {
            LocalDateTime.parse(ts)
        } catch (_: Exception) {
            // 老存档里可能有别的格式，宽<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌松再试一次（去掉末尾的 Z）
            try {
                LocalDateTime.parse(ts.trimEnd('Z'))
            } catch (_: Exception) {
                null
            }
        }
    }

    private fun human(sec: Double): String = when {
        sec < 60 -> "${sec.roundToInt()} 秒"
        sec < 3600 -> "${(sec / 60).toInt()} 分钟"
        sec < DAY_NOTICE_HOURS * 3600 -> "${fmt1(sec / 3600)} 小时"
        else -> {
            val days = sec / 86400.0
            if (days < 30) "${fmt1(days)} 天" else "${fmt1(days / 30)} 个月"
        }
    }

    private fun fmt1(v: Double): String {
        val r = (v * 10).roundToInt() / 10.0
        return if (r == r.toLong().toDouble()) r.toLong().toString() else r.toString()
    }

    /**
     * 生成时间上下文。没有值得说的间隔就返回 null（不注入）。
     * @param chain 当前历史链（按时间正序）
     * @param scale 软件时间流速：报给模型的必须是【那边】过了多久
     */
    fun build(chain: List<MessageNode>, scale: Double = TimeScale.current): String? {
        val stamps = ArrayList<LocalDateTime>()
        for (n in chain) {
            if (n.role == "system") continue
            parse(n.timestamp)?.let { stamps.add(it) }
        }
        if (stamps.size < 2) return null

        val sc = if (scale.isNaN() || scale <= 0) 1.0 else scale
        val marks = ArrayList<Double>()
        for (i in 1 until stamps.size) {
            val gap = Duration.between(stamps[i - 1], stamps[i]).seconds.toDouble()
            // 阈值按【现实】判：现实里隔不到半小时就别啰嗦，
            // 但报出来的数字要乘倍率 —— 那才是她那边过的时长。
            if (gap >= GAP_NOTICE_SECONDS) marks.add(gap * sc)
        }
        if (marks.isEmpty()) return null
        val top = marks.sortedDescending().take(GAP_MAX_MARKS)

        val sinceLast = Duration.between(stamps.last(), LocalDateTime.now()).seconds.toDouble()
        val sb = StringBuilder()
        sb.append("【时间】这段对话不是一口气说完的，中途有过 ")
        sb.append(top.joinToString("、") { human(it) })
        sb.append(" 的间隔。")
        if (sinceLast * sc < GAP_NOTICE_SECONDS) {
            sb.append("上一句是刚才说的。")
        } else {
            sb.append("距离上一次说话已经过了 ").append(human(sinceLast * sc)).append("。")
        }
        sb.append("按这个时间感来演：隔了很久就该有变化（她做过别的、心情会不同、会提起你不在的时候）；")
        sb.append("刚刚才说完的事就别当成很久以前。")
        if (sc >= 60) {
            sb.append("（这个世界的时间流逝比现实快 ").append(sc.toInt()).append(" 倍：现实里的一小会儿，在她那边已经过了很久。）")
        }
        return sb.toString()
    }
}
