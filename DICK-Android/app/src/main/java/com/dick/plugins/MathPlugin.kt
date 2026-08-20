package com.dick.plugins

import java.util.Locale
import kotlin.math.sqrt

/**
 * 数学运算 / 计算器 / Echo —— 移植自 Python math_plugin + pluginscalc + pluginsecho。
 * /calc 表达式求值（安全白名单）/ stats 统计 / rand 随机 / prime 质数 / echo 复读
 */
class MathPlugin : Plugin {
    override val name = "数学运算"
    override val version = "1.0"
    override val description = "计算 /calc、统计 /stats、随机 /rand、质数 /prime、复读 /echo"
    override var enabled = true

    override fun onCommand(command: String, args: String): String? = when (command) {
        "calc" -> calc(args)
        "stats" -> stats(args)
        "rand" -> rand(args)
        "prime" -> prime(args)
        "echo", "复读" -> args.ifBlank { "（空）" }
        else -> null
    }

    private fun calc(args: String): String? {
        val a = args.trim()
        if (a.isEmpty()) return "用法: /calc <表达式>，如 /calc (1+2)*3"
        return try {
            val v = SafeEval.eval(a)
            "$a = $v"
        } catch (e: Exception) {
            "计算错误: ${e.message}"
        }
    }

    private fun stats(args: String): String? {
        val nums = args.replace(',', ' ').split(Regex("\\s+")).mapNotNull { it.toDoubleOrNull() }
        if (nums.size < 2) return "至少需要2个数字：/stats 1 2 3"
        val n = nums.size
        val total = nums.sum()
        val mean = total / n
        val variance = nums.map { (it - mean) * (it - mean) }.sum() / n
        val std = sqrt(variance)
        val sorted = nums.sorted()
        val median = if (n % 2 == 1) sorted[n / 2] else (sorted[n / 2 - 1] + sorted[n / 2]) / 2
        return "📊 统计结果 (共 $n 个数):\n" +
            "总和: $total\n平均值: ${"%.4f".format(Locale.US, mean)}\n" +
            "中位数: ${"%.4f".format(Locale.US, median)}\n标准差: ${"%.4f".format(Locale.US, std)}\n" +
            "最小值: ${nums.min()} 最大值: ${nums.max()}"
    }

    private fun rand(args: String): String? {
        val parts = args.trim().split(Regex("\\s+")).mapNotNull { it.toIntOrNull() }
        return when (parts.size) {
            1 -> "随机数 (1~${parts[0]}): ${(1..parts[0]).random()}"
            2 -> if (parts[1] >= parts[0]) "随机数 (${parts[0]}~${parts[1]}): ${(parts[0]..parts[1]).random()}" else "下限应 ≤ 上限"
            else -> "用法: /rand <上限> 或 /rand <下限> <上限>"
        }
    }

    private fun prime(args: String): String? {
        val n = args.trim().toIntOrNull() ?: return "请输入有效的整数"
        if (n < 2) return "$n 不是质数"
        var i = 2
        while (i * i <= n) {
            if (n % i == 0) return "$n = $i × ${n / i}，不是质数"
            i++
        }
        return "$n 是质数 ✅"
    }
}

/** 安全表达式求值（白名单：数字/四则/括号/常用函数，不用反射/eval） */
object SafeEval {
    fun eval(expr: String): Double {
        val p = Parser(expr.replace(" ", ""))
        val v = p.parseExpression()
        if (p.pos < p.s.length) throw IllegalArgumentException("多余字符: ${p.s.substring(p.pos)}")
        return v
    }

    private class Parser(val s: String) {
        var pos = 0
        fun peek(): Char = if (pos < s.length) s[pos] else '\u0000'

        fun parseExpression(): Double {
            var v = parseTerm()
            while (true) {
                when (peek()) {
                    '+' -> { pos++; v += parseTerm() }
                    '-' -> { pos++; v -= parseTerm() }
                    else -> return v
                }
            }
        }

        fun parseTerm(): Double {
            var v = parseFactor()
            while (true) {
                when (peek()) {
                    '*' -> { pos++; v *= parseFactor() }
                    '/' -> { pos++; v /= parseFactor() }
                    else -> return v
                }
            }
        }

        fun parseFactor(): Double {
            val c = peek()
            if (c == '(') {
                pos++
                val v = parseExpression()
                if (peek() != ')') throw IllegalArgumentException("缺右括号")
                pos++
                return v
            }
            if (c == '-') { pos++; return -parseFactor() }
            if (c == '+') { pos++; return parseFactor() }
            if (c.isLetter()) {
                val start = pos
                while (pos < s.length && (s[pos].isLetter() || s[pos].isDigit())) pos++
                val fn = s.substring(start, pos)
                if (peek() != '(') throw IllegalArgumentException("未知函数 $fn")
                pos++
                val inner = parseExpression()
                if (peek() != ')') throw IllegalArgumentException("函数 $fn 缺右括号")
                pos++
                return when (fn) {
                    "abs" -> kotlin.math.abs(inner)
                    "round" -> kotlin.math.round(inner).toDouble()
                    "sqrt" -> sqrt(inner)
                    "pow" -> { // pow(x, y)
                        if (peek() == ',') { pos++; val y = parseExpression(); if (peek() == ')') pos++; Math.pow(inner, y) }
                        else Math.pow(inner, 2.0)
                    }
                    else -> throw IllegalArgumentException("未知函数 $fn")
                }
            }
            val start = pos
            while (pos < s.length && (s[pos].isDigit() || s[pos] == '.')) pos++
            if (start == pos) throw IllegalArgumentException("无法解析: '${s.substring(pos)}'")
            return s.substring(start, pos).toDouble()
        }
    }
}
