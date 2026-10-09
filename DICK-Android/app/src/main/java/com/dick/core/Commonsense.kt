package com.dick.core

/**
 * Commonsense —— 常识库：年代 → 地点 / 交通 / 屋里格局（`commonsense.py` 的手机端）。
 *
 * 只做一件事：把「生活层（吃什么）」和「空间层（能去哪）」对齐到**同一年代口径**。
 * 电脑端的内置地图原本是现代都市口径，套到明朝或仙侠宗门上就会冒出"她坐地铁去码头"
 * —— 换汤不换药的另一种瞬移。
 *
 * 年代 key 与 `LifeTables.ERAS` 完全一致（Python 那边有测试盯着不许漂，这边靠
 * `tools/gen_parity.py` 从同一份表生成）。
 */
object Commonsense {

    private fun objOf(json: String?): J.Obj? {
        val t = json?.trim()
        if (t.isNullOrEmpty() || t == "null") return null
        return try {
            JsonS.parse(t) as? J.Obj
        } catch (_: Exception) {
            null
        }
    }

    private fun strOf(v: J?): String = (v as? J.Str)?.v ?: ""

    private fun child(o: J.Obj?, key: String): J.Obj? = o?.fields?.get(key) as? J.Obj

    fun eraKeys(): List<String> = CommonsenseTables.ERAS.keys.toList()

    /** 某年代的地点（认不出就用现代<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌口径，与 Python 一致）。 */
    fun places(era: String?): List<CsPlace> {
        val e = CommonsenseTables.ERAS[era?.trim()]
        if (e != null && e.places.isNotEmpty()) return e.places
        return CommonsenseTables.ERAS[CommonsenseTables.DEFAULT_ERA]?.places ?: emptyList()
    }

    fun transports(era: String?): Map<String, Double> {
        val e = CommonsenseTables.ERAS[era?.trim()]
        if (e != null && e.transports.isNotEmpty()) return e.transports
        return CommonsenseTables.ERAS[CommonsenseTables.DEFAULT_ERA]?.transports ?: emptyMap()
    }

    /** 屋里格局（房间）；「同屋走动」不算赶路，所以它们不带路费。 */
    fun rooms(era: String?): List<String> {
        val e = CommonsenseTables.ERAS[era?.trim()]
        if (e != null && e.rooms.isNotEmpty()) return e.rooms
        return CommonsenseTables.ERAS[CommonsenseTables.DEFAULT_ERA]?.rooms ?: emptyList()
    }

    fun notes(era: String?): String = CommonsenseTables.ERAS[era?.trim()]?.notes ?: ""

    /**
     * 该用哪张地图的年代：卡里**显式写**的优先（角色卡 → 世界卡的
     * `era` / `params.era`），其次交给生活层的关键词表认，最后现代。
     *
     * 顺序与 Python 一致：`for src in (role, world)` —— 角色卡说了算。
     */
    fun detectEra(worldJson: String? = null, roleJson: String? = null): String {
        for (src in listOf(objOf(roleJson), objOf(worldJson))) {
            if (src == null) continue
            val life = child(child(src, "advanced"), "life")
            val params = child(src, "params")
            for (probe in listOf(strOf(life?.fields?.get("era")), strOf(src.fields["era"]),
                                 strOf(params?.fields?.get("era")))) {
                if (probe.isNotEmpty() && CommonsenseTables.ERAS.containsKey(probe)) return probe
            }
        }
        val key = LifeCore.detectEra(worldJson)
        return if (CommonsenseTables.ERAS.containsKey(key)) key else CommonsenseTables.DEFAULT_ERA
    }

    /** 设定类型（仙侠/末世…）：卡里显式写 `kind` / `params.era_kind`，或从世界卡关键词认。 */
    fun detectKind(worldJson: String? = null, roleJson: String? = null): String {
        for (src in listOf(objOf(roleJson), objOf(worldJson))) {
            if (src == null) continue
            val life = child(child(src, "advanced"), "life")
            val params = child(src, "params")
            for (probe in listOf(strOf(life?.fields?.get("kind")), strOf(src.fields["kind"]),
                                 strOf(params?.fields?.get("era_kind")))) {
                if (probe.isNotEmpty() && CommonsenseTables.KINDS.contains(probe)) return probe
            }
        }
        var text = ""
        val w = objOf(worldJson)
        if (w != null) {
            for (k in listOf("name", "description", "rules")) text += strOf(w.fields[k])
        }
        for ((kind, hints) in KIND_HINTS) {
            for (h in hints) if (text.contains(h)) return kind
        }
        return ""
    }

    /** 空间层该用哪张地图：类型（仙侠/末世）优先于年代 —— 它们的地图差别更大。 */
    fun effectiveEra(worldJson: String? = null, roleJson: String? = null): String {
        val kind = detectKind(worldJson, roleJson)
        return if (kind.isNotEmpty()) kind else detectEra(worldJson, roleJson)
    }

    private val KIND_HINTS = listOf(
        "仙侠" to listOf("仙侠", "修真", "御剑", "宗门", "灵气", "金丹"),
        "末世" to listOf("末世", "废土", "丧尸", "辐射", "末日"),
    )
}
