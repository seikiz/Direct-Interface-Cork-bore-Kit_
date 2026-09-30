package com.dick.core

/**
 * EventJudge —— 事件判定模块。
 *
 * 判定规则：好感区间（aff_ge / aff_le）+ 关键词（keywords，可留空）。
 * 关键词留空 = 不设闸门，只看好感 —— 玩家不该为了触发事件去猜该说哪个词。
 *
 * once 语义（once 缺省 true，与旧行为一致）：
 *   · once=true  → 触发一次后永久置 flag，不再触发
 *   · once=false → 只受 cooldown 限制，可反复触发
 * cooldown 以【轮】计，用 state 里的 _turn 回合计数。
 * 不能用 event_log 长度 —— 那个只在触发时增长，冷却会算错。
 *
 * 副作用说明：原来这个模块是"纯函数、只读状态"。加入冷却与次数之后
 * 它必须写 _turn / event_counts 两个计数键（否则重复事件算不出节奏），
 * 但 flags（一次性标记）和 event_log（结局链用的顺序记录）仍然由
 * 调用方 MechanicsEngine 写 —— 职责没有被吞掉。
 */
object EventJudge {

    /** 判定结果：命中的事件 + 它现在触发了几次（含本次）。 */
    data class Result(val event: J.Obj, val times: Int)

    /**
     * 从事件数组里挑出第一个满足条件的。
     * @param events 事件数组（角色的 mechanics.events）
     * @param state  当前状态（mechanics 实时数据：affection / status / flags / _turn / event_counts）
     * @param lastUserText 上一条用户输入（用于关键词命中）
     * @return 命中的事件与次数；没命中返回 null
     */
    fun judge(events: J.Arr?, state: J.Obj?, lastUserText: String?): Result? {
        if (events == null || state == null) return null

        // 回合计数：每检查一次算<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌一回合（冷却的时间基准）
        val turn = (state.fields["_turn"]?.int() ?: 0) + 1
        state.fields["_turn"] = J.Num(turn.toDouble())

        val flags = state.fields["flags"] as? J.Obj ?: J.Obj().also { state.fields["flags"] = it }
        val counts = state.fields["event_counts"] as? J.Obj
            ?: J.Obj().also { state.fields["event_counts"] = it }
        val aff = state.fields["affection"]?.int() ?: 0
        val lower = (lastUserText ?: "").lowercase()

        for (item in events.items) {
            val ev = item as? J.Obj ?: continue
            val id = ev.fields["id"]?.str() ?: continue

            // once 缺省 true：老卡没有这个字段时行为完全不变
            val once = ev.fields["once"]?.bool() ?: true
            val rec = counts.fields[id] as? J.Obj
            val fired = rec?.fields?.get("n")?.int() ?: 0
            // 用 "at" 是否存在判断"触发过"，不能 rec["at"] ?: 0 ——
            // 那样"从未触发"和"第 0 回合触发"会混为一谈。
            val hasAt = rec?.fields?.containsKey("at") == true
            val last = if (hasAt) (rec!!.fields["at"]?.int() ?: 0) else 0

            if (once && (fired > 0 || flags.fields[id]?.bool() == true)) continue

            // 冷却：距上次触发不到 cooldown 轮就跳过（once=false 时才有意义）
            if (!once && fired > 0) {
                val cd = ev.fields["cooldown"]?.int() ?: 0
                if (cd > 0 && !hasAt) continue
                if (cd > 0 && (turn - last) < cd) continue
            }

            var ok = true
            val affGe = ev.fields["aff_ge"]?.int()
            if (affGe != null && aff < affGe) ok = false
            val affLe = ev.fields["aff_le"]?.int()
            if (ok && affLe != null && aff > affLe) ok = false
            // keywords 为 null（编辑器里留空时不会写入这个键）或空数组 → 不设闸门
            val kws = ev.fields["keywords"] as? J.Arr
            if (ok && kws != null && kws.items.isNotEmpty()) {
                if (!kws.items.any { k -> k.str()?.let { lower.contains(it.lowercase()) } == true }) ok = false
            }

            if (ok) {
                val times = fired + 1
                val nr = rec ?: J.Obj().also { counts.fields[id] = it }
                nr.fields["n"] = J.Num(times.toDouble())
                nr.fields["at"] = J.Num(turn.toDouble())
                return Result(ev, times)
            }
        }
        return null
    }
}
