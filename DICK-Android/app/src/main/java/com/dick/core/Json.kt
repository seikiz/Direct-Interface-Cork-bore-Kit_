package com.dick.core

/**
 * 极简 JSON 实现（零依赖）：
 *  - 解析：完整支持 字符串转义（含 uXXXX 与代理对）/ 数字 / 布尔 / null / 嵌套
 *  - 序列化：原始 UTF-8 直出（与 Python json.dump ensure_ascii=False 对齐）、
 *            整数字面量原样保留（95 不会变成 95.0）、2 空格缩进
 */
sealed class J {
    object Null : J()
    data class Bool(val v: Boolean) : J()
    data class Num(val v: Double, val raw: String = "") : J()
    data class Str(val v: String) : J()
    data class Arr(val items: MutableList<J> = mutableListOf()) : J()
    data class Obj(val fields: LinkedHashMap<String, J> = LinkedHashMap()) : J()

    fun obj(): Obj? = this as? Obj
    fun arr(): Arr? = this as? Arr
    fun str(): String? = (this as? Str)?.v
    fun int(): Int = ((this as? Num)?.v ?: 0.0).toInt()
    fun bool(): Boolean = (this as? Bool)?.v ?: false
    fun isNull(): Boolean = this is Null

    companion object {
        fun strOr(value: String?): J = if (value == null) Null else Str(value)
    }
}

object JsonS {

    fun parse(text: String): J {
        val p = Parser(text)
        val v = p.parseValue()
        p.skipWs()
        if (!p.atEnd()) throw IllegalArgumentException("JSON 解析：多余字符 @" + p.pos)
        return v
    }

    fun stringify(v: J, pretty: Boolean = false): String {
        val sb = StringBuilder()
        sb.writeJ(v, 0, pretty)
        return sb.toString()
    }

    // ---------- 解析器 ----------
    private class Parser(private val s: String) {
        var pos = 0

        fun atEnd(): Boolean = pos >= s.length
        fun peek(): Char? = if (pos < s.length) s[pos] else null

        fun skipWs() {
            while (pos < s.length) {
                val c = s[pos]
                if (c == ' ' || c.code == 9 || c.code == 10 || c.code == 13) pos++ else break
            }
        }

        private fun err(msg: String): IllegalArgumentException =
            IllegalArgumentException("JSON 解析 @" + pos + ": " + msg)

        fun parseValue(): J {
            skipWs()
            val c = peek() ?: throw err("意外结束")
            return when (c) {
                '{' -> parseObject()
                '[' -> parseArray()
                '"' -> J.Str(parseString())
                't' -> { expect("true"); J.Bool(true) }
                'f' -> { expect("false"); J.Bool(false) }
                'n' -> { expect("null"); J.Null }
                else -> parseNumber()
            }
        }

        private fun expect(word: String) {
            if (!s.startsWith(word, pos)) throw err("期望 " + word)
            pos += word.length
        }

        private fun parseObject(): J.Obj {
            pos++
            val o = J.Obj()
            skipWs()
            if (peek() == '}') { pos++; return o }
            while (true) {
                skipWs()
                if (peek() != '"') throw err("对象键必须是字符串")
                val key = parseString()
                skipWs()
                if (peek() != ':') throw err("缺少冒号")
                pos++
                o.fields[key] = parseValue()
                skipWs()
                when (peek()) {
                    ',' -> pos++
                    '}' -> { pos++; return o }
                    else -> throw err("对象缺少逗号或右括号")
                }
            }
        }

        private fun parseArray(): J.Arr {
            pos++
            val a = J.Arr()
            skipWs()
            if (peek() == ']') { pos++; return a }
            while (true) {
                a.items.add(parseValue())
                skipWs()
                when (peek()) {
                    ',' -> pos++
                    ']' -> { pos++; return a }
                    else -> throw err("数组缺少逗号或右括号")
                }
            }
        }

