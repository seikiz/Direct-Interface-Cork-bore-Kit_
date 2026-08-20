package com.dick.plugins

import java.net.URLEncoder

/** 联网搜索（DuckDuckGo/Bing）+ 深搜（自动跟进抓正文）——移植自 Python v2.0 */
class SearchPlugin : Plugin {
    override val name = "联网搜索"
    override val version = "2.0"
    override val description = "/搜索 快速搜索；/深搜 搜索并跟进抓正文"
    override var enabled = true

    var count = 5
    var deepCount = 4
    var timeoutMs = 10000
    var engineChoice = "自动（DuckDuckGo 优先）"

    private var pending = ""

    data class Hit(val title: String, val snippet: String, val url: String)

    private val ddgRe = Regex(
        """<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>""",
        setOf(RegexOption.DOT_MATCHES_ALL),
    )

    private val bingRe = Regex(
        """<li class="b_algo".*?<h2><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>.*?(?:<p[^>]*>(.*?)</p>)?""",
        setOf(RegexOption.DOT_MATCHES_ALL),
    )

    fun parseDdg(html: String, limit: Int): List<Hit> {
        val out = mutableListOf<Hit>()
        for (m in ddgRe.findAll(html)) {
            var url = m.groupValues[1]
            val title = WebFetch.stripTags(m.groupValues[2]).trim()
            val snippet = WebFetch.stripTags(m.groupValues[3]).trim()
            if (title.isEmpty()) continue
            if (url.startsWith("//")) url = "https:" + url
            if (url.startsWith("/l/?")) {
                val um = Regex("uddg=([^&]+)").find(url)
                if (um != null) url = WebFetch.unescape(um.groupValues[1])
            }
            out.add(Hit(title, snippet, url))
            if (out.size >= limit) break
        }
        return out
    }

    fun parseBing(html: String, limit: Int): List<Hit> {
        val out = mutableListOf<Hit>()
        for (m in bingRe.findAll(html)) {
            val url = m.groupValues[1]
            val title = WebFetch.stripTags(m.groupValues[2]).trim()
            val snippet = WebFetch.stripTags(m.groupValues[3]).trim()
            if (title.isEmpty()) continue
            out.add(Hit(title, snippet, url))
            if (out.size >= limit) break
        }
        return out
    }

    fun search(query: String): Pair<String?, List<Hit>> {
        val q = URLEncoder.encode(query, "UTF-8")
        val attempts = mutableListOf<Pair<String, String>>()
        if (engineChoice in listOf("自动（DuckDuckGo 优先）", "DuckDuckGo")) {
            attempts.add("DuckDuckGo" to "https://html.duckduckgo.com/html/?q=" + q)
        }
        if (engineChoice in listOf("自动（DuckDuckGo 优先）", "Bing")) {
            attempts.add("Bing" to "https://www.bing.com/search?q=" + q)
        }
        var lastErr = "未知错误"
        for ((name, url) in attempts) {
            try {
                val html = WebFetch.fetchHtml(url, timeoutMs)
                val hits = if (name == "Bing") parseBing(html, count) else parseDdg(html, count)
                if (hits.isNotEmpty()) return name to hits
                lastErr = name + "：无结果（可能被反爬拦截）"
            } catch (e: Exception) {
                lastErr = name + "：" + e.message
            }
        }
        return null to emptyList()
    }

    override fun contextInjection(): String = pending

    override fun onCommand(command: String, args: String): String? {
        val query = (args ?: "").trim()
        if (command in listOf("深搜", "deepsearch", "deep")) {
            if (query.isEmpty()) return "🔍 深搜用法：/深搜 <关键词>（搜索并自动跟进抓正文）"
            return deepSearch(query)
        }
        if (command !in listOf("搜索", "search", "web")) return null
        if (query.isEmpty()) return "🔍 用法：/搜索 <关键词>；想要网页全文用 /深搜 <关键词>"
        val (name, hits) = search(query)
        if (name == null) return "⚠️ 搜索失败（网络受限或被反爬拦截）"
        val sb = StringBuilder("🔍 搜索结果（" + name + "，关键词：" + query + "）")
        var i = 1
        for (h in hits) {
            sb.append(10.toChar()).append(i).append(". ").append(h.title)
            sb.append(10.toChar()).append("   ").append(h.snippet)
            sb.append(10.toChar()).append("   ").append(h.url)
            i++
        }
        pending = sb.toString()
        return sb.toString() + 10.toChar() + 10.toChar() + "✅ 已注入上下文，现在可以直接提问"
    }

    fun deepSearch(query: String): String {
        val (name, hits) = search(query)
        if (name == null) return "⚠️ 搜索失败（网络受限或被反爬拦截）"
        val sb = StringBuilder("🔍 深搜结果（" + name + "，关键词：" + query + "）")
        var got = 0
        var i = 1
        for (h in hits.take(deepCount)) {
            sb.append(10.toChar()).append(i).append(". ").append(h.title)
            sb.append(10.toChar()).append("   ").append(h.snippet)
            sb.append(10.toChar()).append("   ").append(h.url)
            try {
                val body = WebFetch.fetchText(h.url, timeoutMs, 2000)
                if (body.isNotEmpty()) {
                    got++
                    val snip = body.take(900)
                    sb.append(10.toChar()).append("   【正文】").append(snip).append(if (body.length > 900) "…" else "")
                } else {
                    sb.append(10.toChar()).append("   【正文】提取为空")
                }
            } catch (e: Exception) {
                sb.append(10.toChar()).append("   【正文】抓取失败：" + e.message)
            }
            i++
        }
        pending = sb.toString()
        return sb.toString() + 10.toChar() + 10.toChar() + "✅ 已跟进抓取 " + got + "/" + hits.take(deepCount).size + " 篇正文并注入上下文"
    }
}
