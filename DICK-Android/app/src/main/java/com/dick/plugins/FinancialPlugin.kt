package com.dick.plugins

import com.dick.core.AppEnv
import com.dick.core.J
import com.dick.core.JsonS
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 财报助手（Kotlin 版）——移植自 Python financial_plugin v2.0：
 * 10 官方政策源深爬（分页 + 正文 + 关联文件递归）+ 通用爬取 + 本地政策库（增量/检索/定时）
 */
class FinancialPlugin : Plugin {
    override val name = "财报助手"
    override val version = "2.0"
    override val description = "政策深爬 / 通用爬取 / 政策库"
    override var enabled = true

    var maxArticles = 4
    var maxPages = 2
    var maxTotal = 30
    var fetchBodies = true
    var bodyChars = 2000
    var timeoutMs = 8000
    var autoRefreshHours = 0
    var activePreset = ""

    private val refreshLock = Any()
    @Volatile private var refreshing = false
    private var pendingInjection = ""

    var SOURCES = listOf(
        "中国政府网·政策" to "https://www.gov.cn/zhengce/",
        "央行·沟通交流" to "http://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html",
        "证监会·要闻" to "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml",
        "发改委·新闻发布" to "https://www.ndrc.gov.cn/xwdt/xwfb/",
        "财政部·政策发布" to "http://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/",
        "工信部·政策文件" to "https://www.miit.gov.cn/zwgk/zcwj/index.html",
        "商务部·政策发布" to "http://www.mofcom.gov.cn/article/zwgk/zcfb/",
        "金融监管总局·政策" to "https://www.nfra.gov.cn/cn/view/pages/ItemList.html?itemPId=915&itemId=916",
        "国家统计局·发布" to "https://www.stats.gov.cn/sj/zxfb/",
        "国家能源局·政策" to "http://www.nea.gov.cn/zcfg/",
    )

    data class Article(val title: String, val url: String, val source: String, val text: String)

    // ---------- 深爬核心 ----------
    fun crawlAll(fetchBodies: Boolean = true, maxPages: Int = this.maxPages, maxTotal: Int = this.maxTotal): List<Article> {
        val perSource = maxArticles
        val pages = maxPages
        val cap = maxTotal
        val seen = mutableSetOf<String>()
        val articles = mutableListOf<Article>()

        for ((name, url) in SOURCES) {
            if (articles.size >= cap) break
            // 1) BFS 翻页（同域）
            val pageUrls = mutableListOf(url)
            var i = 0
            while (i < pageUrls.size && pageUrls.size < pages) {
                val pu = pageUrls[i]
                i++
                try {
                    val html = WebFetch.fetchHtml(pu, timeoutMs)
                    for (nxt in WebFetch.findPagination(html, pu, pu, 2)) {
                        if (nxt !in pageUrls && WebFetch.sameDomain(nxt, url)) pageUrls.add(nxt)
                    }
                } catch (_: Exception) {
                }
            }
            // 2) 收集文章链接（跨页去重）
            val links = mutableListOf<Triple<String, String, String>>()
            for (pu in pageUrls) {
                try {
                    val html = WebFetch.fetchHtml(pu, timeoutMs)
                    for ((t, u) in WebFetch.findArticleLinks(html, pu, perSource)) {
                        if (u !in seen) links.add(Triple(t, u, name))
                    }
                } catch (_: Exception) {
                }
                if (links.size >= perSource * pages) break
            }
            // 3) 抓正文 + 文内政策链接递归（深度 1）
            for ((title, aurl, src) in links) {
                if (articles.size >= cap) break
                seen.add(aurl)
                var text = ""
                if (fetchBodies) {
                    try {
                        Thread.sleep(150)
                        val html = WebFetch.fetchHtml(aurl, timeoutMs)
                        text = WebFetch.cleanText(html, bodyChars)
                        if (text.isNotEmpty()) {
                            for ((t2, u2) in WebFetch.findArticleLinks(html, aurl, 2, WebFetch.POLICY_KW)) {
                                if (u2 in seen || !WebFetch.sameDomain(u2, aurl) || !WebFetch.isPolicyUrl(u2)) continue
                                seen.add(u2)
                                try {
                                    Thread.sleep(150)
                                    val b2 = WebFetch.fetchText(u2, timeoutMs, bodyChars)
                                    if (b2.isNotEmpty()) articles.add(Article(t2, u2, src + "·关联文件", b2))
                                } catch (_: Exception) {
                                }
                            }
                        }
                    } catch (_: Exception) {
                        text = ""
                    }
                }
                articles.add(Article(title, aurl, src, text))
            }
        }
        return articles
    }

