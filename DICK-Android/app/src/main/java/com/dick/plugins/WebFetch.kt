package com.dick.plugins

import java.net.HttpURLConnection
import java.net.URL

/** 通用网页抓取（HttpURLConnection + 正则，零第三方依赖）——移植自 Python web_fetch.py */
object WebFetch {
    val UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    val NL = 10.toChar().toString()

    private val NAV_NOISE = listOf("首页", "无障碍", "网站地图", "English", "联系我们", "版权",
        "ICP备", "政府网站", "客户端", "微博", "微信", "手机版", "政务新媒体", "网站标识码",
        "分享到", "打印本页", "关闭窗口")

    val POLICY_KW = listOf("通知", "办法", "规定", "意见", "公告", "细则", "条例", "政策",
        "批复", "答复", "解读", "zhengce", "zcfg", "content", "xxgk", "gongbao")

    private val ARTICLE_KW = listOf("content", "article", "zhengce", "htm", "shtml", "xxgk",
        "zwgk", "zcfg", "t202", "detail", "news")

    fun fetchHtml(url: String, timeoutMs: Int = 8000): String {
        return fetchRaw(url, "UTF-8", timeoutMs)
    }

    /** 按指定字符集抓取（如 GBK 的腾讯行情接口） */
    fun fetchRaw(url: String, charsetName: String, timeoutMs: Int = 8000): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        conn.setRequestProperty("User-Agent", UA)
        conn.setRequestProperty("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        try {
            val code = conn.responseCode
            val stream = if (code >= 400) (conn.errorStream ?: conn.inputStream) else conn.inputStream
            val bytes = stream.readBytes()
            return String(bytes, charset(charsetName))
        } finally {
            conn.disconnect()
        }
    }

    fun unescape(s: String): String = s
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", 34.toChar().toString())
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")

    fun stripTags(html: String): String {
        var h = html
        h = Regex("(?is)<script[^>]*>.*?</script>").replace(h, " ")
        h = Regex("(?is)<style[^>]*>.*?</style>").replace(h, " ")
        h = Regex("(?is)<noscript[^>]*>.*?</noscript>").replace(h, " ")
        h = Regex("<[^>]+>").replace(h, " ")
        return unescape(h)
    }

    fun cleanText(html: String, maxChars: Int = 8000): String {
        val lines = LinkedHashSet<String>()
        var total = 0
        for (raw in stripTags(html).lineSequence()) {
            val line = raw.trim()
            if (line.isEmpty() || line in lines) continue
            if (line.length < 40 && NAV_NOISE.any { it in line }) continue
            lines.add(line)
            total += line.length
            if (total >= maxChars) break
        }
        return lines.joinToString(NL)
    }

    fun pageTitle(html: String): String {
        val m = Regex("(?is)<title[^>]*>(.*?)</title>").find(html) ?: return ""
        return unescape(stripTags(m.groupValues[1])).trim()
    }

    fun fetchText(url: String, timeoutMs: Int = 8000, maxChars: Int = 8000): String =
        cleanText(fetchHtml(url, timeoutMs), maxChars)

    private fun absUrl(href: String, baseUrl: String): String {
        val h = href.trim()
        if (h.isEmpty() || h.startsWith("javascript:") || h.startsWith("#") || h.startsWith("mailto:")) return ""
        if (h.startsWith("http")) return h
        val u = URL(URL(baseUrl), h)
        return u.toString()
    }

    private val linkRe = Regex("""<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>""", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL))

    fun findArticleLinks(html: String, baseUrl: String, limit: Int = 10, hrefKeywords: List<String>? = null): List<Pair<String, String>> {
        val kws = hrefKeywords ?: ARTICLE_KW
        val out = mutableListOf<Pair<String, String>>()
        val seen = mutableSetOf<String>()
        for (m in linkRe.findAll(html)) {
            val href = m.groupValues[1]
            val title = stripTags(m.groupValues[2]).trim()
            if (title.length !in 8..90) continue
            if (kws.none { it in href }) continue
            val u = absUrl(href, baseUrl)
            if (u.isEmpty() || u in seen) continue
            seen.add(u)
            out.add(title to u)
            if (out.size >= limit) break
        }
        return out
    }

    fun findPagination(html: String, baseUrl: String, currentUrl: String = "", limit: Int = 5): List<String> {
        val out = mutableListOf<String>()
        val seen = mutableSetOf<String>()
        for (m in linkRe.findAll(html)) {
            val href = m.groupValues[1]
            val anchor = stripTags(m.groupValues[2]).trim().lowercase()
            val u = absUrl(href, baseUrl)
            if (u.isEmpty() || u == currentUrl || u in seen) continue
            val isNext = anchor.isNotEmpty() && (anchor.contains("下一页") || anchor.contains("下页") || anchor.contains("next") || anchor.contains(">"))
            if (!isNext && !Regex("""index[_-]\d+""").containsMatchIn(href)) continue
            seen.add(u)
            out.add(u)
            if (out.size >= limit) break
        }
        return out
    }

    fun sameDomain(u1: String, u2: String): Boolean = try {
        URL(u1).host == URL(u2).host
    } catch (_: Exception) {
        false
    }

    fun isPolicyUrl(url: String): Boolean = POLICY_KW.any { it in url }
}
