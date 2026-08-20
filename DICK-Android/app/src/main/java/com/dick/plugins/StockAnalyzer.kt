package com.dick.plugins

import com.dick.core.J
import com.dick.core.JsonS
import kotlin.math.abs
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.sqrt

/**
 * A股炒股要素计算（免费数据源，免 Key）——移植自 Python stock_analysis.py：
 * 腾讯行情（GBK）+ 腾讯前复权日K（JSON）
 * 指标：MA/EMA/MACD/KDJ/RSI/BOLL/WR/ATR/年化波动率/量能/支撑压力/估值
 */
object StockAnalyzer {

    data class Bar(val date: String, val open: Double, val close: Double, val high: Double, val low: Double, val volume: Double)

    fun normalizeCode(code: String): String {
        var c = code.trim().lowercase().replace(" ", "")
        if (c.isEmpty()) return ""
        val m = Regex("^(sh|sz|bj)([0-9]{6})$").find(c)
        if (m != null) return m.groupValues[1] + m.groupValues[2]
        if (Regex("^[0-9]{6}$").matches(c)) {
            val prefix = when (c[0]) {
                '6' -> "sh"
                '0', '3' -> "sz"
                else -> "bj"
            }
            return prefix + c
        }
        return c
    }

    fun fetchQuote(code: String): Map<String, Any> {
        val raw = WebFetch.fetchRaw("https://qt.gtimg.cn/q=" + normalizeCode(code), "GBK", 10000)
        val f = raw.split("~")
        if (f.size < 50) throw IllegalArgumentException("未找到该股票，请用 600519 或 sh600519 格式")
        fun num(i: Int): Double = f.getOrNull(i)?.toDoubleOrNull() ?: 0.0
        fun str(i: Int): String = f.getOrNull(i) ?: ""
        return mapOf(
            "name" to str(1), "code" to str(2), "price" to num(3), "prev_close" to num(4),
            "open" to num(5), "volume_hand" to num(6), "time" to str(30),
            "change" to num(31), "pct" to num(32), "high" to num(33), "low" to num(34),
            "amount_wan" to num(37), "turnover" to num(38), "pe_ttm" to num(39),
            "amplitude" to num(43), "float_cap_yi" to num(44), "total_cap_yi" to num(45),
            "pb" to num(46), "vol_ratio" to num(49), "pe_dyn" to num(52),
            "pe_static" to num(53),
        )
    }

    fun fetchKline(code: String, count: Int = 160): List<Bar> {
        val codeNorm = normalizeCode(code)
        val url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + codeNorm + ",day,,," + count + ",qfq"
        val root = JsonS.parse(WebFetch.fetchHtml(url, 15000)) as? J.Obj ?: return emptyList()
        val data = root.fields["data"] as? J.Obj
        val node = data?.fields?.get(codeNorm) as? J.Obj
        val rows = (node?.fields?.get("qfqday") ?: node?.fields?.get("day")) as? J.Arr
        val out = mutableListOf<Bar>()
        rows?.items?.forEach { r ->
            val a = r as? J.Arr ?: return@forEach
            if (a.items.size < 6) return@forEach
            out.add(Bar(
                date = a.items[0].str() ?: "",
                open = numOf(a.items.getOrNull(1)),
                close = numOf(a.items.getOrNull(2)),
                high = numOf(a.items.getOrNull(3)),
                low = numOf(a.items.getOrNull(4)),
                volume = numOf(a.items.getOrNull(5)),
            ))
        }
        return out
    }

    /** 腾讯K线把数字返回成字符串，这里兼容两种类型 */
    private fun numOf(v: J?): Double {
        if (v is J.Num) return v.v
        if (v is J.Str) return v.v.toDoubleOrNull() ?: 0.0
        return 0.0
    }

    // ---------- 指标 ----------
    private fun sma(values: List<Double>, n: Int): List<Double?> {
        val out = arrayOfNulls<Double>(values.size)
        if (values.size >= n) {
            var s = values.take(n).sum()
            out[n - 1] = s / n
            for (i in n until values.size) {
                s += values[i] - values[i - n]
                out[i] = s / n
            }
        }
        return out.toList()
    }

