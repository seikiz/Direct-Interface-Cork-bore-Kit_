package com.dick.core

import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.random.Random

/** 战斗公式求值（从 MechanicsEngine.kt 拆出，见 tools/ 的拆分记录）。
 *  白名单递归下降：变量 + 四则 + 括号 + max/min/floor/ceil/abs/random/randint
 */

/** 战斗公式求值（白名单递归下降：变量 + 四则 + 括号 + max<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌/min/floor/ceil/abs/random/randint） */
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
