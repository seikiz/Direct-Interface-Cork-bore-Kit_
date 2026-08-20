package com.dick.plugins

/**
 * 插件接口 —— 对应 Python 版插件钩子：
 *   on_load / on_command / on_message_send / on_message_received
 * P1 仅定义契约与注册表；P3 起移植 19 个内置插件。
 */
interface Plugin {
    val name: String
    val version: String
    val description: String
    var enabled: Boolean

    fun onLoad() {}

    /** 返回非 null 表示已处理该命令，返回值作为插件响应消息 */
    fun onCommand(command: String, args: String): String? = null

    /** 消息发送前处理；返回 null 表示拦截（不发送） */
    fun onMessageSend(userInput: String): String? = userInput

    /** AI 回复完成后回调（存档/记忆等重活在这里做） */
    fun onMessageReceived(userInput: String, aiReply: String) {}
}

class PluginRegistry {
    val plugins = mutableListOf<Plugin>()

    fun register(plugin: Plugin) {
        plugins.add(plugin)
        if (plugin.enabled) plugin.onLoad()
    }

    fun handleCommand(input: String): String? {
        if (!input.startsWith("/")) return null
        val parts = input.removePrefix("/").trim().split(" ", limit = 2)
        if (parts.isEmpty() || parts[0].isBlank()) return null
        val command = parts[0].lowercase()
        val args = parts.getOrNull(1) ?: ""
        for (plugin in plugins) {
            if (!plugin.enabled) continue
            try {
                plugin.onCommand(command, args)?.let { return it }
            } catch (_: Exception) {
                // 单个插件出错不影响其他插件
            }
        }
        return null
    }

    fun allEnabled(): List<Plugin> = plugins.filter { it.enabled }

    fun onMessageSend(input: String): String? {
        var current: String? = input
        for (plugin in plugins) {
            if (!plugin.enabled) continue
            try {
                current = plugin.onMessageSend(current ?: return null) ?: return null
            } catch (_: Exception) {
            }
        }
        return current
    }

    fun onMessageReceived(userInput: String, aiReply: String) {
        for (plugin in plugins) {
            if (!plugin.enabled) continue
            try {
                plugin.onMessageReceived(userInput, aiReply)
            } catch (_: Exception) {
            }
        }
    }
}