    private fun ema(values: List<Double>, n: Int): List<Double?> {
        val out = arrayOfNulls<Double>(values.size)
        if (values.isEmpty()) return out.toList()
        val k = 2.0 / (n + 1)
        var prev = values[0]
        out[0] = prev
        for (i in 1 until values.size) {
            prev = values[i] * k + prev * (1 - k)
            out[i] = prev
        }
        return out.toList()
    }

    private fun macd(values: List<Double>): Triple<List<Double?>, List<Double?>, List<Double?>> {
        val e12 = ema(values, 12)
        val e26 = ema(values, 26)
        val dif = e12.indices.map { i -> (e12[i] ?: 0.0) - (e26[i] ?: 0.0) }
        val dea = ema(dif, 9)
        val hist = dif.indices.map { i -> ((dif[i] - (dea[i] ?: 0.0)) * 2) }
        return Triple(dif.map { it }, dea, hist.map { it })
    }

    private fun kdj(bars: List<Bar>, n: Int = 9): Triple<List<Double>, List<Double>, List<Double>> {
        val ks = mutableListOf<Double>()
        val ds = mutableListOf<Double>()
        val js = mutableListOf<Double>()
        var kPrev = 50.0
        var dPrev = 50.0
        for (i in bars.indices) {
            val from = max(0, i - n + 1)
            var lo = Double.MAX_VALUE
            var hi = Double.MIN_VALUE
            for (j in from..i) {
                if (bars[j].low < lo) lo = bars[j].low
                if (bars[j].high > hi) hi = bars[j].high
            }
            val rsv = if (hi == lo) 50.0 else (bars[i].close - lo) / (hi - lo) * 100
            kPrev = kPrev * 2 / 3 + rsv / 3
            dPrev = dPrev * 2 / 3 + kPrev / 3
            val j = 3 * kPrev - 2 * dPrev
            ks.add(kPrev)
            ds.add(dPrev)
            js.add(j)
        }
        return Triple(ks, ds, js)
    }

    private fun rsi(values: List<Double>, n: Int): List<Double?> {
        val out = arrayOfNulls<Double>(values.size)
        val gains = mutableListOf<Double>()
        val losses = mutableListOf<Double>()
        for (i in 1 until values.size) {
            val d = values[i] - values[i - 1]
            gains.add(max(d, 0.0))
            losses.add(max(-d, 0.0))
        }
        if (gains.size < n) return out.toList()
        var ag = gains.take(n).sum() / n
        var al = losses.take(n).sum() / n
        out[n] = if (al == 0.0) 100.0 else 100 - 100 / (1 + ag / al)
        for (i in n + 1 until values.size) {
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
            out[i] = if (al == 0.0) 100.0 else 100 - 100 / (1 + ag / al)
        }
        return out.toList()
    }

    private fun boll(values: List<Double>, n: Int = 20): Triple<List<Double?>, List<Double?>, List<Double?>> {
        val mid = sma(values, n)
        val up = arrayOfNulls<Double>(values.size)
        val lo = arrayOfNulls<Double>(values.size)
        for (i in n - 1 until values.size) {
            val window = values.subList(i - n + 1, i + 1)
            val m = mid[i] ?: 0.0
            var sumSq = 0.0
            for (v in window) sumSq += (v - m) * (v - m)
            val sd = sqrt(sumSq / n)
            up[i] = m + 2 * sd
            lo[i] = m - 2 * sd
        }
        return Triple(up.toList(), mid, lo.toList())
    }

    private fun atr(bars: List<Bar>, n: Int = 14): List<Double?> {
        val trs = mutableListOf(0.0)
        for (i in 1 until bars.size) {
            val h = bars[i].high
            val l = bars[i].low
            val pc = bars[i - 1].close
            trs.add(max(h - l, max(abs(h - pc), abs(l - pc))))
        }
        val out = arrayOfNulls<Double>(trs.size)
        if (trs.size >= n) {
            var prev = trs.subList(1, n + 1).sum() / n
            out[n] = prev
            for (i in n + 1 until trs.size) {
                prev = (prev * (n - 1) + trs[i]) / n
                out[i] = prev
            }
        }
        return out.toList()
    }

