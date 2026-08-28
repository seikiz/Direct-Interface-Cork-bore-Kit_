package com.dick.core

/**
 * EventJudge —— 事件判断模块（确定性、纯函数，无状态、无副作用）。
 *
 * 把「事件是否触发」从 MechanicsEngine / 发送流程里抽出来，独立成模块：
 *   - 事件是【单独的事件数组】（角色的 mechanics.events），与 status 数据分离；
 *   - status（状态栏）只是被【读取】的数据来源（好感/status/flags），本模块不改它；
 *   - 判定规则：一次性 flag / 好感阈值 aff_ge·aff_le / 关键词命中；
 *   - 返回命中的事件（或 null），由调用方决定如何标记 flag / 注入剧情。
 *
 * 这样事件判定与你说的「拆成模块」一致，便于之后接入 EndingJudge 与多结局预设。
 */
object EventJudge {

    /**
     * 纯事件判定：从事件数组里挑出第一个满足条件的。
     * @param events 事件数组（角色的 mechanics.events，单独数组）
     * @param state  当前状态（mechanics 实时数据：affection / status / flags），只读
     * @param lastUserText 上一条用户输入（用于关键词命中）
     * @return 触发的事件 J.Obj（含 id/name/prompt 等）或 null；不改动 state/flags
     */
    fun judge(events: J.Arr?, state: J.Obj?, lastUserText: String?): J.Obj? {
        if (events == null || state == null) return null
        val flags = state.fields["flags"] as? J.Obj ?: J.Obj()
        val lower = (lastUserText ?: "").lowercase()
        for (item in events.items) {
            val ev = item as? J.Obj ?: continue
            val id = ev.fields["id"]?.str() ?: continue
            if (flags.fields[id]?.bool() == true) continue  // 一次性：已触发过
            var ok = true
            val affGe = ev.fields["aff_ge"]?.int()
            if (affGe != null && (state.fields["affection"]?.int() ?: 0) < affGe) ok = false
            val affLe = ev.fields["aff_le"]?.int()
            if (ok && affLe != null && (state.fields["affection"]?.int() ?: 0) > affLe) ok = false
            val kws = ev.fields["keywords"] as? J.Arr
            if (ok && kws != null) {
                if (!kws.items.any { k -> k.str()?.let { lower.contains(it.lowercase()) } == true }) ok = false
            }
            if (ok) return ev
        }
        return null
    }
}
