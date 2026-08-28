package com.dick.core

/**
 * EndingJudge —— 结局判断模块（确定性、纯函数）。
 *
 * 与事件判断一样抽成独立模块，避免把结局逻辑直接耦合进发送流程。
 * 采用 (a)：**确定性状态规则**判定结局——
 *   输入 角色卡的「多结局预设」数组 + 当前只读状态；
 *   输出 第一个满足条件的结局（或 null）。
 * 前置：状态由 MechanicsEngine 维护，本模块只**读取**（affection/status/flags），不改状态。
 *
 * 多结局预设结构（草案，可再细化）：
 *   endings: [
 *     { "id":"good", "name":"告白成功", "hidden":false, "desc":"…",
 *       "when": { "aff_ge": 90 } },                     // 好感 ≥ 90
 *     { "id":"hidden", "name":"？？？", "hidden":true,
 *       "when": { "flag":"secret_event" } },            // 某个一次性事件已触发
 *     { "id":"parting", "name":"离别",
 *       "when": { "status": { "mood": "平静" } } }      // 状态字段精确等于
 *   ]
 */
object EndingJudge {

    /** 从结局数组里挑出第一个满足当前状态的结局（确定性优先 = 数组顺序；需要可加 priority 字段）。返回 null 表示尚未抵达结局。 */
    fun judge(endings: J.Arr?, state: J.Obj?): J.Obj? {
        if (endings == null || state == null) return null
        val ordered = endings.items.mapNotNull { it as? J.Obj }
            .sortedBy { (it.fields["priority"] as? J.Num)?.v ?: Double.MAX_VALUE }
        for (e in ordered) {
            val w = e.fields["when"] as? J.Obj ?: continue
            if (whenMatches(w, state)) return e
        }
        return null
    }

    /** 判断某结局的 when 条件是否满足（只读状态，不修改）。支持"事件链部分影响结局"：
     *  状态阈值 + 事件触发组合(events/events_any/events_count) + 事件顺序(events_chain)。 */
    private fun whenMatches(w: J.Obj, state: J.Obj): Boolean {
        val aff = state.fields["affection"]?.int() ?: 50
        w.fields["aff_ge"]?.int()?.let { if (aff < it) return false }
        w.fields["aff_le"]?.int()?.let { if (aff > it) return false }
        w.fields["flag"]?.str()?.let { flag ->
            val flags = state.fields["flags"] as? J.Obj ?: return false
            if (flags.fields[flag]?.bool() != true) return false
        }
        val statusW = w.fields["status"] as? J.Obj
        if (statusW != null) {
            val status = state.fields["status"] as? J.Obj ?: return false
            for ((k, want) in statusW.fields) {
                val wantS = want.str() ?: want.int().toString()
                val curS = status.fields[k]?.let { it.str() ?: it.int().toString() } ?: ""
                if (curS != wantS) return false
            }
        }
        val eventW = w.fields["event"]?.str()
        if (eventW != null) {
            val flags = state.fields["flags"] as? J.Obj ?: return false
            if (flags.fields[eventW]?.bool() != true) return false
        }
        // 事件链（部分影响结局）：事件触发组合 / 数量 / 顺序
        w.fields["events"]?.let { v ->
            val need = (v as? J.Arr)?.items?.mapNotNull { it.str() } ?: return false
            val flags = state.fields["flags"] as? J.Obj ?: return false
            if (need.any { flags.fields[it]?.bool() != true }) return false   // 全部触发过
        }
        w.fields["events_any"]?.let { v ->
            val cand = (v as? J.Arr)?.items?.mapNotNull { it.str() } ?: return false
            val flags = state.fields["flags"] as? J.Obj ?: return false
            if (cand.none { flags.fields[it]?.bool() == true }) return false   // 至少一个
        }
        w.fields["events_count"]?.let { v ->
            val o = v as? J.Obj ?: return false
            val of = (o.fields["of"] as? J.Arr)?.items?.mapNotNull { it.str() } ?: return false
            val min = (o.fields["min"] as? J.Num)?.v?.toInt() ?: 1
            val flags = state.fields["flags"] as? J.Obj ?: return false
            if (of.count { flags.fields[it]?.bool() == true } < min) return false  // 数量达标
        }
        w.fields["events_chain"]?.let { v ->
            val seq = (v as? J.Arr)?.items?.mapNotNull { it.str() } ?: return false
            val log = (state.fields["event_log"] as? J.Arr)?.items?.mapNotNull { it.str() } ?: return false
            if (!logContainsOrder(log, seq)) return false   // 相对顺序一致
        }
        return true
    }

    /** event_log 中是否按相对顺序包含 seq（子序列匹配）。 */
    private fun logContainsOrder(log: List<String>, seq: List<String>): Boolean {
        var li = 0
        for (s in seq) {
            var found = false
            while (li < log.size) {
                if (log[li] == s) { found = true; li++; break }
                li++
            }
            if (!found) return false
        }
        return true
    }
}
