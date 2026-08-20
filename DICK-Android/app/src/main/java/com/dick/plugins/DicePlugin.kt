package com.dick.plugins

import kotlin.random.Random

class DicePlugin : Plugin {
    override val name = "骰子大师"
    override val version = "1.0"
    override val description = "掷骰：/r 2d6、/d20、/dice"
    override var enabled = true

    override fun onCommand(command: String, args: String): String? {
        if (command == "dice") {
            return "🎲 骰子命令：" + 10.toChar() +
                "  /r 2d6  掷 2 个六面骰" + 10.toChar() +
                "  /r 1d20 掷 1 个二十面骰" + 10.toChar() +
                "  /d20    快捷 d20"
        }
        if (command == "d20") return roll(1, 20)
        if (command == "r") return parseRoll(args.trim())
        return null
    }

    private fun parseRoll(spec: String): String? {
        val m = Regex("""^(\d*)d(\d+)([+-]\d+)?$""").find(spec.trim().lowercase()) ?: return null
        val count = m.groupValues[1].ifEmpty { "1" }.toIntOrNull() ?: 1
        val sides = m.groupValues[2].toIntOrNull() ?: return null
        val mod = m.groupValues[3].ifEmpty { "0" }.toIntOrNull() ?: 0
        if (count < 1 || count > 100 || sides < 1 || sides > 1000) return "⚠️ 骰子参数超出范围"
        return roll(count, sides, mod)
    }

    private fun roll(count: Int, sides: Int, mod: Int = 0): String {
        val results = (1..count).map { Random.nextInt(1, sides + 1) }
        val total = results.sum() + mod
        return "🎲 " + count + "d" + sides + " = [" + results.joinToString(", ") + "]" +
            (if (mod != 0) (" " + (if (mod > 0) "+" else "") + mod) else "") +
            " = **" + total + "**"
    }
}
