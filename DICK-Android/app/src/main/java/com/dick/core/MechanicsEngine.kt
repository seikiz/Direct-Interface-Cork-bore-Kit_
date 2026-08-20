package com.dick.core

import kotlin.random.Random
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.abs

/**
 * 机制卡引擎（好感度 / 状态 / 事件）——与桌面版 DICK_core.py 的机制引擎对齐。
 *
 * 标签协议（AI 回复末尾输出，展示前剥离）：
 *   [aff:+3] / [aff:-2]     好感度相对增减（也可 [aff:5] 绝对值）
 *   [心情:开心]             枚举状态直接赋值
 *   [体力:90] / [体力:-10]   整数状态：绝对值或相对增减（± 前缀）
 *
 * 状态随树节点快照（metadata["ms"]）：回溯到哪一节点，机制就恢复到那一刻。
 */
class MechanicsEngine {
    var config: J.Obj? = null
    var state: J.Obj? = null
    var pendingEvent: J.Obj? = null
    var battleCfg: J.Obj? = null
    var playerCfg: J.Obj? = null

    companion object {
        const val BATTLE_LEGEND_CHANCE = 0.00001
    }

    /** 战斗配置（advanced.battle，App.kt 注入） */
    fun battleConfig(): J.Obj? = battleCfg

    private val tagRegex = Regex("\\[([^\\[\\]:：]+?)\\s*[:：]\\s*([^\\[\\]]+?)\\]")

    // ---------- 初始化 / 恢复 ----------
    /**
     * 重载机制配置。reset=true（切角色/新会话）：无快照用 initial；
     * reset=false（回溯/续聊兜底）：无快照时保留已累加状态（int 累加不清零）。
     * forceInitial=true（改配置保存）：无视树快照，一律用配置 initial 重建——
     * 否则旧快照里同名字段（旧值）会覆盖新配置的 initial（如新增"敏感度" initial=3
     * 却显示旧快照的 2）。
     */
    fun reload(cfg: J.Obj?, tree: ChatTree, reset: Boolean = false, forceInitial: Boolean = false) {
        config = cfg
        pendingEvent = null
        if (cfg == null) { state = null; return }
        val prev = state
        state = null
        val st = J.Obj()
        val aff = cfg.fields["affection"] as? J.Obj
        if (aff != null && aff.fields["enabled"]?.bool() == true) {
            val lo = aff.fields["min"]?.int() ?: 0
            val hi = aff.fields["max"]?.int() ?: 100
            st.fields["affection"] = J.Num(((aff.fields["initial"]?.int() ?: 50).coerceIn(lo, hi)).toDouble())
        } else {
            st.fields["affection"] = J.Num(50.0)
        }
        val status = J.Obj()
        val stCfg = cfg.fields["status"] as? J.Obj
        if (stCfg != null && stCfg.fields["enabled"]?.bool() == true) {
            (stCfg.fields["fields"] as? J.Arr)?.items?.forEach { f ->
                val fo = f as? J.Obj ?: return@forEach
                val key = fo.fields["key"]?.str() ?: return@forEach
                // 与好感度同规格：int 型永远写具体数值（缺失用 0），enum 型缺失用空串
                // 绝不能写 J.Null —— J.Null.int()=0 且非 null，会导致累加每轮从 0 开始
                status.fields[key] = if (fo.fields["type"]?.str() == "int") {
                    J.Num((fo.fields["initial"]?.int() ?: 0).toDouble())
                } else {
                    fo.fields["initial"] ?: J.Str("")
                }
            }
        }
        st.fields["status"] = status
        st.fields["flags"] = J.Obj()
        sanitize(st)
        val snap = if (forceInitial) null else leafSnapshot(tree)
        if (snap != null) {
            state = snap
            // 旧存档快照可能含 J.Null/缺失字段 → 清洗后再用（否则累加从 0 开始）
            sanitize(state!!)
        } else if (prev != null && !reset) {
            // 无快照且非强制重置：保留已累加状态，只补缺失字段
            val merged = prev.fields["status"] as? J.Obj ?: J.Obj()
            (status.fields).forEach { (k, v) ->
                if (!merged.fields.containsKey(k)) merged.fields[k] = v
            }
            prev.fields["status"] = merged
            if (!prev.fields.containsKey("flags")) prev.fields["flags"] = J.Obj()
            state = prev
            sanitize(state!!)
        } else {
            state = st
        }
    }

    fun snapshot(): J.Obj? {
        val s = state ?: return null
        return try { JsonS.parse(JsonS.stringify(s)) as? J.Obj } catch (_: Exception) { s }
    }