    // ---------- 政策库 ----------
    private fun loadDb(): J.Obj {
        val f = AppEnv.dbFile()
        if (f.exists()) {
            try {
                val root = JsonS.parse(f.readText(Charsets.UTF_8))
                (root as? J.Obj)?.let { return it }
            } catch (_: Exception) {
            }
        }
        return J.Obj()
    }

    private fun saveDb(db: J.Obj) {
        try {
            AppEnv.dbFile().writeText(JsonS.stringify(db, pretty = true), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    private fun articleToJson(a: Article): J.Obj {
        val o = J.Obj()
        o.fields["title"] = J.Str(a.title)
        o.fields["url"] = J.Str(a.url)
        o.fields["source"] = J.Str(a.source)
        o.fields["text"] = J.Str(a.text)
        return o
    }

    private fun jsonToArticle(o: J.Obj): Article = Article(
        title = o.fields["title"]?.str() ?: "",
        url = o.fields["url"]?.str() ?: "",
        source = o.fields["source"]?.str() ?: "",
        text = o.fields["text"]?.str() ?: "",
    )

    fun buildDb(): Triple<Int, Int, Int> {
        val articles = crawlAll(fetchBodies = true)
        val db = loadDb()
        val arts = db.fields["articles"] as? J.Obj ?: J.Obj().also { db.fields["articles"] = it }
        var added = 0
        var updated = 0
        for (a in articles) {
            val old = arts.fields[a.url] as? J.Obj
            if (old != null) {
                if (a.text.isNotEmpty() && a.text != (old.fields["text"]?.str() ?: "")) {
                    arts.fields[a.url] = articleToJson(a)
                    updated++
                }
            } else {
                arts.fields[a.url] = articleToJson(a)
                added++
            }
        }
        val fmt = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
        db.fields["updated_at"] = J.Str(fmt.format(Date()))
        saveDb(db)
        return Triple(added, updated, arts.fields.size)
    }

    private fun dbStale(hours: Int): Boolean {
        val db = loadDb()
        val ts = db.fields["updated_at"]?.str()
        if (ts.isNullOrEmpty()) return true
        return try {
            val fmt = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
            val then = fmt.parse(ts) ?: return true
            (System.currentTimeMillis() - then.time) > hours * 3600_000L
        } catch (_: Exception) {
            true
        }
    }

    fun refreshQuiet() {
        synchronized(refreshLock) {
            if (refreshing) return
            refreshing = true
        }
        try {
            val (added, updated, total) = buildDb()
            println("[财报助手] 政策库后台刷新：+" + added + " 更新" + updated + " 共" + total + " 条")
        } catch (e: Exception) {
            println("[财报助手] 政策库后台刷新失败：" + e.message)
        } finally {
            refreshing = false
        }
    }

    private fun countSub(s: String, sub: String): Int {
        if (sub.isEmpty()) return 0
        var c = 0
        var i = s.indexOf(sub)
        while (i >= 0) {
            c++
            i = s.indexOf(sub, i + sub.length)
        }
        return c
    }

    private fun tokenize(q: String): List<String> {
        val tokens = mutableListOf<String>()
        for (word in Regex("[0-9A-Za-z]+").findAll(q)) tokens.add(word.value.lowercase())
        val cjk = StringBuilder()
        for (ch in q) {
            val c = ch.code
            if (c in 0x4E00..0x9FFF) cjk.append(ch)
        }
        val s = cjk.toString()
        for (i in 0 until s.length - 1) tokens.add(s.substring(i, i + 2))
        return tokens.filter { it.length >= 2 }
    }

    fun searchDb(query: String, top: Int = 8): List<Article> {
        val db = loadDb()
        val arts = db.fields["articles"] as? J.Obj ?: return emptyList()
        val tokens = tokenize(query)
        val scored = mutableListOf<Pair<Int, Article>>()
        for ((_, v) in arts.fields) {
            val a = jsonToArticle(v as? J.Obj ?: continue)
            var score = 0
            for (tk in tokens) score += countSub(a.title, tk) * 3 + countSub(a.text, tk)
            if (query.isNotBlank() && query in a.title) score += 5
            if (score > 0) scored.add(score to a)
        }
        scored.sortByDescending { it.first }
        return scored.take(top).map { it.second }
    }

    private fun autoInject(userInput: String) {
        pendingInjection = ""
        if (activePreset != "财报模式") return
        val hits = searchDb(userInput, top = 3)
        if (hits.isEmpty()) return
        val sb = StringBuilder("【政策库自动引用（与当前话题相关）】")
        for (a in hits) {
            sb.append(10.toChar())
            sb.append("■ ").append(a.title).append(10.toChar())
            sb.append("  来源：").append(a.url).append(10.toChar())
            sb.append("  ").append(a.text.take(400))
        }
        pendingInjection = sb.toString()
    }

    override fun contextInjection(): String = pendingInjection

    override fun onMessageSend(userInput: String): String? {
        if (autoRefreshHours > 0 && dbStale(autoRefreshHours)) {
            Thread { refreshQuiet() }.apply { isDaemon = true }.start()
        }
        autoInject(userInput)
        return userInput
    }

    override fun onLoad() {
        seedHistory()
        if (autoRefreshHours > 0 && dbStale(autoRefreshHours)) {
            Thread { refreshQuiet() }.apply { isDaemon = true }.start()
        }
    }

    /** 把金融史年表（1617-2026）播种进政策库：仅补缺失，不覆盖爬取内容 */
    private fun seedHistory() {
        try {
            val f = File(AppEnv.dataRoot, "financial_history.json")
            if (!f.exists()) return
            val hist = JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj ?: return
            val entries = hist.fields["entries"] as? J.Arr ?: return
            val db = loadDb()
            val arts = db.fields["articles"] as? J.Obj ?: J.Obj().also { db.fields["articles"] = it }
            var n = 0
            for (e in entries.items) {
                val o = e as? J.Obj ?: continue
                val url = o.fields["url"]?.str() ?: continue
                if (!arts.fields.containsKey(url)) {
                    arts.fields[url] = o
                    n++
                }
            }
            if (n > 0) {
                db.fields["history_count"] = J.Num(entries.items.size.toDouble(), entries.items.size.toString())
                saveDb(db)
            }
        } catch (_: Exception) {
        }
    }

    // ---------- 命令 ----------
    override fun onCommand(command: String, args: String): String? {
        val arg = (args ?: "").trim()
        val low = arg.lowercase()
        if (command == "爬取" || command == "crawl") {
            if (low.isNotEmpty()) return crawlSingle(low)
            return crawlSources()
        }
        if (command == "股票" || command == "stock") {
            if (arg.isEmpty()) return "📊 用法：/股票 <代码>，如 /股票 600519 或 /股票 sh600519"
            return analyzeStock(arg)
        }
        if (command == "联动" || command == "linked") {
            if (arg.isEmpty()) return "🔗 用法：/联动 <代码1[,代码2...]> [关键词]，如 /联动 600519,300750 消费 新能源"
            return analyzeLinked(arg)
        }
        if (command == "股票列表" || command == "涨跌幅榜" || command == "ranklist") {
            return marketList(arg)
        }
        if (command == "全市场" || command == "screen") {
            return screenMarket(arg)
        }
        if (command != "财报") return null
        if (low in listOf("help", "帮助", "h", "")) return help()
        if (low.startsWith("爬取")) {
            val url = arg.substring(2).trim()
            if (url.isNotEmpty()) return crawlSingle(url)
            return crawlSources()
        }
        if (low in listOf("标题", "速览", "titles")) return crawlSources(fetchBodies = false)
        if (low in listOf("入库", "更新", "建库")) {
            return try {
                val (added, updated, total) = buildDb()
                "📚 政策库已更新：新增 " + added + " 条，更新 " + updated + " 条，库内共 " + total + " 条" + 10.toChar() +
                    "（policy_db.json 保存在数据目录；财报模式下自动引用相关条目，/财报 检索 <关键词> 可查询）"
            } catch (e: Exception) {
                "⚠️ 入库失败：" + e.message
            }
        }
        if (low.startsWith("检索") || low.startsWith("查询")) {
            val q = arg.substring(2).trim()
            if (q.isEmpty()) return "📚 用法：/财报 检索 <关键词>，如 /财报 检索 新能源"
            val hits = searchDb(q, top = 8)
            if (hits.isEmpty()) return "📚 政策库中没有匹配的条目（可先 /财报 入库 建立政策库）"
            val sb = StringBuilder("📚 政策库检索结果（" + q + "）")
            var idx = 1
            for (a in hits) {
                sb.append(10.toChar()).append(idx).append(". ").append(a.title).append("（").append(a.source).append("）")
                sb.append(10.toChar()).append("   ").append(a.url)
                idx++
            }
            pendingInjection = sb.toString()
            return sb.toString() + 10.toChar() + 10.toChar() + "✅ 已注入上下文，可直接提问"
        }
        if (low.startsWith("股票") || low.startsWith("stock")) {
            val c = if (low.startsWith("股票")) arg.substring(2).trim() else arg.substring(5).trim()
            if (c.isEmpty()) return "📊 用法：/财报 股票 <代码>，如 /财报 股票 600519"
            return analyzeStock(c)
        }
        if (low.startsWith("股票列表") || low.startsWith("涨跌幅榜")) {
            return marketList(arg.substring(4).trim())
        }
        if (low.startsWith("全市场") || low.startsWith("screen")) {
            val rest = if (low.startsWith("全市场")) arg.substring(3).trim() else arg.substring(6).trim()
            return screenMarket(rest)
        }
        if (low.startsWith("联动") || low.startsWith("linked")) {
            val rest = if (low.startsWith("联动")) arg.substring(2).trim() else arg.substring(6).trim()
            if (rest.isEmpty()) return "🔗 用法：/财报 联动 <代码1[,代码2...]> [关键词]"
            return analyzeLinked(rest)
        }
        if (low.startsWith("定时")) {
            val rest = arg.substring(2).trim()
            if (rest.isEmpty()) {
                val state = if (autoRefreshHours > 0) "开启，每 " + autoRefreshHours + " 小时自动刷新" else "关闭"
                return "⏰ 政策库定时刷新：" + state + 10.toChar() + "用法：/财报 定时 开 [小时] 或 /财报 定时 关"
            }
            val toks = rest.split(" ")
            if (toks[0] in listOf("开", "开启", "on")) {
                val hours = toks.getOrNull(1)?.toIntOrNull() ?: 6
                autoRefreshHours = hours
                return "⏰ 已开启政策库定时刷新（每 " + hours + " 小时，过期后下次发消息时后台自动刷新）"
            }
            if (toks[0] in listOf("关", "关闭", "off")) {
                autoRefreshHours = 0
                return "⏰ 已关闭政策库定时刷新"
            }
            return "⏰ 用法：/财报 定时 开 [小时] 或 /财报 定时 关"
        }
        return help()
    }

    private fun crawlSources(fetchBodies: Boolean = this.fetchBodies): String {
        val articles = try {
            crawlAll(fetchBodies = fetchBodies)
        } catch (e: Exception) {
            return "⚠️ 爬取失败：" + e.message
        }
        if (articles.isEmpty()) {
            return "⚠️ 全部来源爬取失败（网络受限或站点改版）。" + 10.toChar() + "可用 /财报 爬取 <网址> 手动补充指定文件。"
        }
        val sb = StringBuilder()
        var curSrc: String? = null
        for (a in articles) {
            if (a.source != curSrc) {
                curSrc = a.source
                sb.append("【").append(curSrc).append("】").append(10.toChar())
            }
            if (fetchBodies && a.text.isNotEmpty()) {
                sb.append("■ ").append(a.title).append(10.toChar())
                sb.append("  （来源：").append(a.url).append("）").append(10.toChar())
                sb.append("  ").append(a.text).append(10.toChar())
            } else {
                sb.append("- ").append(a.title).append("（").append(a.url).append("）").append(10.toChar())
            }
        }
        val digest = sb.toString()
        pendingInjection = digest
        val preview = digest.take(1200)
        val bodies = articles.count { it.text.isNotEmpty() }
        val srcs = articles.map { it.source.split("·")[0] }.distinct().size
        val mode = if (fetchBodies) "深度抓取 " + bodies + " 篇正文" else "标题速览"
        return "📈 已爬取 " + srcs + " 个政策源（" + mode + "，共 " + articles.size + " 条）：" + 10.toChar() +
            preview + (if (digest.length > 1200) 10.toChar() + "…（完整内容已注入上下文）" else "") + 10.toChar() + 10.toChar() +
            "✅ 已注入上下文，现在可以直接提问分析"
    }

    private fun crawlSingle(url: String): String {
        var u = url.trim()
        if (u.isEmpty()) {
            return "🌐 用法：/爬取 <网址> 抓取任意网页正文" + 10.toChar() + "  例：/爬取 https://www.gov.cn/zhengce/content/xxxx.htm"
        }
        if (!u.startsWith("http")) u = "https://" + u
        return try {
            val html = WebFetch.fetchHtml(u, timeoutMs)
            val title = WebFetch.pageTitle(html)
            val text = WebFetch.cleanText(html, 8000)
            if (text.isBlank()) return "⚠️ 未能从该页面提取到文本（可能是纯图片、JS 渲染或需登录的页面）"
            val head = if (title.isNotEmpty()) "📄 " + title + 10.toChar() + "来源：" + u + 10.toChar() + 10.toChar()
            else "📄 已抓取 " + u + 10.toChar() + 10.toChar()
            pendingInjection = head + text
            val preview = text.take(600)
            head + preview + (if (text.length > 600) 10.toChar() + "…（全文 " + text.length + " 字符已注入上下文）" else "") +
                10.toChar() + 10.toChar() + "✅ 已注入上下文，可直接提问分析"
        } catch (e: Exception) {
            "⚠️ 抓取失败：" + e.message
        }
    }

    private fun analyzeLinked(arg: String): String {
        val nums = listOf("一", "二", "三", "四", "五", "六", "七")
        val parts = arg.split(" ")
        val codes = parts[0].split(",").map { it.trim() }.filter { it.isNotEmpty() }.take(5)
        val keywords = parts.drop(1).joinToString(" ")
        if (codes.isEmpty()) return "🔗 用法：/联动 <代码1[,代码2...]> [关键词]"
        val names = mutableListOf<String>()
        val sections = mutableListOf<String>()
        val sums = mutableListOf<List<String>>()
        for (code in codes) {
            var name = code
            try {
                name = StockAnalyzer.fetchQuote(code)["name"] as? String ?: code
            } catch (_: Exception) {
            }
            names.add(name)
            try {
                val report = StockAnalyzer.analyze(code)
                sections.add(report)
                val m = Regex("偏多 ([0-9]+)｜中性 ([0-9]+)｜偏空 ([0-9]+) → (.+)").find(report)
                if (m != null) sums.add(listOf(code, m.groupValues[1], m.groupValues[2], m.groupValues[3], m.groupValues[4]))
                else sums.add(listOf(code, "?", "?", "?", "?"))
            } catch (e: Exception) {
                sections.add("⚠️ " + code + " 分析失败：" + e.message)
                sums.add(listOf(code, "?", "?", "?", "?"))
            }
        }
        val policyHits = mutableListOf<Article>()
        val seen = mutableSetOf<String>()
        for (name in names) {
            for (a in searchDb((name + " " + keywords).trim(), 4)) {
                if (a.url.isNotEmpty() && a.url in seen) continue
                if (a.url.isNotEmpty()) seen.add(a.url)
                policyHits.add(a)
            }
        }
        val sb = StringBuilder()
        sb.append("🔗 联动综合分析报告（").append(codes.size).append(" 只个股 × 政策库）").append(10.toChar())
        sb.append("━━━━━━━━━━━━━━━━━━━━").append(10.toChar())
        var idx = 0
        for (i in codes.indices) {
            sb.append("【").append(nums[minOf(idx, 6)]).append("、").append(names[idx]).append("（").append(codes[idx]).append("）技术面】").append(10.toChar())
            sb.append(sections[idx]).append(10.toChar()).append(10.toChar())
            idx++
        }
        sb.append("【").append(nums[minOf(idx, 6)]).append("、政策面（匹配：").append(names.joinToString(","))
            .append(if (keywords.isNotEmpty()) " " + keywords else "").append("）】").append(10.toChar())
        if (policyHits.isEmpty()) {
            sb.append("（政策库暂无匹配条目。先运行 /财报 入库 建立政策库（10 官方源自动深爬），或补充关键词重试）")
        } else {
            for (a in policyHits.take(8)) {
                sb.append("■ ").append(a.title).append("（").append(a.source).append("）").append(10.toChar())
                val text = a.text
                sb.append("  ").append(text.take(200)).append(if (text.length > 200) "…" else "").append(10.toChar())
            }
        }
        sb.append(10.toChar())
        sb.append("【").append(nums[minOf(idx + 1, 6)]).append("、联动结论】").append(10.toChar())
        var totalBull = 0
        var totalBear = 0
        for (s in sums) {
            sb.append("  ").append(s[0]).append("：偏多 ").append(s[1]).append("｜中性 ").append(s[2]).append("｜偏空 ")
                .append(s[3]).append(" → ").append(s[4]).append(10.toChar())
            totalBull += s[1].toIntOrNull() ?: 0
            totalBear += s[3].toIntOrNull() ?: 0
        }
        if (policyHits.isNotEmpty()) {
            sb.append("  政策面：").append(policyHits.size).append(" 条相关条目已纳入上下文，关注政策对相关行业的边际影响").append(10.toChar())
        } else {
            sb.append("  政策面：无匹配（可 /财报 入库 补库）").append(10.toChar())
        }
        sb.append("  综合：").append(
            when {
                totalBear > totalBull -> "技术面偏空信号占优，结合政策面谨慎对待"
                totalBull > totalBear -> "技术面偏多信号占优，可结合政策面寻找催化"
                else -> "技术面多空胶着，等待方向选择"
            },
        ).append(10.toChar())
        sb.append("  💡 报告已注入上下文，直接让 AI 深度解读（如：综合分析这两只票的联动机会）").append(10.toChar())
        sb.append("⚠️ 仅供参考，不构成任何投资建议")
        val digest = sb.toString()
        pendingInjection = digest
        val preview = digest.take(1600)
        return preview + (if (digest.length > 1600) 10.toChar().toString() + "…（完整报告已注入上下文）" else "")
    }

    private fun marketList(arg: String): String {
        var text = (arg ?: "").trim()
        var losers = false
        if (text.startsWith("跌") || text.startsWith("down")) {
            losers = true
            text = text.substring(1).trim()
        }
        val n = (text.toIntOrNull() ?: 20).coerceIn(1, 100)
        return try {
            StockAnalyzer.marketListReport(n, losers)
        } catch (e: Exception) {
            "📈 行情列表获取失败：" + e.message
        }
    }

    private fun screenMarket(arg: String): String {
        if ((arg ?: "").trim().isEmpty()) return StockAnalyzer.screenReport("")
        val report = try {
            StockAnalyzer.screenReport(arg.trim())
        } catch (e: Exception) {
            return "🔍 全市场筛选失败：" + e.message
        }
        pendingInjection = report
        return report
    }

    private fun analyzeStock(code: String): String {
        return try {
            val report = StockAnalyzer.analyze(code)
            pendingInjection = report
            report
        } catch (e: Exception) {
            "📊 个股分析失败：" + e.message
        }
    }

    private fun help(): String = listOf(
        "📈 财报助手 v2.0 使用说明",
        "  /财报 爬取              全源深爬：10 官方政策源 + 翻页 + 正文 + 关联文件递归",
        "  /财报 标题              全源标题速览（不抓正文，最快）",
        "  /财报 爬取 <网址>       抓取指定文件全文",
        "  /爬取 <网址>            通用网页爬取：任意网站正文",
        "  /财报 入库              全源深爬存入本地政策库（增量去重）",
        "  /财报 检索 <关键词>     从政策库检索相关条目",
        "  /财报 股票 <代码>       A股个股炒股要素分析（行情/估值/均线/MACD/KDJ/RSI/BOLL/ATR/支撑压力）",
        "  /股票 <代码>            个股分析快捷方式",
        "  /财报 联动 <代码,代码> [关键词]  联动综合分析：多股技术面 + 政策库匹配 + 综合结论",
        "  /联动 <代码,代码> [关键词]      联动分析快捷方式",
        "  /股票列表 [N] / 跌 [N]       A股涨跌幅榜（沪深北全市场）",
        "  /全市场 涨幅>5 换手>10     全市场筛选（涨幅/换手/量比/市盈/市值/流入）",
        "  /财报 定时 开 [小时]    开启政策库定时刷新",
        "  /财报 定时 关           关闭定时刷新",
        "  财报模式下发送消息会自动引用政策库中与话题最相关的条目。",
    ).joinToString(10.toChar().toString())
}