    private fun wr(bars: List<Bar>, n: Int = 14): List<Double?> {
        val out = arrayOfNulls<Double>(bars.size)
        for (i in n - 1 until bars.size) {
            val window = bars.subList(i - n + 1, i + 1)
            var hi = Double.MIN_VALUE
            var lo = Double.MAX_VALUE
            for (b in window) {
                if (b.high > hi) hi = b.high
                if (b.low < lo) lo = b.low
            }
            out[i] = if (hi == lo) 100.0 else (hi - bars[i].close) / (hi - lo) * 100
        }
        return out.toList()
    }

    private fun volatility(values: List<Double>, n: Int = 20): Double {
        if (values.size < n + 1) return 0.0
        val rets = mutableListOf<Double>()
        for (i in values.size - n until values.size) {
            val prev = values[i - 1]
            if (prev > 0) rets.add(ln(values[i] / prev))
        }
        if (rets.size < 2) return 0.0
        val m = rets.sum() / rets.size
        var sumSq = 0.0
        for (r in rets) sumSq += (r - m) * (r - m)
        val sd = sqrt(sumSq / (rets.size - 1))
        return sd * sqrt(252.0) * 100
    }

    private fun last(vals: List<Double?>): Double? {
        for (i in vals.indices.reversed()) {
            vals[i]?.let { return it }
        }
        return null
    }

    private fun crossUp(a: List<Double?>, b: List<Double?>, lookback: Int = 3): Int {
        for (i in 1..lookback) {
            val j = a.size - i
            if (j < 1) break
            val a0 = a[j - 1] ?: continue
            val b0 = b[j - 1] ?: continue
            val a1 = a[j] ?: continue
            val b1 = b[j] ?: continue
            if (a0 <= b0 && a1 > b1) return i
        }
        return 0
    }

    private fun crossDown(a: List<Double?>, b: List<Double?>, lookback: Int = 3): Int {
        for (i in 1..lookback) {
            val j = a.size - i
            if (j < 1) break
            val a0 = a[j - 1] ?: continue
            val b0 = b[j - 1] ?: continue
            val a1 = a[j] ?: continue
            val b1 = b[j] ?: continue
            if (a0 >= b0 && a1 < b1) return i
        }
        return 0
    }

    private fun fmt(v: Double?, nd: Int = 2): String {
        if (v == null) return "--"
        return ("%." + nd + "f").format(v)
    }

    // ---------- 全市场列表 / 筛选 ----------
    data class MarketRow(
        val code: String, val name: String, val price: Double, val pct: Double,
        val change: Double, val volumeHand: Double, val amount: Double, val amplitude: Double,
        val turnover: Double, val pe: Double, val volRatio: Double, val high: Double,
        val low: Double, val open: Double, val prevClose: Double, val totalCapYi: Double,
        val floatCapYi: Double, val pb: Double, val mainInflowWan: Double,
    )

    @Volatile
    var lastSource = "eastmoney"
        private set

    private fun numJ(v: J?): Double = numOf(v)

    private fun eastmoneyList(sortField: String, ascend: Boolean, limit: Int): List<MarketRow> {
        val hosts = listOf(
            "https://push2.eastmoney.com",
            "https://82.push2.eastmoney.com",
            "https://17.push2.eastmoney.com",
        )
        val rows = mutableListOf<MarketRow>()
        val seen = mutableSetOf<String>()
        var pn = 1
        while (rows.size < limit && pn <= 40) {
            val pz = if (limit > 200) 200 else limit
            val host = hosts[(pn - 1) % hosts.size]
            val url = host + "/api/qt/clist/get?pn=" + pn + "&pz=" + pz +
                "&po=" + (if (ascend) "0" else "1") + "&np=1&fltt=2&invt=2&fid=" + sortField +
                "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048" +
                "&fields=f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21,f23,f62"
            val root = try {
                JsonS.parse(WebFetch.fetchHtml(url, 20000)) as? J.Obj
            } catch (_: Exception) {
                null
            }
            val diff = (root?.fields?.get("data") as? J.Obj)?.fields?.get("diff") as? J.Arr
            if (diff == null || diff.items.isEmpty()) break
            for (r in diff.items) {
                val o = r as? J.Obj ?: continue
                val code = o.fields["f12"]?.str() ?: ""
                if (code.isEmpty() || code in seen) continue
                seen.add(code)
                rows.add(MarketRow(
                    code = code,
                    name = o.fields["f14"]?.str() ?: "",
                    price = numJ(o.fields["f2"]),
                    pct = numJ(o.fields["f3"]),
                    change = numJ(o.fields["f4"]),
                    volumeHand = numJ(o.fields["f5"]),
                    amount = numJ(o.fields["f6"]),
                    amplitude = numJ(o.fields["f7"]),
                    turnover = numJ(o.fields["f8"]),
                    pe = numJ(o.fields["f9"]),
                    volRatio = numJ(o.fields["f10"]),
                    high = numJ(o.fields["f15"]),
                    low = numJ(o.fields["f16"]),
                    open = numJ(o.fields["f17"]),
                    prevClose = numJ(o.fields["f18"]),
                    totalCapYi = numJ(o.fields["f20"]) / 1e8,
                    floatCapYi = numJ(o.fields["f21"]) / 1e8,
                    pb = numJ(o.fields["f23"]),
                    mainInflowWan = numJ(o.fields["f62"]) / 1e4,
                ))
            }
            if (diff.items.size < pz) break
            pn++
        }
        return rows
    }