        private fun parseString(): String {
            pos++
            val sb = StringBuilder()
            while (true) {
                val ch = peek() ?: throw err("字符串未闭合")
                if (ch == '"') { pos++; return sb.toString() }
                if (ch.code != 92) { sb.append(ch); pos++; continue }
                pos++
                val e = peek() ?: throw err("转义未完成")
                pos++
                when (e) {
                    '"' -> sb.append('"')
                    '/' -> sb.append('/')
                    'b' -> sb.append(8.toChar())
                    'f' -> sb.append(12.toChar())
                    'n' -> sb.append(10.toChar())
                    'r' -> sb.append(13.toChar())
                    't' -> sb.append(9.toChar())
                    'u' -> {
                        val hex = s.substring(pos, (pos + 4).coerceAtMost(s.length))
                        if (hex.length != 4) throw err("u 转义非法")
                        pos += 4
                        val cp0 = hex.toIntOrNull(16) ?: throw err("u 转义非法")
                        var cp = cp0
                        if (cp in 0xD800..0xDBFF && pos + 6 <= s.length &&
                            s[pos].code == 92 && s[pos + 1] == 'u') {
                            val lowHex = s.substring(pos + 2, pos + 6)
                            val low = lowHex.toIntOrNull(16)
                            if (low != null && low in 0xDC00..0xDFFF) {
                                cp = 0x10000 + ((cp - 0xD800) shl 10) + (low - 0xDC00)
                                pos += 6
                            }
                        }
                        sb.appendCodePoint(cp)
                    }
                    else -> {
                        if (e.code == 92) sb.append(92.toChar())
                        else throw err("非法转义: " + e)
                    }
                }
            }
        }

        private fun parseNumber(): J.Num {
            val start = pos
            if (peek() == '-') pos++
            while (pos < s.length && s[pos].isDigit()) pos++
            if (pos < s.length && s[pos] == '.') {
                pos++
                while (pos < s.length && s[pos].isDigit()) pos++
            }
            if (pos < s.length && (s[pos] == 'e' || s[pos] == 'E')) {
                pos++
                if (pos < s.length && (s[pos] == '+' || s[pos] == '-')) pos++
                while (pos < s.length && s[pos].isDigit()) pos++
            }
            val raw = s.substring(start, pos)
            val d = raw.toDoubleOrNull() ?: throw err("非法数字: " + raw)
            return J.Num(d, raw)
        }
    }

    // ---------- 序列化 ----------
    private fun StringBuilder.writeJ(v: J, indent: Int, pretty: Boolean) {
        when (v) {
            is J.Null -> append("null")
            is J.Bool -> append(if (v.v) "true" else "false")
            is J.Num -> append(if (v.raw.isNotEmpty()) v.raw else formatNum(v.v))
            is J.Str -> writeStr(v.v)
            is J.Arr -> {
                append('[')
                if (v.items.isNotEmpty()) {
                    for ((i, item) in v.items.withIndex()) {
                        if (i > 0) append(',')
                        nl(indent + 1, pretty)
                        writeJ(item, indent + 1, pretty)
                    }
                    nl(indent, pretty)
                }
                append(']')
            }
            is J.Obj -> {
                append('{')
                if (v.fields.isNotEmpty()) {
                    var i = 0
                    for ((key, fv) in v.fields) {
                        if (i > 0) append(',')
                        i++
                        nl(indent + 1, pretty)
                        writeStr(key)
                        append(':')
                        if (pretty) append(' ')
                        writeJ(fv, indent + 1, pretty)
                    }
                    nl(indent, pretty)
                }
                append('}')
            }
        }
    }

    private fun StringBuilder.nl(indent: Int, pretty: Boolean) {
        if (pretty) {
            append(10.toChar())
            repeat(indent * 2) { append(' ') }
        }
    }

    private fun StringBuilder.writeStr(s: String) {
        append('"')
        for (ch in s) {
            when (ch.code) {
                34 -> { append(92.toChar()); append('"') }
                92 -> { append(92.toChar()); append(92.toChar()) }
                8 -> esc("b")
                9 -> esc("t")
                10 -> esc("n")
                12 -> esc("f")
                13 -> esc("r")
                else -> {
                    if (ch.code < 0x20) {
                        append(92.toChar())
                        append('u')
                        append(ch.code.toString(16).padStart(4, '0'))
                    } else {
                        append(ch)
                    }
                }
            }
        }
        append('"')
    }

    private fun StringBuilder.esc(c: String) {
        append(92.toChar())
        append(c)
    }

    private fun formatNum(d: Double): String {
        if (d == d.toLong().toDouble() && kotlin.math.abs(d) < 1e15) {
            return d.toLong().toString()
        }
        return d.toString()
    }
}