    /**
     * 清洗机制状态：把状态里缺失/为 J.Null 的字段按配置补齐。
     * 旧版本存档的 ms 快照里 int 字段可能是 J.Null（J.Null.int()=0 且非 null，
     * 会导致累加每轮从 0 开始），恢复时必须清洗，否则算法再对也白搭。
     * int → initial（缺失用 0）；enum → initial（缺失用空串）；缺失字段补上。
     */
    private fun sanitize(st: J.Obj) {
        val cfg = config ?: return
        val stCfg = cfg.fields["status"] as? J.Obj
        if (stCfg?.fields?.get("enabled")?.bool() != true) return
        var status = st.fields["status"] as? J.Obj
        if (status == null) {
            status = J.Obj()
            st.fields["status"] = status
        }
        (stCfg.fields["fields"] as? J.Arr)?.items?.forEach { f ->
            val fo = f as? J.Obj ?: return@forEach
            val key = fo.fields["key"]?.str() ?: return@forEach
            val cur = status.fields[key]
            if (fo.fields["type"]?.str() == "int") {
                if (cur !is J.Num) {
                    status.fields[key] = J.Num((fo.fields["initial"]?.int() ?: 0).toDouble())
                }
            } else {
                if (cur !is J.Str) {
                    status.fields[key] = fo.fields["initial"] ?: J.Str("")
                }
            }
        }
    }

    /** METTERTOOLS：按上限百分比一键填好感（percent 0-100，默认 100=满上限） */
    fun setAffectionPercent(percent: Int = 100): Int? {
        val cfg = config ?: return null
        val aff = cfg.fields["affection"] as? J.Obj ?: return null
        if (aff.fields["enabled"]?.bool() != true) return null
        val lo = aff.fields["min"]?.int() ?: 0
        val hi = aff.fields["max"]?.int() ?: 100
        val pct = percent.coerceIn(0, 100)
        val v = (hi * pct / 100.0).toInt().coerceIn(lo, hi)
        state?.fields?.set("affection", J.Num(v.toDouble()))
        return v
    }

    fun restore(tree: ChatTree, nodeId: String?) {
        if (config == null) return
        var nid = nodeId ?: tree.currentLeafId
        var guard = 0
        while (nid != null && guard++ < 2000) {
            val node = tree.getNode(nid) ?: break
            val ms = (node.metadata as? J.Obj)?.fields?.get("ms") as? J.Obj
            if (ms != null) {
                state = ms
                sanitize(state!!)  // 旧快照 J.Null/缺失字段清洗
                return
            }
            nid = node.parentId
        }
        reload(config, tree)
    }

    private fun leafSnapshot(tree: ChatTree): J.Obj? {
        var nid = tree.currentLeafId
        var guard = 0
        while (nid != null && guard++ < 2000) {
            val node = tree.getNode(nid) ?: break
            val ms = (node.metadata as? J.Obj)?.fields?.get("ms") as? J.Obj
            if (ms != null) return ms
            nid = node.parentId
        }
        return null
    }

