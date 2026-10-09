package com.dick.core

/**
 * ChatBridge —— 生活层/空间层与界面之间的**一根线**。
 *
 * 为什么要有它：这两层要回答的问题（她今天吃了什么、她此刻在哪、这段时间够去哪）都得先知道
 * "现在跟谁聊、用哪张世界卡、历史链长什么样" —— 那是界面侧的状态，而 `LifeCore` / `SpaceCore`
 * 是纯逻辑（core 里连 Compose 都不许出现）。所以界面在这里挂几个取值的钩子：
 *
 *   · `ChatEngine.contextProvider` 用 `injections()` 拿每轮要注入的那两小段；
 *   · 插件命令（`/生活`、`/在哪`、`/世界包`）用同一套钩子，不必各自去摸界面状态；
 *   · 回复里的 `[loc:地名|交通]` / `[ploc:地名]` 用 `takeMoves()` 剥离并记账 ——
 *     **剥离是同步的**（要立刻显示干净文本），**记账交给 io 线**（那是写盘）。
 */
object ChatBridge {

    /** 当前历史链（按时间正序）。 */
    @Volatile
    var chainProvider: () -> List<MessageNode> = { emptyList() }

    /** 当前说话的角色名（群聊里就是本轮发言那位）。 */
    @Volatile
    var roleNameProvider: () -> String = { "" }

    /** 当前角色卡 JSON（`{name, advanced:{life:{…}, space:{…}}}`）。 */
    @Volatile
    var roleJsonProvider: () -> String? = { null }

    /** 当前世界卡 JSON（`{name, description, rules, params:{era, space…}}`）。 */
    @Volatile
    var worldJsonProvider: () -> String? = { null }

    /** 装完世界卡包后让界面重扫 worlds/（界面自己做主线程切换，core 不碰 UI）。 */
    @Volatile
    var worldsChanged: () -> Unit = {}

    fun notifyWorldsChanged() {
        try {
            worldsChanged()
        } catch (_: Exception) {
        }
    }

    fun who(): String = roleNameProvider().takeIf { it.isNotBlank() } ?: "她"

    private fun chain(): List<MessageNode> = try {
        chainProvider()
    } catch (_: Exception) {
        emptyList()
    }

    private fun roleJson(): String? = try {
        roleJsonProvider()
    } catch (_: Exception) {
        null
    }

    private fun worldJson(): String? = try {
        worldJsonProvider()
    } catch (_: Exception) {
        null
    }

    /**
     * 每轮注入的两小段：【生活·那边】然后【空间】（与电脑端 `_fetch_response` 的顺序一致）。
     * 关掉的那层、算不出的那层返回空串，由调用方跳过 —— 空注入不进载荷。
     */
    fun injections(): List<String> {
        val out = ArrayList<String>(2)
        val chain = chain()
        val rj = roleJson()
        val wj = worldJson()
        val who = who()
        try {
            LifeCore.injectionText(chain, TimeScale.current, rj, wj)
                .takeIf { it.isNotBlank() }?.let { out.add(it) }
        } catch (_: Exception) {
        }
        try {
            SpaceCore.injectionText(roleJson = rj, worldJson = wj, scale = TimeScale.current,
                name = who, chain = chain)
                .takeIf { it.isNotBlank() }?.let { out.add(it) }
        } catch (_: Exception) {
        }
        return out
    }

    /** 一条位置标注：谁（她/你）、去哪、怎么去的。 */
    data class MoveNote(val player: Boolean, val place: String, val by: String)

    /**
     * 把显示文本里的位置标签剥掉，并给出要记的移动。
     * 剥离必须同步（界面立刻要干净文本），记账由调用方丢给 io 线（见 `applyMoves`）。
     */
    fun takeMoves(text: String?): Pair<String, List<MoveNote>> {
        val t = text ?: return "" to emptyList()
        val moves = try {
            SpaceCore.parseMove(t)
        } catch (_: Exception) {
            emptyList()
        }
        if (moves.isEmpty()) return t to emptyList()
        val notes = moves.map { MoveNote(it.player, it.place, it.by) }
        val clean = try {
            SpaceCore.stripMoveTags(t)
        } catch (_: Exception) {
            t
        }
        return clean to notes
    }

    /** 记账（写盘）：**只在 io 线上调**。返回 `[她/你] 地名` 的说明，给系统消息用。 */
    fun applyMoves(notes: List<MoveNote>, who: String): List<String> {
        if (notes.isEmpty()) return emptyList()
        val wj = worldJson()
        val rj = roleJson()
        val mp = try {
            SpaceCore.mapFor(roleJson = rj, worldJson = wj)
        } catch (_: Exception) {
            return emptyList()
        }
        val out = ArrayList<String>(notes.size)
        for (n in notes) {
            try {
                if (n.player) {
                    SpaceCore.notePlayerMove(who, n.place, n.by, TimeScale.current,
                        java.time.LocalDateTime.now(), mp)
                    out.add("你 → " + n.place)
                } else {
                    val (_, v) = SpaceCore.noteMove(who, n.place, n.by, TimeScale.current,
                        java.time.LocalDateTime.now(), mp)
                    out.add(who + " → " + n.place + (if (v.ok) "" else "（⚠ 时间不够：" + v.why + "）"))
                }
            } catch (_: Exception) {
            }
        }
        return out
    }

    // ---------------- 命令用的<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌两个面板 ----------------

    fun lifePanel(): String = try {
        LifeCore.describe(chain(), TimeScale.current, roleJson(), worldJson())
    } catch (e: Exception) {
        "生活层出错：" + (e.message ?: e.javaClass.simpleName)
    }

    fun spacePanel(): String = try {
        SpaceCore.describe(roleJson = roleJson(), worldJson = worldJson(), scale = TimeScale.current,
            name = who())
    } catch (e: Exception) {
        "空间层出错：" + (e.message ?: e.javaClass.simpleName)
    }

    /** `/在哪 <地名>[|交通]`：记下她去了哪，并回一段说明（与电脑端命令同义）。 */
    fun moveTo(spec: String): String = move(spec, player = false)

    /** `/在哪 我=<地名>`：记下**你**去了哪（玩家位置也参与路费计算）。 */
    fun movePlayerTo(spec: String): String = move(spec, player = true)

    private fun move(spec: String, player: Boolean): String {
        val raw = spec.trim()
        if (raw.isEmpty()) return spacePanel()
        var place = raw
        var by = ""
        for (sep in listOf("|", "｜")) {
            if (raw.contains(sep)) {
                place = raw.substringBefore(sep).trim()
                by = raw.substringAfter(sep).trim()
                break
            }
        }
        val who = who()
        val mp = try {
            SpaceCore.mapFor(roleJson = roleJson(), worldJson = worldJson())
        } catch (e: Exception) {
            return "空间层出错：" + (e.message ?: e.javaClass.simpleName)
        }
        return try {
            val v = if (player) {
                SpaceCore.notePlayerMove(who, place, by, TimeScale.current,
                    java.time.LocalDateTime.now(), mp).second
            } else {
                SpaceCore.noteMove(who, place, by, TimeScale.current,
                    java.time.LocalDateTime.now(), mp).second
            }
            val head = (if (player) "你 → " else who + " → ") + place +
                    (if (v.need > 0) String.format(java.util.Locale.ROOT, "（%.0f 分钟）", v.need) else "")
            if (v.ok) head else "⚠ " + head + "\n" + v.why + "\n（照记了，下一轮注入会提醒她补一句路上）"
        } catch (e: Exception) {
            "位置记账失败：" + (e.message ?: e.javaClass.simpleName)
        }
    }
}
