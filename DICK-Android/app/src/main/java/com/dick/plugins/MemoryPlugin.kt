package com.dick.plugins

import com.dick.core.AppEnv
import com.dick.core.J
import com.dick.core.JsonS
import java.io.File

/** 记忆链：持久化对话历史到 memory/ 目录，/memory recall 回溯注入 */
class MemoryPlugin : Plugin {
    override val name = "记忆链"
    override val version = "1.0"
    override val description = "/memory 保存与回溯对话历史"
    override var enabled = true

    private val turns = mutableListOf<Pair<String, String>>()
    private var recalled = ""

    private fun file(): File = File(AppEnv.memoryDir(), "memory.json")

    fun load() {
        try {
            if (!file().exists()) return
            val root = JsonS.parse(file().readText(Charsets.UTF_8)) as? J.Obj ?: return
            (root.fields["turns"] as? J.Arr)?.items?.forEach { t ->
                (t as? J.Obj)?.let { o ->
                    val u = o.fields["user"]?.str() ?: ""
                    val a = o.fields["assistant"]?.str() ?: ""
                    turns.add(u to a)
                }
            }
        } catch (_: Exception) {
        }
    }

    fun save() {
        try {
            val arr = J.Arr()
            for ((u, a) in turns.takeLast(200)) {
                val o = J.Obj()
                o.fields["user"] = J.Str(u)
                o.fields["assistant"] = J.Str(a)
                arr.items.add(o)
            }
            val root = J.Obj()
            root.fields["turns"] = arr
            file().writeText(JsonS.stringify(root, pretty = true), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    override fun onMessageReceived(userInput: String, aiReply: String) {
        if (userInput.isBlank() || aiReply.isBlank()) return
        turns.add(userInput to aiReply)
        if (turns.size % 5 == 0) save()
    }

    override fun onCommand(command: String, args: String): String? {
        if (command != "memory") return null
        val arg = args.trim().lowercase()
        if (arg.isEmpty()) {
            return "🧠 记忆链：共 " + turns.size + " 轮对话（memory/memory.json）" + 10.toChar() +
                "  /memory recall [N]  回溯最近 N 轮注入下次对话" + 10.toChar() +
                "  /memory summary     查看已回溯内容" + 10.toChar() +
                "  /memory clear       清除回溯"
        }
        if (arg.startsWith("recall")) {
            val n = arg.removePrefix("recall").trim().toIntOrNull() ?: 5
            val take = turns.takeLast(n.coerceIn(1, 50))
            if (take.isEmpty()) return "🧠 暂无历史可回溯"
            recalled = take.joinToString(10.toChar().toString()) { (u, a) -> "用户：" + u + 10.toChar() + "AI：" + a }
            return "🧠 已回溯最近 " + take.size + " 轮对话（下次发送自动注入）"
        }
        if (arg == "summary") {
            return if (recalled.isBlank()) "🧠 当前没有回溯内容" else recalled
        }
        if (arg == "clear") {
            recalled = ""
            return "🧠 已清除回溯内容"
        }
        return null
    }

    override fun contextInjection(): String =
        if (recalled.isBlank()) "" else "【记忆回溯】" + 10.toChar() + recalled
}