    // ---------- 标签解析 ----------
    /** 解析机制标签：apply=true 更新状态并剥离；false 仅做显示剥离（流式） */
    fun stripTags(text: String, apply: Boolean): String {
        val cfg = config ?: return text
        val st = state ?: return text
        val affCfg = cfg.fields["affection"] as? J.Obj
        val stCfg = cfg.fields["status"] as? J.Obj
        val fields = LinkedHashMap<String, J.Obj>()
        (stCfg?.fields?.get("fields") as? J.Arr)?.items?.forEach {
            val fo = it as? J.Obj ?: return@forEach
            val key = fo.fields["key"]?.str() ?: return@forEach
            fields[key] = fo
        }
        val statusObj = st.fields["status"] as? J.Obj
        val statusRef = if (statusObj != null) statusObj else {
            // 防御：旧快照/restore 的 state 可能没有 status 字段 → 新建并写回 st，
            // 否则累加结果写入临时对象后丢失（表现为"每次都从0开始加"）
            val fresh = J.Obj()
            st.fields["status"] = fresh
            fresh
        }

        return tagRegex.replace(text) { m ->
            val key = m.groupValues[1].trim()
            val value = m.groupValues[2].trim()
            if (key.equals("aff", ignoreCase = true)) {
                if (affCfg == null || affCfg.fields["enabled"]?.bool() != true) return@replace m.value
                if (!apply) return@replace ""
                val deltaPct = value.toIntOrNull() ?: return@replace m.value
                val lo = affCfg.fields["min"]?.int() ?: 0
                val hi = affCfg.fields["max"]?.int() ?: 100
                // 好感度按百分比算：[aff:+N] = 上限的 N%（100 上限时与绝对值一致）
                val delta = if (deltaPct != 0) Math.round(hi * deltaPct / 100.0).toInt() else 0
                val cur = st.fields["affection"]?.int() ?: 50
                var next = (cur + delta).coerceIn(lo, hi)
                val crit = (affCfg.fields["crit"] as? J.Num)?.v ?: 0.001
                if (crit > 0 && Random.nextDouble() < crit) next = hi
                st.fields["affection"] = J.Num(next.toDouble())
                ""
            } else if (key.equals("ph", ignoreCase = true) || key.equals("player_hp", ignoreCase = true)) {
                if (!apply) return@replace ""
                val delta = value.toIntOrNull() ?: return@replace m.value
                val player = state?.fields?.get("player") as? J.Obj ?: return@replace m.value
                val cur = (player.fields["hp"] as? J.Num)?.v?.toInt() ?: 100
                player.fields["hp"] = J.Num(maxOf(0, cur + delta).toDouble())
                ""
            } else {
                val fo = fields[key] ?: return@replace m.value
                if (!apply) return@replace ""
                val ftype = fo.fields["type"]?.str() ?: "enum"
                if (ftype == "int") {
                    val raw = value.toIntOrNull() ?: return@replace m.value
                    // 好感度同规格：cur 永远有值（reload 写 J.Num；restore 旧快照缺字段时兜底 initial）
                    val cur = statusRef.fields[key]?.int() ?: (fo.fields["initial"]?.int() ?: 0)
                    val next = if ((value.startsWith("+") || value.startsWith("-")) && raw != 0) {
                        cur + raw
                    } else {
                        raw
                    }
                    val lo = fo.fields["min"]?.int() ?: 0
                    val hi = fo.fields["max"]?.int() ?: 100
                    statusRef.fields[key] = J.Num(next.coerceIn(lo, hi).toDouble())
                } else {
                    statusRef.fields[key] = J.Str(value)
                }
                ""
            }
        }
    }

    // ---------- 事件 ----------
    fun checkEvents(lastUserText: String?): J.Obj? {
        val cfg = config ?: return null
        val st = state ?: return null
        val evs = cfg.fields["events"] as? J.Arr ?: return null
        val flags = st.fields["flags"] as? J.Obj ?: J.Obj()
        val lower = (lastUserText ?: "").lowercase()
        for (item in evs.items) {
            val ev = item as? J.Obj ?: continue
            val id = ev.fields["id"]?.str() ?: continue
            if (flags.fields[id]?.bool() == true) continue
            var ok = true
            val affGe = ev.fields["aff_ge"]?.int()
            if (affGe != null && (st.fields["affection"]?.int() ?: 0) < affGe) ok = false
            val affLe = ev.fields["aff_le"]?.int()
            if (ok && affLe != null && (st.fields["affection"]?.int() ?: 0) > affLe) ok = false
            val kws = ev.fields["keywords"] as? J.Arr
            if (ok && kws != null) {
                if (!kws.items.any { k -> k.str()?.let { lower.contains(it.lowercase()) } == true }) ok = false
            }
            if (ok) {
                flags.fields[id] = J.Bool(true)
                return ev
            }
        }
        return null
    }

    // ---------- GAL 选项效果 ----------
    fun applyEffect(aff: Int?, stMap: Map<String, String>?) {
        val cfg = config ?: return
        val st = state ?: return
        val affCfg = cfg.fields["affection"] as? J.Obj
        if (aff != null && affCfg != null && affCfg.fields["enabled"]?.bool() == true) {
            val lo = affCfg.fields["min"]?.int() ?: 0
            val hi = affCfg.fields["max"]?.int() ?: 100
            // 好感度按百分比算
            val delta = if (aff != 0) Math.round(hi * aff / 100.0).toInt() else 0
            val cur = st.fields["affection"]?.int() ?: 50
            var next = (cur + delta).coerceIn(lo, hi)
            val crit = (affCfg.fields["crit"] as? J.Num)?.v ?: 0.001
            if (crit > 0 && Random.nextDouble() < crit) next = hi
            st.fields["affection"] = J.Num(next.toDouble())
        }
        if (stMap.isNullOrEmpty()) return
        val stCfg = cfg.fields["status"] as? J.Obj
        if (stCfg == null || stCfg.fields["enabled"]?.bool() != true) return
        val statusObj = st.fields["status"] as? J.Obj
        val statusRef = if (statusObj != null) statusObj else {
            val fresh = J.Obj()
            st.fields["status"] = fresh
            fresh
        }
        val fields = LinkedHashMap<String, J.Obj>()
        (stCfg.fields["fields"] as? J.Arr)?.items?.forEach {
            val fo = it as? J.Obj ?: return@forEach
            val key = fo.fields["key"]?.str() ?: return@forEach
            fields[key] = fo
        }
        for ((k, v) in stMap) {
            val fo = fields[k] ?: continue
            if (fo.fields["type"]?.str() == "int") {
                val raw = v.toIntOrNull() ?: continue
                // 好感度同规格：cur 永远有值
                val cur = statusRef.fields[k]?.int() ?: (fo.fields["initial"]?.int() ?: 0)
                val next = if ((v.startsWith("+") || v.startsWith("-")) && raw != 0) cur + raw else raw
                val lo = fo.fields["min"]?.int() ?: 0
                val hi = fo.fields["max"]?.int() ?: 100
                statusRef.fields[k] = J.Num(next.coerceIn(lo, hi).toDouble())
            } else {
                statusRef.fields[k] = J.Str(v)
            }
        }
    }

