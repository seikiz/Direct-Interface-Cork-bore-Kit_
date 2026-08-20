package com.dick.plugins

import com.dick.core.J
import com.dick.core.JsonS
import java.net.HttpURLConnection
import java.net.URL
import java.util.Base64

/**
 * 传图补丁：DeepSeek 是纯文本模型，图片先走 OVH 免费视觉链（免 Key，每模型 2 次/分钟/IP，
 * 429 自动降级下一个模型）转成中文描述，再把描述喂给 DeepSeek 思考。
 * 链：Qwen3.5-397B-A17B → Qwen2.5-VL-72B-Instruct → Qwen3.6-27B → Mistral-Small-3.2-24B → Qwen3.5-9B
 */
object VisionHelper {
    private val MODELS = listOf(
        "Qwen3.5-397B-A17B",
        "Qwen2.5-VL-72B-Instruct",
        "Qwen3.6-27B",
        "Mistral-Small-3.2-24B-Instruct-2506",
        "Qwen3.5-9B",
    )
    private val BASE = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"

    /** 图片 → 中文描述；全部模型失败返回 null */
    fun describe(bytes: ByteArray, mime: String, question: String, timeoutMs: Int = 60000): String? {
        val b64 = Base64.getEncoder().encodeToString(bytes)
        val dataUrl = "data:" + mime + ";base64," + b64
        val imagePart = J.Obj()
        imagePart.fields["type"] = J.Str("image_url")
        val iu = J.Obj()
        iu.fields["url"] = J.Str(dataUrl)
        imagePart.fields["image_url"] = iu
        val textPart = J.Obj()
        textPart.fields["type"] = J.Str("text")
        textPart.fields["text"] = J.Str(question)
        val msg = J.Obj()
        msg.fields["role"] = J.Str("user")
        msg.fields["content"] = J.Arr(mutableListOf(imagePart, textPart))
        val body = J.Obj()
        body.fields["messages"] = J.Arr(mutableListOf(msg))
        body.fields["max_tokens"] = J.Num(4096.0, "4096")
        body.fields["stream"] = J.Bool(false)
        for (model in MODELS) {
            body.fields["model"] = J.Str(model)
            try {
                val (code, lines) = post(JsonS.stringify(body), timeoutMs)
                if (code == 429) continue
                if (code >= 400) continue
                val obj = JsonS.parse(lines.joinToString("")) as? J.Obj ?: continue
                val choices = obj.fields["choices"] as? J.Arr
                val m = (choices?.items?.getOrNull(0) as? J.Obj)?.fields?.get("message") as? J.Obj
                val text = (m?.fields?.get("content") as? J.Str)?.v
                if (!text.isNullOrBlank()) return text
            } catch (_: Exception) {
            }
        }
        return null
    }

    private fun post(body: String, timeoutMs: Int): Pair<Int, List<String>> {
        val conn = URL(BASE + "/chat/completions").openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.connectTimeout = 15000
        conn.readTimeout = timeoutMs
        try {
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code >= 400) (conn.errorStream ?: conn.inputStream) else conn.inputStream
            return code to stream.bufferedReader(Charsets.UTF_8).readLines()
        } finally {
            conn.disconnect()
        }
    }
}
