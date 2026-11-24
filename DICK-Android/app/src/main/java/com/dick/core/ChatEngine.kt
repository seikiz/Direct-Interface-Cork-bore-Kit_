package com.dick.core

import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.URL

data class Usage(
    val promptTokens: Int = 0,
    val completionTokens: Int = 0,
    val totalTokens: Int = 0,
)

/**
 * 流式聊天引擎 —— OpenAI 兼容接口（DeepSeek 等）。
 * HttpURLConnection 实现：Android 全版本可用，桌面 JVM 同样可运行。
 * 回调在后台线程触发；UI 侧用 Handler/协程切回主线程。
 */
class ChatEngine(
    var baseUrl: String = "https://api.deepseek.com",
    var apiKey: String = "",
    var model: String = "deepseek-flash",
) {
    /** 免费厂商（OVH 免费链 / Ollama 本地）允许空 Key */
    @Volatile
    var allowEmptyKey: Boolean = false

    /** LLM 通道代理（http://host:port 或 host:port；null=直连），保证被墙厂商可用 */
    @Volatile
    var proxy: String? = null

    /** 内置代理通道（中转地址，如 https://xxx.workers.dev）；直连网络失败自动走它 */
    @Volatile
    var relayBase: String? = null

    /** 是否已切换到中转通道（直连失败后置 true，后续请求直接走中转） */
    @Volatile
    var relayOn: Boolean = false

    /** 停止序列（指令模板）：模型输出到这些串即停止生成 */
    @Volatile
    var stopSequences: List<String> = emptyList()

    /** 采样参数（null = 模型默认） */
    @Volatile
    var temperature: Float? = null

    @Volatile
    var topP: Float? = null

    /**
     * 每轮的额外上下文（生活层【生活·那边】/ 空间层【空间】）。
     *
     * 为什么不写死在引擎里：这两层要读"当前角色/当前世界卡/现在几点"，那是 UI 侧的状态，
     * 引擎不该反过来依赖 App。做成一个返回字符串的钩子，插在【时间】后面 ——
     * 与电脑端 `_fetch_response` 的注入顺序一致（世界 → 时间 → 生活 → 空间 → 状态）。
     */
    @Volatile
    var contextProvider: (() -> List<String>)? = null

    @Volatile
    var isProcessing: Boolean = false
        private set

    @Volatile
    private var activeConn: HttpURLConnection? = null

    @Volatile
    private var activeThread: Thread? = null

    @Volatile
    private var stopped: Boolean = false

    /** 记录不支持 stream_options 的 (baseUrl, model)，避免每轮都多发一次 400 请求 */
    private val noStreamOptions = java.util.Collections.synchronizedSet(mutableSetOf<String>())

    /** 主动中止正在进行的流式生成（断开连接 + 打断读取线程） */
    fun stop() {
        stopped = true
        try { activeConn?.disconnect() } catch (_: Exception) {}
        try { activeThread?.interrupt() } catch (_: Exception) {}
    }

    private fun role(role: String, content: String): J.Obj {
        val o = J.Obj()
        o.fields["role"] = J.Str(role)
        o.fields["content"] = J.Str(content)
        return o
    }

    private fun buildBody(
        chain: List<MessageNode>,
        systemPrompt: String?,
        withUsage: Boolean,
        stream: Boolean,
    ): String {
        val messages = J.Arr()
        if (!systemPrompt.isNullOrBlank()) messages.items.add(role("system", systemPrompt))
        // 时间上下文：粘在历史【之前】，让模型带着时间感去读下面这些对话。
        // 这就是"两条纸带粘一起"——一条记内容，一条记间隔。
        TimeContext.build(chain, TimeScale.current)?.let {
            messages.items.add(role("system", it))
        }
        // 生活层 / 空间层：同样粘在历史之前。注入里带"那边现在几点、她今天吃了什么、
        // 她此刻在哪、这段时间够去哪" —— 都是**当轮才算得出来**的东西，不能进 system 缓存。
        try {
            contextProvider?.invoke()?.forEach { part ->
                if (part.isNotBlank()) messages.items.add(role("system", part))
            }
        } catch (_: Exception) {
            // 上下文算不出来（没时间戳/没选角色）就不注入，别把整轮请求带崩
        }
        for (node in chain) {
            // 引用：只有 user 节点可能带（metadata["quote"]），拼成「〔引用 谁：…〕\n正文」
            val text = if (node.role == "user") Quote.apply(node.content, Quote.fromNode(node))
                       else node.content
            if (text.isNotBlank()) messages.items.add(role(node.role, text))
        }
        val body = J.Obj()
        body.fields["model"] = J.Str(model)
        body.fields["messages"] = messages
        body.fields["stream"] = J.Bool(stream)
        if (stopSequences.isNotEmpty()) {
            val stops = J.Arr()
            stopSequences.forEach { stops.items.add(J.Str(it)) }
            body.fields["stop"] = stops
        }
        temperature?.let { body.fields["temperature"] = J.Num(it.toDouble(), it.toString()) }
        topP?.let { body.fields["top_p"] = J.Num(it.toDouble(), it.toString()) }
        if (stream && withUsage) {
            val so = J.Obj()
            so.fields["include_usage"] = J.Bool(true)
            body.fields["stream_options"] = so
        }
        return JsonS.stringify(body)
    }

    private fun openConn(effBase: String): HttpURLConnection {
        val url = URL(effBase.trimEnd('/') + "/chat/completions")
        val proxyConn = if (isLocalUrl(effBase)) null else parseProxy(proxy)
        return (if (proxyConn != null) url.openConnection(proxyConn) else url.openConnection()) as HttpURLConnection
    }

    /** 内置代理通道：base_url 编码成 <中转>/relay/<base64>，中转把请求转发到真实厂商 */
    private fun relayTargetUrl(): String {
        if (isLocalUrl(baseUrl)) return baseUrl
        val b64 = java.util.Base64.getUrlEncoder().withoutPadding()
            .encodeToString(baseUrl.toByteArray(Charsets.UTF_8))
        return (relayBase?.trimEnd('/') ?: "") + "/relay/" + b64
    }

    private fun post(body: String): Pair<Int, List<String>> {
        var attempt = 0
        while (true) {
            attempt++
            val relayMode = relayOn && relayBase != null && !isLocalUrl(baseUrl)
            val effBase = if (relayMode) relayTargetUrl() else baseUrl
            val conn = openConn(effBase)
            try {
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("Authorization", "Bearer " + apiKey.ifBlank { "free" })
                conn.doOutput = true
                conn.connectTimeout = 15000
                conn.readTimeout = 300000  // 长思考/慢流式不易被 120s 掐断（配合 onError 兜底）
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                val code = conn.responseCode
                val stream = if (code >= 400) (conn.errorStream ?: conn.inputStream) else conn.inputStream
                val lines = stream.bufferedReader(Charsets.UTF_8).readLines()
                if (attempt == 1 && isRetryableStatus(code)) {
                    try { java.util.concurrent.TimeUnit.MILLISECONDS.sleep(1000) } catch (_: InterruptedException) { return Pair(code, lines) }
                    continue
                }
                return Pair(code, lines)
            } catch (e: java.io.IOException) {
                // 网络层失败（直连被墙/超时）→ 切内置代理通道重试一次（本机地址不切）
                if (attempt == 1 && relayBase != null && !relayOn && !isLocalUrl(baseUrl)) {
                    relayOn = true
                    continue
                }
                throw e
            } finally {
                conn.disconnect()
            }
        }
    }

    /** 真正的逐行流式 POST：每收到一行 SSE 立刻回调 onLine，不等整条响应结束。
     *  返回 (statusCode, errorBodyOrEmpty)。 */
    private fun streamPost(body: String, onLine: (String) -> Unit, hasAnyOutput: () -> Boolean): Pair<Int, String> {
        var attempt = 0
        while (true) {
            attempt++
            val relayMode = relayOn && relayBase != null && !isLocalUrl(baseUrl)
            val effBase = if (relayMode) relayTargetUrl() else baseUrl
            val conn = openConn(effBase)
            activeConn = conn
            try {
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("Accept", "text/event-stream")
                conn.setRequestProperty("Authorization", "Bearer " + apiKey.ifBlank { "free" })
                conn.doOutput = true
                conn.connectTimeout = 15000
                conn.readTimeout = 300000
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                val code = conn.responseCode
                if (code >= 400) {
                    val errText = try {
                        (conn.errorStream ?: conn.inputStream)?.bufferedReader(Charsets.UTF_8)?.readText() ?: ""
                    } catch (_: Exception) { "" }
                    if (attempt == 1 && !stopped && !hasAnyOutput() && isRetryableStatus(code)) {
                        try { java.util.concurrent.TimeUnit.MILLISECONDS.sleep(1000) } catch (_: InterruptedException) { return Pair(code, errText) }
                        continue
                    }
                    return Pair(code, errText)
                }
                conn.inputStream.bufferedReader(Charsets.UTF_8).use { reader ->
                    while (!stopped) {
                        val line = reader.readLine() ?: break
                        onLine(line)
                    }
                }
                return Pair(code, "")
            } catch (e: java.io.IOException) {
                if (stopped) return Pair(200, "")
                if (attempt == 1 && !hasAnyOutput() && relayBase != null && !relayOn && !isLocalUrl(baseUrl)) {
                    relayOn = true
                    continue
                }
                if (hasAnyOutput()) return Pair(200, "")
                throw e
            } finally {
                if (activeConn === conn) activeConn = null
                conn.disconnect()
            }
        }
    }

    /** 流式发送：真正逐行流式读取 SSE，逐块回调 onStream(累计全文) */
    fun send(
        chain: List<MessageNode>,
        systemPrompt: String?,
        onStream: (String) -> Unit = {},
        onResponse: (String, Usage?) -> Unit = { _, _ -> },
        onError: (String) -> Unit = {},
    ) {
        if (apiKey.isBlank() && !allowEmptyKey) {
            onError("请先设置 API Key")
            return
        }
        if (isProcessing) {
            onError("正在处理中，请稍候")
            return
        }
        isProcessing = true
        stopped = false
        // 这一条**故意**是裸线程，不走 Lanes：它是流式读取的专用工作线程 ——
        // 里面是阻塞的 HttpURLConnection 读循环，还要能被 stop() 随时打断（interrupt）。
        // 丢进分道的话，一次生成就会长期占住一条线的名额，其它任务全排在后面；
        // 而且 stops 的语义需要拿到这个 Thread 引用。别的活该走线就走线。
        val worker = Thread {
            try {
                val full = StringBuilder()
                var usage: Usage? = null
                val epKey = "${baseUrl.trimEnd('/')}|$model"
                val handleLine: (String) -> Unit = { line ->
                    if (line.startsWith("data:")) {
                        val payload = line.removePrefix("data:").trim()
                        if (payload.isNotEmpty() && payload != "[DONE]") {
                            try {
                                val obj = JsonS.parse(payload) as? J.Obj
                                if (obj != null) {
                                    (obj.fields["usage"] as? J.Obj)?.let { usage = parseUsage(it) }
                                    val choices = obj.fields["choices"] as? J.Arr
                                    val first = choices?.items?.getOrNull(0) as? J.Obj
                                    val delta = first?.fields?.get("delta") as? J.Obj
                                    val text = (delta?.fields?.get("content") as? J.Str)?.v
                                    if (!text.isNullOrEmpty()) {
                                        full.append(text)
                                        onStream(full.toString())
                                    }
                                }
                            } catch (_: Exception) {
                            }
                        }
                    }
                }
                val tryWithUsage = epKey !in noStreamOptions
                var res = streamPost(buildBody(chain, systemPrompt, tryWithUsage, true), handleLine) { full.isNotEmpty() }
                // 仅 400/422（厂商不认 stream_options）时降级重试，避免 401/402/429 白发第二次
                if (tryWithUsage && res.first in setOf(400, 422) && full.isEmpty() && !stopped) {
                    noStreamOptions.add(epKey)
                    res = streamPost(buildBody(chain, systemPrompt, false, true), handleLine) { full.isNotEmpty() }
                }
                if (res.first >= 400 && full.isEmpty()) {
                    isProcessing = false
                    onError(formatHttpError(res.first, res.second))
                    return@Thread
                }
                isProcessing = false
                onResponse(full.toString(), usage)
            } catch (e: Exception) {
                isProcessing = false
                if (!stopped) onError(e.message ?: "网络错误")
            } finally {
                isProcessing = false
                activeConn = null
                activeThread = null
            }
        }
        activeThread = worker
        worker.isDaemon = true
        worker.start()
    }

    /** 非流式单次调用（供 /jp /zh /swipe 等使用）；失败返回 null */
    fun complete(chain: List<MessageNode>, systemPrompt: String?): String? {
        if (apiKey.isBlank() && !allowEmptyKey) return null
        try {
            val (code, lines) = post(buildBody(chain, systemPrompt, false, false))
            if (code >= 400) return null
            val obj = JsonS.parse(lines.joinToString("")) as? J.Obj ?: return null
            val choices = obj.fields["choices"] as? J.Arr
            val msg = (choices?.items?.getOrNull(0) as? J.Obj)?.fields?.get("message") as? J.Obj
            return (msg?.fields?.get("content") as? J.Str)?.v
        } catch (_: Exception) {
            return null
        }
    }

    private fun parseUsage(o: J.Obj): Usage = Usage(
        promptTokens = (o.fields["prompt_tokens"] as? J.Num)?.v?.toInt() ?: 0,
        completionTokens = (o.fields["completion_tokens"] as? J.Num)?.v?.toInt() ?: 0,
        totalTokens = (o.fields["total_tokens"] as? J.Num)?.v?.toInt() ?: 0,
    )

    companion object {
        internal fun isLocalUrl(u: String): Boolean {
            return try {
                val host = URL(u.trim()).host.lowercase()
                host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "10.0.2.2"
            } catch (_: Exception) {
                false
            }
        }

        internal fun isRetryableStatus(code: Int): Boolean = code in setOf(429, 502, 503, 504)

        /** 统一解析代理串：支持 http:// / https:// / socks5:// / socks://，正确区分 HTTP 与 SOCKS 类型 */
        internal fun parseProxy(proxy: String?): Proxy? {
            val p = proxy?.trim()?.takeIf { it.isNotEmpty() } ?: return null
            return try {
                val lower = p.lowercase()
                val type = if (lower.startsWith("socks5://") || lower.startsWith("socks://")) {
                    Proxy.Type.SOCKS
                } else {
                    Proxy.Type.HTTP
                }
                var hp = p.removePrefix("http://").removePrefix("https://")
                    .removePrefix("socks5://").removePrefix("socks://").trimEnd('/')
                if (!hp.contains(':')) hp += ":1080"
                val idx = hp.lastIndexOf(':')
                val port = if (idx > 0) hp.substring(idx + 1).toIntOrNull() else null
                if (port != null) Proxy(type, InetSocketAddress(hp.substring(0, idx), port)) else null
            } catch (_: Exception) {
                null
            }
        }

        internal fun formatHttpError(code: Int, body: String): String {
            val base = when (code) {
                400 -> "400 请求参数被拒"
                401 -> "401 无效 Key（厂商拒绝了这枚 Key）"
                402 -> "402 余额不足（请先充值）"
                403 -> "403 无权访问（Key 未开通该模型）"
                404 -> "404 端点或模型名不对"
                429 -> "429 限流（请求太快或额度用完）"
                in 500..599 -> "$code 厂商服务端异常"
                else -> "HTTP $code 请求失败"
            }
            val msg = try {
                val obj = JsonS.parse(body) as? J.Obj
                val err = obj?.fields?.get("error") as? J.Obj
                (err?.fields?.get("message")?.str() ?: obj?.fields?.get("message")?.str())
                    ?.replace("\n", " ")?.trim()?.take(100)
            } catch (_: Exception) {
                null
            }
            return if (!msg.isNullOrBlank()) "$base（$msg）" else base
        }

        /**
         * 向导第③步「测试并保存」用的探针：**真连一次** `GET {base}/models`。
         *
         * 为什么不用一条最小对话试探：多数厂商对 /models 不做计费，而哪怕 1 token 的
         * 对话也会扣钱、也会被审计日志记一笔 —— 用户点一次"测试"就被计费是坏体验。
         * 只有厂商不实现 /models（404/405）时才退化成最小对话兜底。
         *
         * 返回 (是否连通, 人话原因)。原因要能直接贴到界面上，别返回异常对象。
         */
        fun probeApi(baseUrl: String, apiKey: String, proxy: String?, free: Boolean, model: String = ""): Pair<Boolean, String> {
            val base = baseUrl.trim().trimEnd('/')
            if (base.isEmpty()) return false to "Base URL 是空的"
            if (apiKey.isBlank() && !free) return false to "还没有填 Key"
            val proxyConn = if (isLocalUrl(base)) null else parseProxy(proxy)
            fun open(u: String): HttpURLConnection {
                val url = URL(u)
                return (if (proxyConn != null) url.openConnection(proxyConn) else url.openConnection()) as HttpURLConnection
            }
            fun reason(code: Int): String = when (code) {
                401 -> "401 无效 Key（厂商拒绝了这枚 Key）"
                402 -> "402 余额不足（要先充值）"
                403 -> "403 无权访问（Key 没开通这个模型）"
                404 -> "404 端点或模型名不对"
                429 -> "429 限流（请求太快或额度用完）"
                in 500..599 -> "$code 厂商服务端异常"
                else -> "$code 请求被拒绝"
            }
            fun hint(code: Int): String = when (code) {
                401 -> "回上一步整条重贴 Key（别带空格，别把 Base URL 粘进来）"
                402 -> "去服务商官网充一点，或点「稍后再说」先用免费链"
                404 -> "照教程里的模型名示例原样填；Base URL 别漏 /v1"
                429 -> "等几十秒再试；免费链最常见，配一枚 Key 就稳了"
                else -> "检查网络或代理；不确定就先点「稍后再说」用免费链"
            }
            var conn: HttpURLConnection? = null
            try {
                conn = open(base + "/models")
                conn.requestMethod = "GET"
                conn.setRequestProperty("Authorization", "Bearer " + apiKey.ifBlank { "free" })
                conn.connectTimeout = 12000
                conn.readTimeout = 12000
                val code = conn.responseCode
                if (code in 200..299) return true to ""
                if (code == 404 || code == 405) {
                    // 少数 OpenAI 兼容实现不实现 /models → 用 1 token 最小对话兜底
                    conn.disconnect()
                    conn = open(base + "/chat/completions")
                    conn.requestMethod = "POST"
                    conn.setRequestProperty("Content-Type", "application/json")
                    conn.setRequestProperty("Authorization", "Bearer " + apiKey.ifBlank { "free" })
                    conn.connectTimeout = 12000
                    conn.readTimeout = 20000
                    conn.doOutput = true
                    val body = "{\"model\":\"" + model + "\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":1,\"stream\":false}"
                    conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                    val code2 = conn.responseCode
                    if (code2 in 200..299) return true to ""
                    return false to (reason(code2) + "  ·  " + hint(code2))
                }
                return false to (reason(code) + "  ·  " + hint(code))
            } catch (e: Exception) {
                return false to ("网络层失败：" + (e.message ?: e.javaClass.simpleName) +
                    "  ·  多半是超时或被墙，填个代理再试；也可以先点「稍后再说」用免费链")
            } finally {
                try {
                    conn?.disconnect()
                } catch (_: Exception) {
                }
            }
        }
    }
}