    // ---------- 系统提示注入 ----------
    fun promptBlock(): String {
        val cfg = config ?: return ""
        val st = state ?: return ""
        val sb = StringBuilder()
        val aff = cfg.fields["affection"] as? J.Obj
        if (aff != null && aff.fields["enabled"]?.bool() == true) {
            val lo = aff.fields["min"]?.int() ?: 0
            val hi = aff.fields["max"]?.int() ?: 100
            val cur = st.fields["affection"]?.int() ?: lo
            sb.append("【机制·好感度】当前好感度 ").append(cur).append('/').append(hi)
                .append("（范围 ").append(lo).append('-').append(hi)
                .append("，数值越高越亲近）。每轮回复末尾用 [aff:+N] 或 [aff:-N] 标签表示好感度变化")
                .append("（N 为百分比，即上限的 N%，根据剧情自然判定，通常 -5~+5；无变化则不输出标签，不要解释标签）。")
                .append(10.toChar())
        }
        val stCfg = cfg.fields["status"] as? J.Obj
        if (stCfg != null && stCfg.fields["enabled"]?.bool() == true) {
            val fields = (stCfg.fields["fields"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj } ?: emptyList()
            if (fields.isNotEmpty()) {
                val statusObj = st.fields["status"] as? J.Obj ?: J.Obj()
                val desc = fields.mapNotNull { f ->
                    val key = f.fields["key"]?.str() ?: return@mapNotNull null
                    val name = f.fields["name"]?.str()?.takeIf { it.isNotBlank() } ?: key
                    val cur = statusObj.fields[key] ?: f.fields["initial"] ?: J.Str("")
                    "$name=${cur.str() ?: cur.int().toString()}"
                }
                val keys = fields.mapNotNull { it.fields["key"]?.str() }.joinToString("、")
                sb.append("【机制·状态栏】当前状态：").append(desc.joinToString("，"))
                    .append("。状态变化时在回复末尾用 [键:值] 标签标注（键名：").append(keys)
                    .append("；整数型支持 [键:+N] 相对增减、[键:N] 绝对值；枚举型直接给值），无变化则不输出。")
                    .append("状态异常时（体力低/心情差/好感度骤降等）在回复中自然体现（如'我有点不舒服'、'今天没什么精神'），不要机械播报数值。")
                    .append(10.toChar())
            }
        }
        val evs = cfg.fields["events"] as? J.Arr
        if (evs != null && evs.items.isNotEmpty()) {
            val desc = evs.items.mapNotNull { it as? J.Obj }.mapNotNull { ev ->
                val id = ev.fields["id"]?.str() ?: return@mapNotNull null
                val conds = mutableListOf<String>()
                ev.fields["aff_ge"]?.int()?.let { conds.add("好感度≥$it") }
                ev.fields["aff_le"]?.int()?.let { conds.add("好感度≤$it") }
                (ev.fields["keywords"] as? J.Arr)?.items?.mapNotNull { it.str() }?.takeIf { it.isNotEmpty() }
                    ?.let { conds.add("提到" + it.joinToString("/")) }
                val name = ev.fields["name"]?.str()?.takeIf { it.isNotBlank() } ?: id
                name + "（" + (if (conds.isEmpty()) "无条件" else conds.joinToString("且")) + "）"
            }
            sb.append("【机制·事件】存在条件事件：").append(desc.joinToString("；"))
                .append("。条件满足时事件提示会自动注入，照常演出即可。").append(10.toChar())
        }
        return sb.toString().trim()
    }

    // ================= 战斗系统（招式触发 / 伤害防御公式 / buff） =================
    fun battleAttrs(): Map<String, J.Obj> {
        val cfg = battleConfig() ?: return emptyMap()
        val out = LinkedHashMap<String, J.Obj>()
        (cfg.fields["attrs"] as? J.Obj)?.fields?.forEach { (k, v) ->
            (v as? J.Obj)?.let { out[k] = it }
        }
        (cfg.fields["mech_attrs"] as? J.Arr)?.items?.forEach {
            val a = it as? J.Obj ?: return@forEach
            val key = a.fields["key"]?.str() ?: return@forEach
            out[key] = a
        }
        return out
    }

    fun initBattle() {
        val cfg = battleConfig() ?: run { return }
        val st = state
        val status: J.Obj
        if (st == null) {
            val s = J.Obj()
            s.fields["affection"] = J.Num(50.0)
            s.fields["status"] = J.Obj()
            s.fields["flags"] = J.Obj()
            s.fields["buffs"] = J.Arr()
            state = s
            status = J.Obj()
        } else {
            status = st.fields["status"] as? J.Obj ?: J.Obj().also { st.fields["status"] = it }
        }
        val attrs = cfg.fields["attrs"] as? J.Obj
        attrs?.fields?.forEach { (key, v) ->
            val a = v as? J.Obj ?: return@forEach
            if (key !in status.fields) {
                status.fields[key] = if (key == "hp") {
                    J.Num((a.fields["max"]?.int() ?: 100).toDouble())
                } else {
                    J.Num((a.fields["initial"]?.int() ?: 10).toDouble())
                }
            }
        }
        (cfg.fields["mech_attrs"] as? J.Arr)?.items?.forEach {
            val a = it as? J.Obj ?: return@forEach
            val key = a.fields["key"]?.str() ?: return@forEach
            if (key !in status.fields) {
                status.fields[key] = J.Num((a.fields["initial"]?.int() ?: 10).toDouble())
            }
        }
        if (st != null && st.fields["buffs"] !is J.Arr) st.fields["buffs"] = J.Arr()
        // 玩家侧属性（同规格：玩家卡配的战斗属性）→ 存 state["player"] 随树快照
        val player = J.Obj()
        player.fields["hp"] = J.Num(100.0)
        player.fields["atk"] = J.Num(10.0)
        player.fields["def"] = J.Num(5.0)
        playerCfg?.let { pc ->
            if (pc.fields["enabled"]?.bool() == true) {
                (pc.fields["attrs"] as? J.Obj)?.fields?.forEach { (key, v) ->
                    val a = v as? J.Obj ?: return@forEach
                    player.fields[key] = if (key == "hp") {
                        J.Num((a.fields["max"]?.int() ?: 100).toDouble())
                    } else {
                        J.Num((a.fields["initial"]?.int() ?: 10).toDouble())
                    }
                }
                (pc.fields["mech_attrs"] as? J.Arr)?.items?.forEach {
                    val a = it as? J.Obj ?: return@forEach
                    val key = a.fields["key"]?.str() ?: return@forEach
                    player.fields[key] = J.Num((a.fields["initial"]?.int() ?: 10).toDouble())
                }
            }
        }
        // 续聊/回溯：保留快照里的玩家状态
        (st?.fields?.get("player") as? J.Obj)?.fields?.forEach { (k, v) ->
            if (v is J.Num) player.fields[k] = v
        }
        st?.fields?.set("player", player)
    }

    /** 坍缩（十万分之一事件）：把战斗卡的所有数值统一变为 2000（名称即效果） */
    fun collapseBattleValues() {
        val s = state ?: J.Obj().also { state = it }
        val status = s.fields["status"] as? J.Obj ?: J.Obj().also { s.fields["status"] = it }
        val cfg = battleConfig()
        if (cfg != null) {
            (cfg.fields["attrs"] as? J.Obj)?.fields?.forEach { (key, _) ->
                status.fields[key] = J.Num(2000.0)
            }
            (cfg.fields["mech_attrs"] as? J.Arr)?.items?.forEach {
                val a = it as? J.Obj ?: return@forEach
                a.fields["key"]?.str()?.let { k -> status.fields[k] = J.Num(2000.0) }
            }
        }
        val player = s.fields["player"] as? J.Obj
        player?.fields?.forEach { (k, v) ->
            if (k != "turns" && v is J.Num) player.fields[k] = J.Num(2000.0)
        }
        s.fields["collapsed"] = J.Bool(true)
        if (s.fields["buffs"] !is J.Arr) s.fields["buffs"] = J.Arr()
    }

    private fun battleVars(extra: Map<String, Double>? = null): Map<String, Double> {
        val vars = HashMap<String, Double>()
        ((state?.fields?.get("status") as? J.Obj)?.fields)?.forEach { (k, v) ->
            if (v is J.Num) vars[k] = v.v
        }
        val player = state?.fields?.get("player") as? J.Obj
        vars["player_atk"] = (player?.fields?.get("atk") as? J.Num)?.v ?: 10.0
        vars["player_def"] = (player?.fields?.get("def") as? J.Num)?.v ?: 5.0
        vars["player_hp"] = (player?.fields?.get("hp") as? J.Num)?.v ?: 100.0
        extra?.forEach { (k, v) -> vars[k] = v }
        return vars
    }

    private fun evalFormula(expr: String?, extra: Map<String, Double>? = null): Double? {
        if (expr.isNullOrBlank()) return null
        return try { BattleFormula.eval(expr, battleVars(extra)) } catch (_: Exception) { null }
    }

    /** 结算玩家出招。返回 (结算文本 or null, 是否传说事件) */
    fun resolveMove(moveId: String): Pair<String?, Boolean> {
        val cfg = battleConfig() ?: return null to false
        val st = state ?: return null to false
        val status = st.fields["status"] as? J.Obj ?: return null to false
        val move = (cfg.fields["moves"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj }
            ?.firstOrNull { it.fields["id"]?.str() == moveId } ?: return null to false
        val moveName = move.fields["name"]?.str()?.takeIf { it.isNotBlank() } ?: moveId
        // 消耗检查
        (move.fields["cost"] as? J.Obj)?.fields?.forEach { (k, v) ->
            val need = v.int()
            if ((status.fields[k]?.int() ?: 0) < need) {
                return "⚠️ $moveName 需要 $k $need，当前不足" to false
            }
        }
        val formulas = cfg.fields["formulas"] as? J.Obj
        val critChance = evalFormula(formulas?.fields?.get("crit_chance")?.str() ?: "0.1")
            ?.coerceIn(0.0, 1.0) ?: 0.1
        val isCrit = Random.nextDouble() < critChance
        val critMult = evalFormula(formulas?.fields?.get("crit_mult")?.str() ?: "2") ?: 2.0
        val expr = move.fields["formula"]?.str()?.takeIf { it.isNotBlank() }
            ?: formulas?.fields?.get("damage")?.str() ?: "player_atk * 2 - def"
        val dmg = (evalFormula(expr) ?: 1.0) * (if (isCrit) critMult else 1.0)
        val dmgInt = maxOf(1, dmg.toInt())
        status.fields["hp"] = J.Num(maxOf(0, (status.fields["hp"]?.int() ?: 0) - dmgInt).toDouble())
        // 消耗
        (move.fields["cost"] as? J.Obj)?.fields?.forEach { (k, v) ->
            status.fields[k] = J.Num(maxOf(0, (status.fields[k]?.int() ?: 0) - v.int()).toDouble())
        }
        // 挂 buff（同 id 刷新）
        val buffs = st.fields["buffs"] as? J.Arr ?: J.Arr().also { st.fields["buffs"] = it }
        (move.fields["buffs"] as? J.Arr)?.items?.forEach {
            val b = it as? J.Obj ?: return@forEach
            val id = b.fields["id"]?.str() ?: return@forEach
            buffs.items.removeAll { x -> (x as? J.Obj)?.fields?.get("id")?.str() == id }
            val nb = J.Obj()
            nb.fields["id"] = J.Str(id)
            nb.fields["turns"] = J.Num((b.fields["turns"]?.int() ?: 3).toDouble())
            buffs.items.add(nb)
        }
        tickBuffs()
        val isLegend = Random.nextDouble() < BATTLE_LEGEND_CHANCE
        val critTxt = if (isCrit) "（暴击！）" else ""
        val hp = status.fields["hp"]?.int() ?: 0
        val txt = "💥 $moveName！造成 $dmgInt 点伤害$critTxt，对方生命 $hp。"
        return (if (isLegend) txt + "【天命触发】" else txt) to isLegend
    }

    /** 每回合结算 buff：应用效果 → 剩余回合-1 → 到期移除 */
    fun tickBuffs() {
        val st = state ?: return
        val buffs = st.fields["buffs"] as? J.Arr ?: return
        if (buffs.items.isEmpty()) return
        val cfg = battleConfig() ?: return
        val defs = HashMap<String, J.Obj>()
        (cfg.fields["buffs"] as? J.Arr)?.items?.forEach {
            val b = it as? J.Obj ?: return@forEach
            b.fields["id"]?.str()?.let { defs[it] = b }
        }
        val status = st.fields["status"] as? J.Obj ?: J.Obj()
        val kept = J.Arr()
        for (item in buffs.items) {
            val b = item as? J.Obj ?: continue
            val id = b.fields["id"]?.str() ?: continue
            val attrsObj = defs[id]?.fields?.get("attrs") as? J.Obj
            attrsObj?.fields?.forEach { (k, v) ->
                val cur = status.fields[k]?.int() ?: 0
                status.fields[k] = J.Num(maxOf(0, cur + v.int()).toDouble())
            }
            val turns = (b.fields["turns"]?.int() ?: 1) - 1
            if (turns > 0) {
                b.fields["turns"] = J.Num(turns.toDouble())
                kept.items.add(b)
            }
        }
        st.fields["buffs"] = kept
    }

    /** 给前端：战斗配置摘要 + 当前属性 + buff 列表 */
    fun battleUiState(): J.Obj? {
        val cfg = battleConfig() ?: return null
        val status = (state?.fields?.get("status") as? J.Obj)
        val collapsed = (state?.fields?.get("collapsed") as? J.Bool)?.v == true
        val out = J.Obj()
        val attrs = J.Arr()
        battleAttrs().forEach { (key, a) ->
            val o = J.Obj()
            o.fields["key"] = J.Str(key)
            o.fields["label"] = J.Str(a.fields["label"]?.str() ?: key)
            o.fields["value"] = J.Num((status?.fields?.get(key)?.int() ?: 0).toDouble())
            o.fields["max"] = J.Num((if (collapsed) 2000 else a.fields["max"]?.int() ?: 999999).toDouble())
            attrs.items.add(o)
        }
        out.fields["attrs"] = attrs
        val moves = J.Arr()
        (cfg.fields["moves"] as? J.Arr)?.items?.forEach {
            val m = it as? J.Obj ?: return@forEach
            val id = m.fields["id"]?.str() ?: return@forEach
            val o = J.Obj()
            o.fields["id"] = J.Str(id)
            o.fields["name"] = J.Str(m.fields["name"]?.str()?.takeIf { n -> n.isNotBlank() } ?: id)
            o.fields["desc"] = J.Str(m.fields["desc"]?.str() ?: "")
            moves.items.add(o)
        }
        out.fields["moves"] = moves
        val buffs = J.Arr()
        ((state?.fields?.get("buffs") as? J.Arr)?.items)?.forEach {
            val b = it as? J.Obj ?: return@forEach
            val o = J.Obj()
            o.fields["id"] = J.Str(b.fields["id"]?.str() ?: "")
            o.fields["turns"] = J.Num((b.fields["turns"]?.int() ?: 0).toDouble())
            buffs.items.add(o)
        }
        out.fields["buffs"] = buffs
        out.fields["hp"] = J.Num((status?.fields?.get("hp")?.int() ?: 0).toDouble())
        // 玩家侧属性（同规格）
        val pl = J.Arr()
        ((state?.fields?.get("player") as? J.Obj)?.fields)?.forEach { (k, v) ->
            if (v is J.Num) {
                val o = J.Obj()
                o.fields["key"] = J.Str(k)
                o.fields["label"] = J.Str(k)
                o.fields["value"] = J.Num(v.v)
                o.fields["max"] = J.Num((if (collapsed) 2000 else 999999).toDouble())
                pl.items.add(o)
            }
        }
        out.fields["player"] = pl
        return out
    }

    /** 战斗规则注入系统提示 */
    fun battlePromptBlock(): String {
        val cfg = battleConfig() ?: return ""
        val st = (state?.fields?.get("status") as? J.Obj)
        val sb = StringBuilder()
        // 玩家侧属性（同规格）
        val player = state?.fields?.get("player") as? J.Obj
        if (player != null) {
            val pdesc = player.fields.mapNotNull { (k, v) ->
                if (v is J.Num) "$k=${v.v.toInt()}" else null
            }
            if (pdesc.isNotEmpty()) {
                sb.append("【玩家属性】").append(pdesc.joinToString("、"))
                    .append("。玩家的生命可用 [ph:-N] 标签修正（你攻击玩家时用 [ph:-10] 表示对其造成 10 伤害）。")
                    .append(10.toChar())
            }
        }
        val fields = battleAttrs()
        if (fields.isNotEmpty()) {
            val desc = fields.mapNotNull { (key, a) ->
                val label = a.fields["label"]?.str() ?: key
                "$label=${st?.fields?.get(key)?.int() ?: 0}"
            }
            sb.append("【战斗属性】").append(desc.joinToString("、"))
                .append("（数值由战斗系统维护，你的回复可用 [键:值] 标签修正）。").append(10.toChar())
        }
        val moves = cfg.fields["moves"] as? J.Arr
        if (moves != null && moves.items.isNotEmpty()) {
            val names = moves.items.mapNotNull { it as? J.Obj }.mapNotNull { m ->
                val id = m.fields["id"]?.str() ?: return@mapNotNull null
                val n = m.fields["name"]?.str()?.takeIf { x -> x.isNotBlank() } ?: id
                val d = m.fields["desc"]?.str() ?: ""
                "$n（$d）"
            }
            sb.append("【招式】玩家可通过出招战斗：").append(names.joinToString("、"))
                .append("。出招伤害与消耗由系统结算，你负责以角色口吻演出战斗过程、受击反应与战况播报。")
                .append(10.toChar())
        }
        return sb.toString().trim()
    }
}

/** 战斗公式求值（白名单递归下降：变量 + 四则 + 括号 + max/min/floor/ceil/abs/random/randint） */
object BattleFormula {
    fun eval(expr: String, vars: Map<String, Double>): Double {
        val p = Parser(expr.replace(Regex("\\bdef\\b"), "_def_"), vars)
        val v = p.parseExpr()
        p.expectEnd()
        return v
    }

    private class Parser(private val s: String, private val vars: Map<String, Double>) {
        private var pos = 0
        fun expectEnd() {
            skipWs()
            if (pos < s.length) throw IllegalArgumentException("公式多余字符 @$pos")
        }
        private fun skipWs() {
            while (pos < s.length && s[pos].isWhitespace()) pos++
        }
        private fun peek(): Char? = if (pos < s.length) s[pos] else null
        fun parseExpr(): Double {
            var v = parseTerm()
            while (true) {
                skipWs()
                when (peek()) {
                    '+' -> { pos++; v += parseTerm() }
                    '-' -> { pos++; v -= parseTerm() }
                    else -> return v
                }
            }
        }
        private fun parseTerm(): Double {
            var v = parseFactor()
            while (true) {
                skipWs()
                when (peek()) {
                    '*' -> { pos++; v *= parseFactor() }
                    '/' -> { pos++; v /= parseFactor() }
                    '%' -> { pos++; v %= parseFactor() }
                    else -> return v
                }
            }
        }
        private fun parseFactor(): Double {
            skipWs()
            val c = peek() ?: throw IllegalArgumentException("公式意外结束")
            if (c == '(') {
                pos++
                val v = parseExpr()
                skipWs()
                if (peek() != ')') throw IllegalArgumentException("缺少右括号")
                pos++
                return v
            }
            if (c == '-') { pos++; return -parseFactor() }
            if (c == '+') { pos++; return parseFactor() }
            if (c in '0'..'9') {
                val start = pos
                while (pos < s.length && (s[pos].isDigit() || s[pos] == '.')) pos++
                return s.substring(start, pos).toDoubleOrNull() ?: throw IllegalArgumentException("非法数字")
            }
            if (c.isLetter() || c == '_') {
                val start = pos
                while (pos < s.length && (s[pos].isLetterOrDigit() || s[pos] == '_')) pos++
                val name = s.substring(start, pos)
                skipWs()
                if (peek() == '(') {
                    pos++
                    val args = mutableListOf<Double>()
                    skipWs()
                    if (peek() != ')') {
                        while (true) {
                            args.add(parseExpr())
                            skipWs()
                            when (peek()) {
                                ',' -> { pos++; skipWs() }
                                ')' -> break
                                else -> throw IllegalArgumentException("函数参数错误")
                            }
                        }
                    }
                    if (peek() != ')') throw IllegalArgumentException("缺少右括号")
                    pos++
                    return when (name) {
                        "max" -> args.maxOrNull() ?: 0.0
                        "min" -> args.minOrNull() ?: 0.0
                        "abs" -> abs(args.firstOrNull() ?: 0.0)
                        "floor" -> floor(args.firstOrNull() ?: 0.0)
                        "ceil" -> ceil(args.firstOrNull() ?: 0.0)
                        "round" -> Math.round(args.firstOrNull() ?: 0.0).toDouble()
                        "random" -> Random.nextDouble()
                        "randint" -> if (args.size >= 2) Random.nextInt(args[0].toInt(), args[1].toInt() + 1).toDouble() else 0.0
                        else -> throw IllegalArgumentException("未知函数: $name")
                    }
                }
                val key = if (name == "_def_") "def" else name
                return vars[key] ?: throw IllegalArgumentException("未知变量: $name")
            }
            throw IllegalArgumentException("公式非法字符: $c")
        }
    }
}
