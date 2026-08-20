package com.dick.core

import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

data class Usage(
    val promptTokens: Int = 0,
    val completionTokens: Int = 0,
    val totalTokens: Int = 0,
)

/**
 * 流式聊天引擎 —— OpenAI 兼容接口（DeepSeek 等）。
 * 使用 JDK 内置 HttpClient，SSE 逐行解析 data: 帧（与 Python _stream_create 对齐）。
 *
 * 回调在后台线程触发；Compose UI 侧用 scope.launch(Dispatchers.Main) 收口（见 ui/Main.kt）。
 */
class ChatEngine(
    private val baseUrl: String = "https://api.deepseek.com",
    var apiKey: String = "",
    var model: String = "deepseek-v4-pro",
) {
    private val client: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(15))
        .build()

    @Volatile
    var isProcessing: Boolean = false
        private set

    private fun role(role: String, content: String): J.Obj {
        val o = J.Obj()
        o.fields["role"] = J.Str(role)
        o.fields["content"] = J.Str(content)
        return o
    }

    private fun buildBody(chain: List<MessageNode>, systemPrompt: String?, withUsage: Boolean): String {
        val messages = J.Arr()
        if (!systemPrompt.isNullOrBlank()) messages.items.add(role("system", systemPrompt))
        for (node in chain) {
            if (node.content.isNotBlank()) messages.items.add(role(node.role, node.content))
        }
        val body = J.Obj()
        body.fields["model"] = J.Str(model)
        body.fields["messages"] = messages
        body.fields["stream"] = J.Bool(true)
        if (withUsage) {
            val so = J.Obj()
            so.fields["include_usage"] = J.Bool(true)
            body.fields["stream_options"] = so
        }
        return JsonS.stringify(body)
    }

    fun send(
        chain: List<MessageNode>,
        systemPrompt: String?,
        onStream: (String) -> Unit = {},
        onResponse: (String, Usage?) -> Unit = { _, _ -> },
        onError: (String) -> Unit = {},
    ) {
        if (apiKey.isBlank()) {
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
                var response = post(buildBody(chain, systemPrompt, true))
                // 部分服务商不支持 stream_options → 去掉后重试一次（对应 Python TypeError 回退）
                if (response.statusCode() >= 400) {
                    response = post(buildBody(chain, systemPrompt, false))
                }
                if (response.statusCode() >= 400) {
                    onError("HTTP " + response.statusCode())
                    return@Thread
                }
                val full = StringBuilder()
                var usage: Usage? = null
                for (line in response.body()) {
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
                        // 单帧解析失败不中断整条流
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

    private fun post(body: String): HttpResponse<java.util.stream.Stream<String>> {
        val request = HttpRequest.newBuilder(URI.create(baseUrl.trimEnd('/') + "/chat/completions"))
            .header("Content-Type", "application/json")
            .header("Authorization", "Bearer " + apiKey)
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build()
        return client.send(request, HttpResponse.BodyHandlers.ofLines())
    }

    private fun parseUsage(o: J.Obj): Usage = Usage(
        promptTokens = (o.fields["prompt_tokens"] as? J.Num)?.v?.toInt() ?: 0,
        completionTokens = (o.fields["completion_tokens"] as? J.Num)?.v?.toInt() ?: 0,
        totalTokens = (o.fields["total_tokens"] as? J.Num)?.v?.toInt() ?: 0,
    )
}
