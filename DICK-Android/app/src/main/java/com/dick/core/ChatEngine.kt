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
    var model: String = "deepseek-v4-flash",
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

    @Volatile
    var isProcessing: Boolean = false
        private set

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
        for (node in chain) {
            if (node.content.isNotBlank()) messages.items.add(role(node.role, node.content))
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
        // 配置了代理时走代理（http/https；支持 socks5:// 前缀解析）
        var proxyConn: Proxy? = null
        val p = proxy?.trim()?.takeIf { it.isNotEmpty() }
        if (p != null) {
            try {
                var hp = p.removePrefix("http://").removePrefix("https://")
                    .removePrefix("socks5://").removePrefix("socks://").trimEnd('/')
                if (!hp.contains(':')) {
                    hp += ":1080"
                }
                val idx = hp.lastIndexOf(':')
                if (idx > 0) {
                    val port = hp.substring(idx + 1).toIntOrNull()
                    if (port != null) {
                        proxyConn = Proxy(Proxy.Type.HTTP, InetSocketAddress(hp.substring(0, idx), port))
                    }
                }
            } catch (_: Exception) {
            }
        }
        return (if (proxyConn != null) url.openConnection(proxyConn) else url.openConnection()) as HttpURLConnection
    }

    /** 内置代理通道：base_url 编码成 <中转>/relay/<base64>，中转把请求转发到真实厂商 */
    private fun relayTargetUrl(): String {
        val b64 = java.util.Base64.getUrlEncoder().withoutPadding()
            .encodeToString(baseUrl.toByteArray(Charsets.UTF_8))
        return (relayBase?.trimEnd('/') ?: "") + "/relay/" + b64
    }

    private fun post(body: String): Pair<Int, List<String>> {
        var attempt = 0
        while (true) {
            attempt++
            val relayMode = relayOn && relayBase != null
            val effBase = if (relayMode) relayTargetUrl() else baseUrl
            val conn = openConn(effBase)
            try {
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("Authorization", "Bearer " + apiKey)
                conn.doOutput = true
                conn.connectTimeout = 15000
                conn.readTimeout = 120000
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
                val code = conn.responseCode
                val stream = if (code >= 400) (conn.errorStream ?: conn.inputStream) else conn.inputStream
                val lines = stream.bufferedReader(Charsets.UTF_8).readLines()
                return Pair(code, lines)
            } catch (e: java.io.IOException) {
                // 网络层失败（直连被墙/超时）→ 切内置代理通道重试一次
                if (attempt == 1 && relayBase != null && !relayOn) {
                    relayOn = true
                    continue
                }
                throw e
            } finally {
                conn.disconnect()
            }
        }
    }

    /** 流式发送：逐块回调 onStream(累计全文) */
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
        val worker = Thread {
            try {
                var result = post(buildBody(chain, systemPrompt, true, true))
                if (result.first >= 400) {
                    result = post(buildBody(chain, systemPrompt, false, true))
                }
                if (result.first >= 400) {
                    onError("HTTP " + result.first)
                    return@Thread
                }
                val full = StringBuilder()
                var usage: Usage? = null
                for (line in result.second) {
                    if (!line.startsWith("data:")) continue
                    val payload = line.removePrefix("data:").trim()
                    if (payload.isEmpty() || payload == "[DONE]") continue
                    try {
                        val obj = JsonS.parse(payload) as? J.Obj ?: continue
                        (obj.fields["usage"] as? J.Obj)?.let { usage = parseUsage(it) }
                        val choices = obj.fields["choices"] as? J.Arr
                        val first = choices?.items?.getOrNull(0) as? J.Obj
                        val delta = first?.fields?.get("delta") as? J.Obj
                        val text = (delta?.fields?.get("content") as? J.Str)?.v
                        if (!text.isNullOrEmpty()) {
                            full.append(text)
                            onStream(full.toString())
                        }
                    } catch (_: Exception) {
                    }
                }
                isProcessing = false
                onResponse(full.toString(), usage)
            } catch (e: Exception) {
                isProcessing = false
                onError(e.message ?: "网络错误")
            }
        }
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
}
