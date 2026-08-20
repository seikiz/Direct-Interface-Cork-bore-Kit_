package com.dick.core

import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * 创意工坊（联网版）—— 与桌面版 html_app 接口协议一致：
 *   /api/health /api/stats /api/cards/list /api/worlds/list /api/search
 *   /api/cards/{id} /api/worlds/{id}（下载）
 *   POST /like、/upload（multipart）、DELETE /{id}
 *   可选请求头 X-API-Key；连接配置保存在数据目录 workshop_config.json
 */
object Workshop {

    var serverUrl: String = ""
        private set
    var apiKey: String = ""
        private set

    fun loadConfig() {
        try {
            val o = JsonS.parse(configFile().readText(Charsets.UTF_8)) as? J.Obj
            serverUrl = o?.fields?.get("server_url")?.str() ?: ""
            apiKey = o?.fields?.get("api_key")?.str() ?: ""
        } catch (_: Exception) {
        }
    }

    fun saveConfig(url: String, key: String) {
        serverUrl = url.trim()
        apiKey = key.trim()
        try {
            val o = J.Obj()
            o.fields["server_url"] = J.Str(serverUrl)
            o.fields["api_key"] = J.Str(apiKey)
            configFile().writeText(JsonS.stringify(o, pretty = true), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    private fun configFile(): File = File(AppEnv.dataRoot, "workshop_config.json")

    /** 自动部署：返回可用服务器地址（缓存 30 秒）。
     *  候选：配置地址 → 默认隧道地址。手机没有本机服务器，直接连云端。 */
    private var activeCache: Pair<String, Long>? = null

    fun activeServer(): String {
        val now = System.currentTimeMillis()
        activeCache?.let { if (now - it.second < 30000) return it.first }
        val candidates = listOf(serverUrl, DEFAULT_TUNNEL_URL).filter { it.isNotBlank() }
        for (base in candidates) {
            try {
                val conn = URL(base.trimEnd('/') + "/api/health").openConnection() as HttpURLConnection
                conn.connectTimeout = 2500
                conn.readTimeout = 2500
                if (apiKey.isNotBlank()) conn.setRequestProperty("X-API-Key", apiKey)
                val code = conn.responseCode
                conn.disconnect()
                if (code < 400) {
                    activeCache = base.trimEnd('/') to now
                    return base.trimEnd('/')
                }
            } catch (_: Exception) {
            }
        }
        val fallback = serverUrl.ifBlank { DEFAULT_TUNNEL_URL }
        activeCache = fallback.trimEnd('/') to now
        return fallback.trimEnd('/')
    }

    private fun urlFor(path: String): URL {
        val base = activeServer()
        if (base.isBlank()) throw IllegalStateException("未配置工坊服务器地址")
        return URL(base + path)
    }

    private const val DEFAULT_TUNNEL_URL = "https://referrals-lambda-geographical-says.trycloudflare.com"

    private fun request(
        path: String,
        method: String = "GET",
        params: Map<String, String> = emptyMap(),
        body: ByteArray? = null,
        contentType: String? = null,
        timeoutMs: Int = 8000,
    ): Pair<Int, ByteArray> {
        var u = path
        if (params.isNotEmpty()) {
            u += "?" + params.entries.joinToString("&") { (k, v) ->
                URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8")
            }
        }
        val conn = urlFor(u).openConnection() as HttpURLConnection
        conn.requestMethod = method
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        if (apiKey.isNotBlank()) conn.setRequestProperty("X-API-Key", apiKey)
        if (body != null) {
            conn.doOutput = true
            if (contentType != null) conn.setRequestProperty("Content-Type", contentType)
            conn.outputStream.use { it.write(body) }
        }
        val code = conn.responseCode
        val data = if (code < 400) conn.inputStream.use { it.readBytes() }
            else conn.errorStream?.use { it.readBytes() } ?: ByteArray(0)
        conn.disconnect()
        return code to data
    }

    fun health(): J.Obj? {
        val (code, body) = request("/api/health")
        if (code >= 400) return null
        return try { JsonS.parse(String(body, Charsets.UTF_8)) as? J.Obj } catch (_: Exception) { null }
    }

    fun stats(): J.Obj? {
        val (code, body) = request("/api/stats")
        if (code >= 400) return null
        return try { JsonS.parse(String(body, Charsets.UTF_8)) as? J.Obj } catch (_: Exception) { null }
    }

    /** 返回 (角色卡列表, 世界卡列表)；失败抛异常 */
    fun listResources(): Pair<List<J.Obj>, List<J.Obj>> {
        val (c1, b1) = request("/api/cards/list")
        val (c2, b2) = request("/api/worlds/list")
        if (c1 >= 400 || c2 >= 400) throw IllegalStateException("HTTP $c1 / $c2")
        val cards = ((JsonS.parse(String(b1, Charsets.UTF_8)) as? J.Arr)?.items ?: emptyList()).mapNotNull { it as? J.Obj }
        val worlds = ((JsonS.parse(String(b2, Charsets.UTF_8)) as? J.Arr)?.items ?: emptyList()).mapNotNull { it as? J.Obj }
        return cards to worlds
    }

    fun search(q: String, type: String): List<J.Obj> {
        val params = mutableMapOf<String, String>()
        if (q.isNotBlank()) params["q"] = q
        if (type.isNotBlank()) params["type"] = type
        val (code, body) = request("/api/search", params = params)
        if (code >= 400) throw IllegalStateException("HTTP $code")
        return ((JsonS.parse(String(body, Charsets.UTF_8)) as? J.Arr)?.items ?: emptyList()).mapNotNull { it as? J.Obj }
    }

    /** 下载在线作品到本地（重名自动加序号），返回保存的文件 */
    fun download(id: String, type: String, filename: String): File {
        val kind = if (type == "角色卡") "cards" else "worlds"
        val targetDir = if (type == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir()
        val (code, body) = request("/api/" + kind + "/" + id, timeoutMs = 30000)
        if (code >= 400) throw IllegalStateException("HTTP $code")
        var fname = filename.replace("..", "_")
        if (!fname.endsWith(".json")) fname += ".json"
        var dst = File(targetDir, fname)
        val base = fname.removeSuffix(".json")
        var i = 1
        while (dst.exists()) {
            dst = File(targetDir, base + "_" + i + ".json")
            i++
        }
        dst.writeBytes(body)
        return dst
    }

    // ============ 插件市场 ============

    /** 拉取插件列表（返回 在线插件, 本地已安装插件名） */
    fun listPlugins(): Pair<List<J.Obj>, List<String>> {
        val (code, body) = request("/api/plugins/list")
        if (code >= 400) throw IllegalStateException("HTTP $code")
        val plugins = ((JsonS.parse(String(body, Charsets.UTF_8)) as? J.Arr)?.items ?: emptyList())
            .mapNotNull { it as? J.Obj }
        val dir = AppEnv.dir("plugins")
        val local = dir.listFiles()?.filter { it.name.endsWith(".py") && !it.name.startsWith("_") }
            ?.map { it.name.removeSuffix(".py") } ?: emptyList()
        return plugins to local
    }

    /** 下载安装插件到 plugins/ 目录，返回安装的文件名 */
    fun installPlugin(id: String): String {
        val (code, body) = request("/api/plugins/" + id, timeoutMs = 30000)
        if (code >= 400) throw IllegalStateException("HTTP $code")
        var fname = id + ".py"
        try {
            val (_, lb) = request("/api/plugins/list")
            val lst = ((JsonS.parse(String(lb, Charsets.UTF_8)) as? J.Arr)?.items ?: emptyList())
                .mapNotNull { it as? J.Obj }
            val info = lst.firstOrNull { it.fields["id"]?.str() == id }
            info?.fields?.get("original_name")?.str()?.let { fname = it }
        } catch (_: Exception) {
        }
        fname = File(fname).name.replace("..", "_")
        if (!fname.endsWith(".py")) fname += ".py"
        val dir = AppEnv.dir("plugins")
        var dst = File(dir, fname)
        val base = fname.removeSuffix(".py")
        var i = 1
        while (dst.exists()) {
            dst = File(dir, base + "_" + i + ".py")
            i++
        }
        dst.writeBytes(body)
        return dst.name
    }

    fun like(id: String, type: String): Boolean {
        val kind = if (type == "角色卡") "cards" else "worlds"
        val (code, _) = request("/api/" + kind + "/" + id + "/like", method = "POST")
        return code < 400
    }

    fun deleteRemote(id: String, type: String): Boolean {
        val kind = if (type == "角色卡") "cards" else "worlds"
        val (code, _) = request("/api/" + kind + "/" + id, method = "DELETE")
        return code < 400
    }

    /** multipart 上传本地卡/世界卡 */
    fun upload(type: String, name: String): Boolean {
        val targetDir = if (type == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir()
        val fname = name.replace(Regex("[\\\\/:*?\"<>|]"), "_").take(60) + ".json"
        val f = File(targetDir, fname)
        if (!f.isFile) return false
        val kind = if (type == "角色卡") "cards" else "worlds"
        val boundary = "----DICK" + System.currentTimeMillis()
        val CRLF = "\r\n"
        val head = ("--" + boundary + CRLF +
            "Content-Disposition: form-data; name=\"name\"" + CRLF + CRLF + name + CRLF +
            "--" + boundary + CRLF +
            "Content-Disposition: form-data; name=\"file\"; filename=\"" + fname + "\"" + CRLF +
            "Content-Type: application/json" + CRLF + CRLF).toByteArray(Charsets.UTF_8)
        val tail = (CRLF + "--" + boundary + "--" + CRLF).toByteArray(Charsets.UTF_8)
        val fileBytes = f.readBytes()
        val body = head + fileBytes + tail
        val (code, _) = request("/api/" + kind + "/upload", method = "POST", body = body,
            contentType = "multipart/form-data; boundary=" + boundary, timeoutMs = 30000)
        return code < 400
    }

    fun localRoles(): List<String> =
        AppEnv.savesDir().listFiles()?.filter { it.name.endsWith(".json") }?.map { it.name }?.sorted() ?: emptyList()

    fun localWorlds(): List<String> =
        AppEnv.worldsDir().listFiles()?.filter { it.name.endsWith(".json") }?.map { it.name }?.sorted() ?: emptyList()

    fun preview(type: String, filename: String): String {
        val targetDir = if (type == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir()
        val f = File(targetDir, File(filename).name)
        return if (f.isFile) f.readText(Charsets.UTF_8).take(6000) else ""
    }

    fun deleteLocal(type: String, filename: String): Boolean {
        val targetDir = if (type == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir()
        val f = File(targetDir, File(filename).name)
        return if (f.isFile) f.delete() else false
    }
}
