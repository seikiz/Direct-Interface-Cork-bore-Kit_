package com.dick.core

/**
 * 去中心化跑团会话引擎（Kotlin 版）—— 与 Python 端 trpg_session.py 行为对齐。
 *
 * 可内嵌到任意设备：谁持有本实例谁就能当 GM（本地推理，用 ChatEngine），
 * 成员设备只需连上该 GM 设备（HTTP）提交行动/看剧情。这样"跑团不依赖电脑脚本"：
 * 手机也能当 GM，电脑只是可选。
 *
 * 说明：真正的多人实时（状态广播/回合/成员直连）由上层 HTTP 壳（Workshop/trpg_server）
 * 负责；本类只承载"会话"的权威状态 + GM 推理（与 Python 端一致，易对齐测试）。
 */
class TrpgSession(
    private val engine: ChatEngine,
    var gm: String = "",
    pcs: List<String> = emptyList(),
    private val cardPrompt: (String) -> String = { "" },  // 角色卡 system_prompt 读取回调
) {
    val pcs = pcs.toMutableList()
    var turn: String = pcs.firstOrNull() ?: ""
    val story = mutableListOf<StoryEntry>()   // [{"actor","action","gm"}]
    val joined = mutableMapOf<String, String>() // pc名 -> 玩家名

    data class StoryEntry(val actor: String, val action: String, val gm: String)

    private val gmPrompt = (
        "【跑团模式 · 剧情为主】你是一名 TRPG 主持人(GM)，正在一场以剧情为核心的冒险。规则：" +
        "① 节奏由剧情驱动，把每个行动演成有画面感的场景并自然引出下一段剧情，不机械播报数值；" +
        "② 在节点给当前行动者 2-4 个下一步选项(GAL 分支)；③ 不确定性用掷骰(大成功/大失败/暴击要演出)；" +
        "④ 每个 PC 一张角色卡，贴合各自设定，绝不串戏；⑤ 保持世界观一致，让故事有因果、悬念、情感。" +
        "你用 GM 口吻叙述：先一句场景，再给该行动的结果，结尾给 2-4 个下一步选项。"
    )

    private fun buildSystem(actor: String): String {
        val parts = mutableListOf(gmPrompt)
        if (gm.isNotBlank()) parts += "（主持者 GM 卡：\n" + cardPrompt(gm) + "\n）"
        if (pcs.isNotEmpty()) {
            parts += "本次队伍(PC)：" + pcs.joinToString("、") + "。各角色设定如下："
            for (pc in pcs) {
                val sp = cardPrompt(pc)
                if (sp.isNotBlank()) parts += "■ $pc：\n$sp"
            }
        }
        if (story.isNotEmpty()) {
            parts += "【剧情回顾】"
            for (s in story.takeLast(12)) parts += "- ${s.actor}：${s.action} → 「${s.gm}」"
        }
        parts += "当前行动者：$actor，请围绕他/她的行动叙事并给 2-4 个下一步选项。"
        return parts.joinToString("\n\n")
    }

    /** GM 本地推理：构造 system 提示 + 用户消息，用 ChatEngine.complete 非流式叙述。 */
    private fun llm(system: String, user: String): String {
        return try {
            val chain = listOf(
                MessageNode(role = "system", content = system),
                MessageNode(role = "user", content = user),
            )
            engine.complete(chain, null) ?: "（GM 叙事失败：无返回）"
        } catch (e: Exception) {
            "（GM 叙事失败：${e.message ?: "异常"}）"
        }
    }

    // ---- 会话接口（与 P<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ython 端一致）----
    fun stateJson(): String {
        // 供 HTTP 壳返回；字段名与 Python 保持一致
        val o = J.Obj()
        o.fields["gm"] = J.Str(gm)
        o.fields["pcs"] = J.Arr(pcs.map { J.Str(it) }.toMutableList())
        o.fields["turn"] = J.Str(turn)
        val storyArr = J.Arr(mutableListOf())
        for (s in story.takeLast(40)) {
            val so = J.Obj()
            so.fields["actor"] = J.Str(s.actor)
            so.fields["action"] = J.Str(s.action)
            so.fields["gm"] = J.Str(s.gm)
            storyArr.items.add(so)
        }
        o.fields["story"] = storyArr
        val j = J.Obj(); joined.forEach { (k, v) -> j.fields[k] = J.Str(v) }
        o.fields["joined"] = j
        return JsonS.stringify(o)
    }

    fun setup(gm: String?, pcs: List<String>?): String {
        if (gm != null) this.gm = gm.trim()
        if (pcs != null) { this.pcs.clear(); pcs.forEach { if (it.isNotBlank()) this.pcs.add(it.trim()) } }
        if (this.pcs.isNotEmpty()) turn = this.pcs.first()
        return JsonS.stringify(J.Obj().apply { fields["ok"] = J.Str("true"); fields["turn"] = J.Str(turn) })
    }

    fun join(name: String, player: String = ""): Pair<String, String> {
        if (name !in pcs) return "error" to "该角色不在队伍中"
        joined[name] = player.ifBlank { "玩家" }
        return JsonS.stringify(J.Obj().apply { fields["ok"] = J.Str("true"); fields["turn"] = J.Str(turn) }) to "ok"
    }

    fun leave(name: String): String {
        if (name.isNotBlank()) joined.remove(name)
        return JsonS.stringify(J.Obj().apply { fields["ok"] = J.Str("true"); fields["joined"] = J.Str(joined.keys.joinToString(",")) })
    }

    fun act(actor: String, action: String): String? {
        var a = actor.trim(); val act = action.trim()
        if (act.isEmpty()) return null          // 空行动
        if (a.isEmpty()) a = turn.ifBlank { pcs.firstOrNull() ?: "你" }
        val system = buildSystem(a)
        val narration = llm(system, "${a}的行动：$act\n请叙述接下来发生什么，结尾给 2-4 个下一步选项。")
        story.add(StoryEntry(a, act, narration))
        if (pcs.isNotEmpty()) {
            val i = pcs.indexOf(a).let { if (it >= 0) it else 0 }
            turn = pcs[(i + 1) % pcs.size]
        }
        return JsonS.stringify(J.Obj().apply {
            fields["ok"] = J.Str("true"); fields["gm"] = J.Str(narration); fields["turn"] = J.Str(turn)
        })
    }
}