    private val sinaKeyRe = Regex("([{,][ ]*)([A-Za-z_][A-Za-z0-9_]*)([ ]*:)")

    private fun sinaList(sortField: String, ascend: Boolean, limit: Int): List<MarketRow> {
        val sort = when (sortField) {
            "f6" -> "amount"
            "f8" -> "turnoverratio"
            else -> "changepercent"
        }
        val rows = mutableListOf<MarketRow>()
        val seen = mutableSetOf<String>()
        var page = 1
        while (rows.size < limit && page <= 80) {
            val num = if (limit - rows.size > 80) 80 else limit - rows.size
            val url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/" +
                "Market_Center.getHQNodeData?page=" + page + "&num=" + num +
                "&sort=" + sort + "&asc=" + (if (ascend) "1" else "0") +
                "&node=hs_a&symbol=&_s_r_a=page"
            val quoted = try {
                val raw = WebFetch.fetchRaw(url, "UTF-8", 15000)
                sinaKeyRe.replace(raw) { m -> m.groupValues[1] + "\"" + m.groupValues[2] + "\"" + m.groupValues[3] }
            } catch (_: Exception) {
                ""
            }
            if (quoted.isEmpty()) break
            val arr = JsonS.parse(quoted) as? J.Arr
            if (arr == null || arr.items.isEmpty()) break
            for (r in arr.items) {
                val o = r as? J.Obj ?: continue
                val code = o.fields["code"]?.str() ?: ""
                if (code.isEmpty() || code in seen) continue
                seen.add(code)
                val prev = numJ(o.fields["settlement"])
                rows.add(MarketRow(
                    code = code,
                    name = o.fields["name"]?.str() ?: "",
                    price = numJ(o.fields["trade"]),
                    pct = numJ(o.fields["changepercent"]),
                    change = numJ(o.fields["pricechange"]),
                    volumeHand = numJ(o.fields["volume"]) / 100,
                    amount = numJ(o.fields["amount"]),
                    amplitude = if (prev > 0) (numJ(o.fields["high"]) - numJ(o.fields["low"])) / prev * 100 else 0.0,
                    turnover = numJ(o.fields["turnoverratio"]),
                    pe = numJ(o.fields["per"]),
                    volRatio = 0.0,
                    high = numJ(o.fields["high"]),
                    low = numJ(o.fields["low"]),
                    open = numJ(o.fields["open"]),
                    prevClose = prev,
                    totalCapYi = numJ(o.fields["mktcap"]) / 10000,
                    floatCapYi = numJ(o.fields["nmc"]) / 10000,
                    pb = numJ(o.fields["pb"]),
                    mainInflowWan = 0.0,
                ))
            }
            if (arr.items.size < num) break
            page++
        }
        return rows
    }

    fun fetchMarketList(sortField: String = "f3", ascend: Boolean = false, limit: Int = 6000): List<MarketRow> {
        val em = try {
            eastmoneyList(sortField, ascend, limit)
        } catch (_: Exception) {
            emptyList()
        }
        if (em.isNotEmpty()) {
            lastSource = "eastmoney"
            return em
        }
        lastSource = "sina"
        return sinaList(sortField, ascend, limit)
    }

    private fun rowText(i: Int, r: MarketRow): String {
        return i.toString() + ". " + r.name + "（" + r.code + "）现价 " + fmt(r.price) +
            "｜涨幅 " + fmt(r.pct) + "%｜换手 " + fmt(r.turnover) + "%｜量比 " + fmt(r.volRatio) +
            "｜市盈 " + fmt(r.pe) + "｜市值 " + fmt(r.totalCapYi) + "亿｜主力净流入 " + fmt(r.mainInflowWan) + "万"
    }

    fun marketListReport(n: Int = 20, losers: Boolean = false): String {
        val rows = fetchMarketList("f3", losers, n.coerceIn(1, 100))
        val sb = StringBuilder()
        sb.append(if (losers) "📉 A股跌幅榜 Top" else "📈 A股涨幅榜 Top")
        sb.append(rows.size).append("（沪深北全市场，按涨跌幅排序）").append(10.toChar())
        var i = 1
        for (r in rows) {
            sb.append(rowText(i, r)).append(10.toChar())
            i++
        }
        return sb.toString().trim()
    }

    private data class Cond(val key: String, val op: String, val value: Double)

    private val condRe = Regex("([一-龥]+)(>=|<=|>|<)(-?[0-9.]+)")

    private fun condKey(key: String): String = when (key) {
        "涨幅" -> "pct"
        "换手" -> "turnover"
        "量比" -> "volRatio"
        "市盈" -> "pe"
        "市值" -> "totalCapYi"
        "流入" -> "mainInflowWan"
        else -> ""
    }

    private fun match(r: MarketRow, c: Cond): Boolean {
        val v = when (condKey(c.key)) {
            "pct" -> r.pct
            "turnover" -> r.turnover
            "volRatio" -> r.volRatio
            "pe" -> r.pe
            "totalCapYi" -> r.totalCapYi
            "mainInflowWan" -> r.mainInflowWan
            else -> return false
        }
        return when (c.op) {
            ">" -> v > c.value
            "<" -> v < c.value
            ">=" -> v >= c.value
            "<=" -> v <= c.value
            else -> false
        }
    }

    fun screenReport(text: String, limit: Int = 50): String {
        val conds = condRe.findAll(text).map { Cond(it.groupValues[1], it.groupValues[2], it.groupValues[3].toDoubleOrNull() ?: 0.0) }.toList()
        if (conds.isEmpty()) {
            return "🔍 全市场筛选用法：/全市场 涨幅>5 换手>10 量比>2 市盈<50 市值<500 流入>1000" + 10.toChar() +
                "  指标：涨幅% / 换手% / 量比 / 市盈 / 市值(亿) / 流入(主力净流入,万)"
        }
        val rows = fetchMarketList("f3", false, 6000)
        var pctFloor: Double? = null
        for (c in conds) {
            if (c.key == "涨幅" && (c.op == ">" || c.op == ">=")) pctFloor = c.value
        }
        val out = mutableListOf<MarketRow>()
        for (r in rows) {
            if (pctFloor != null && r.pct < pctFloor - 0.01) break
            var ok = true
            for (c in conds) {
                if (!match(r, c)) {
                    ok = false
                    break
                }
            }
            if (ok) out.add(r)
            if (out.size >= limit) break
        }
        val sb = StringBuilder()
        val condText = conds.joinToString(" ") { it.key + it.op + fmt(it.value) }
        sb.append("🔍 全市场筛选（条件：").append(condText).append("）命中 ")
        sb.append(out.size).append(" 只（显示前 ").append(minOf(limit, out.size)).append("）").append(10.toChar())
        var i = 1
        for (r in out) {
            sb.append(rowText(i, r)).append(10.toChar())
            i++
        }
        if (out.isEmpty()) sb.append("（无匹配，放宽条件试试）").append(10.toChar())
        if (lastSource == "sina" && conds.any { it.key == "量比" || it.key == "流入" }) {
            sb.append("⚠️ 当前使用新浪备用源（东财被限流），量比/主力净流入字段不可用")
        }
        return sb.toString().trim()
    }

    fun analyze(code: String): String {
        val quote = fetchQuote(code)
        val bars = fetchKline(code, 160)
        if (bars.size < 30) throw IllegalArgumentException("K线数据不足（仅 " + bars.size + " 根），无法计算指标")
        val closes = bars.map { it.close }
        val vols = bars.map { it.volume }
        val price = quote["price"] as? Double ?: 0.0

        val ma5 = sma(closes, 5)
        val ma10 = sma(closes, 10)
        val ma20 = sma(closes, 20)
        val ma60 = sma(closes, 60)
        val (dif, dea, hist) = macd(closes)
        val (ks, ds, js) = kdj(bars)
        val r6 = rsi(closes, 6)
        val r12 = rsi(closes, 12)
        val r24 = rsi(closes, 24)
        val (bUp, bMid, bLo) = boll(closes)
        val a = atr(bars)
        val w = wr(bars)
        val vola = volatility(closes)

        val signs = mutableListOf<Triple<String, String, Int>>()
        val ma5v = last(ma5)
        val ma10v = last(ma10)
        val ma20v = last(ma20)
        val ma60v = last(ma60)
        if (ma5v != null && ma10v != null && ma20v != null) {
            when {
                price > ma5v && ma5v > ma10v && ma10v > ma20v -> signs.add(Triple("均线", "多头排列", 1))
                price < ma5v && ma5v < ma10v && ma10v < ma20v -> signs.add(Triple("均线", "空头排列", -1))
                else -> signs.add(Triple("均线", "缠绕", 0))
            }
        }
        if (crossUp(dif, dea) > 0) signs.add(Triple("MACD", "金叉", 1))
        else if (crossDown(dif, dea) > 0) signs.add(Triple("MACD", "死叉", -1))
        else signs.add(Triple("MACD", "延续", if ((last(dif) ?: 0.0) > (last(dea) ?: 0.0)) 1 else -1))
        if (crossUp(ks, ds) > 0) signs.add(Triple("KDJ", "金叉", 1))
        else if (crossDown(ks, ds) > 0) signs.add(Triple("KDJ", "死叉", -1))
        else {
            val jv = last(js) ?: 0.0
            signs.add(Triple("KDJ", if (jv > 100) "超买" else if (jv < 0) "超卖" else "中性", if (jv > 100) -1 else if (jv < 0) 1 else 0))
        }
        val r6v = last(r6) ?: 0.0
        signs.add(Triple("RSI", if (r6v > 70) "超买" else if (r6v < 30) "超卖" else "中性", if (r6v > 70) -1 else if (r6v < 30) 1 else 0))
        val bup = last(bUp)
        val blo = last(bLo)
        if (bup != null && blo != null && bup > blo) {
            val pos = (price - blo) / (bup - blo) * 100
            signs.add(Triple("BOLL", if (pos > 80) "强势区" else if (pos < 20) "弱势区" else "中轨区", if (pos > 80) 1 else if (pos < 20) -1 else 0))
        }
        val avg5 = if (vols.size >= 5) vols.takeLast(5).sum() / 5 else 0.0
        val avg10 = if (vols.size >= 10) vols.takeLast(10).sum() / 10 else 0.0
        signs.add(Triple("量能", if (avg5 > avg10 * 1.3) "放量" else if (avg5 < avg10 * 0.7) "缩量" else "平量",
            if (avg5 > avg10 * 1.3) 1 else if (avg5 < avg10 * 0.7) -1 else 0))

        var lo20 = Double.MAX_VALUE
        var hi20 = Double.MIN_VALUE
        var lo60 = Double.MAX_VALUE
        var hi60 = Double.MIN_VALUE
        var loAll = Double.MAX_VALUE
        var hiAll = Double.MIN_VALUE
        for (i in bars.indices) {
            val b = bars[i]
            if (b.low < loAll) loAll = b.low
            if (b.high > hiAll) hiAll = b.high
            if (i >= bars.size - 20) {
                if (b.low < lo20) lo20 = b.low
                if (b.high > hi20) hi20 = b.high
            }
            if (i >= bars.size - 60) {
                if (b.low < lo60) lo60 = b.low
                if (b.high > hi60) hi60 = b.high
            }
        }

        val bullish = signs.count { it.third > 0 }
        val bearish = signs.count { it.third < 0 }
        val neutral = signs.size - bullish - bearish
        val verdict = when {
            bearish >= 4 || (bearish > bullish && bearish >= 3) -> "偏空，注意风险"
            bullish >= 4 || (bullish > bearish && bullish >= 3) -> "偏多，可关注"
            else -> "多空胶着，观望为主"
        }

        val sb = StringBuilder()
        sb.append("📊 ").append(quote["name"]).append("（").append(quote["code"]).append("）炒股要素分析").append(10.toChar())
        sb.append("⏱ 行情时间 ").append(quote["time"]).append(10.toChar())
        sb.append("【实时行情】现价 ").append(fmt(price)).append("｜涨跌 ").append(fmt(quote["change"] as? Double))
            .append("（").append(fmt(quote["pct"] as? Double)).append("%）｜今开 ").append(fmt(quote["open"] as? Double))
            .append("｜最高 ").append(fmt(quote["high"] as? Double)).append("｜最低 ").append(fmt(quote["low"] as? Double)).append(10.toChar())
        sb.append("  成交量 ").append(fmt((quote["volume_hand"] as? Double ?: 0.0) / 10000)).append(" 万手｜成交额 ")
            .append(fmt((quote["amount_wan"] as? Double ?: 0.0) / 10000)).append(" 亿｜换手 ")
            .append(fmt(quote["turnover"] as? Double)).append("%｜量比 ").append(fmt(quote["vol_ratio"] as? Double))
            .append("｜振幅 ").append(fmt(quote["amplitude"] as? Double)).append("%").append(10.toChar())
        sb.append("【估值】市盈(动) ").append(fmt(quote["pe_dyn"] as? Double)).append("｜市盈(静) ")
            .append(fmt(quote["pe_static"] as? Double)).append("｜市净率 ").append(fmt(quote["pb"] as? Double))
            .append("｜总市值 ").append(fmt(quote["total_cap_yi"] as? Double)).append(" 亿｜流通市值 ")
            .append(fmt(quote["float_cap_yi"] as? Double)).append(" 亿").append(10.toChar())
        sb.append("【均线】MA5 ").append(fmt(ma5v)).append("｜MA10 ").append(fmt(ma10v)).append("｜MA20 ")
            .append(fmt(ma20v)).append("｜MA60 ").append(fmt(ma60v)).append("｜现价相对 MA20：")
            .append(fmt(if (ma20v != null && ma20v > 0) (price / ma20v - 1) * 100 else 0.0)).append("%").append(10.toChar())
        sb.append("【MACD】DIF ").append(fmt(last(dif))).append("｜DEA ").append(fmt(last(dea))).append("｜柱 ")
            .append(fmt(last(hist))).append(10.toChar())
        sb.append("【KDJ】K ").append(fmt(last(ks))).append("｜D ").append(fmt(last(ds))).append("｜J ")
            .append(fmt(last(js))).append(10.toChar())
        sb.append("【RSI】RSI6 ").append(fmt(last(r6))).append("｜RSI12 ").append(fmt(last(r12))).append("｜RSI24 ")
            .append(fmt(last(r24))).append(10.toChar())
        sb.append("【BOLL】上轨 ").append(fmt(bup)).append("｜中轨 ").append(fmt(last(bMid))).append("｜下轨 ")
            .append(fmt(blo)).append(10.toChar())
        sb.append("【WR/ATR/波动率】WR14 ").append(fmt(last(w))).append("｜ATR14 ").append(fmt(last(a)))
            .append("（占现价 ").append(fmt(if (price > 0) (last(a) ?: 0.0) / price * 100 else 0.0)).append("%）｜20日年化波动率 ")
            .append(fmt(vola)).append("%").append(10.toChar())
        sb.append("【支撑/压力】20日 支撑 ").append(fmt(lo20)).append(" / 压力 ").append(fmt(hi20))
            .append("｜60日 支撑 ").append(fmt(lo60)).append(" / 压力 ").append(fmt(hi60))
            .append("｜区间内 ").append(fmt(loAll)).append(" - ").append(fmt(hiAll)).append(10.toChar())
        sb.append("【信号】")
        for ((idx, s) in signs.withIndex()) {
            if (idx > 0) sb.append("；")
            sb.append(s.first).append("：").append(s.second)
            if (s.third > 0) sb.append("↑") else if (s.third < 0) sb.append("↓")
        }
        sb.append(10.toChar())
        sb.append("【汇总】偏多 ").append(bullish).append("｜中性 ").append(neutral).append("｜偏空 ")
            .append(bearish).append(" → ").append(verdict).append(10.toChar())
        sb.append("⚠️ 以上为技术指标计算，仅供参考，不构成任何投资建议")
        return sb.toString()
    }
}
