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
     *  候选：配置地址 → 局域网自动发现 → 默认隧道地址。手机没有本机服务器。
     *  同 Wi-Fi 下可自动找到电脑上的 net.py，无需手输 IP。 */
    private var activeCache: Pair<String, Long>? = null
    private var lanCache: Pair<String?, Long>? = null

    private fun discoverCached(): String? {
        val now = System.currentTimeMillis()
        lanCache?.let { if (now - it.second < 30000) return it.first }
        val lan = discoverServer()
        lanCache = lan to now
        return lan
    }

    private fun healthy(base: String): Boolean {
        return try {
            val conn = URL(base.trimEnd('/') + "/api/health").openConnection() as HttpURLConnection
            conn.connectTimeout = 2500
            conn.readTimeout = 2500
            if (apiKey.isNotBlank()) conn.setRequestProperty("X-API-Key", apiKey)
            val code = conn.responseCode
            conn.disconnect()
            code < 400
        } catch (_: Exception) {
            false
        }
    }

    /** 局域网自动发现：发 UDP 探测包，收集电脑 net.py 的回复（含 HTTP 端口）。 */
    fun discoverServer(): String? {
        try {
            val socket = java.net.DatagramSocket()
            try {
                socket.soTimeout = 2500
                socket.broadcast = true
                val magic = "DICK_DISCOVER_V1".toByteArray(Charsets.UTF_8)
                val target = java.net.InetAddress.getByName("255.255.255.255")
                socket.send(java.net.DatagramPacket(magic, magic.size, target, 5001))
                val buf = ByteArray(2048)
                val resp = java.net.DatagramPacket(buf, buf.size)
                socket.receive(resp)
                val text = String(buf, 0, resp.length, Charsets.UTF_8)
                val d = JsonS.parse(text) as? J.Obj ?: return null
                // 按 service 严格分流：本函数只认创意工<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌坊(save/sync)主机，绝不误连跑团主机
                if (d.fields["service"]?.str() != "dick-sync") return null
                val port = (d.fields["port"] as? J.Num)?.v?.toInt() ?: 5000
                val host = resp.address.hostAddress ?: return null
                return "http://" + host + ":" + port
            } finally {
                socket.close()
            }
        } catch (_: Exception) {
            return null
        }
    }

    /** 局域网跑团发现：向 UDP 5081 发 DICK_TRPG_DISCOVER_V1，收集跑团主机（PC 端 trpg_server）。 */
    fun discoverTrpg(discoverPort: Int = 5081): List<J.Obj> {
        val found = mutableListOf<J.Obj>()
        try {
            val s = java.net.DatagramSocket()
            s.broadcast = true
            val magic = "DICK_TRPG_DISCOVER_V1".toByteArray(Charsets.UTF_8)
            for (t in listOf("255.255.255.255", "127.0.0.1")) {
                try { s.send(java.net.DatagramPacket(magic, magic.size, java.net.InetAddress.getByName(t), discoverPort)) } catch (_: Exception) {}
            }
            val end = System.currentTimeMillis() + 2000
            s.soTimeout = 600
            while (System.currentTimeMillis() < end) {
                try {
                    val buf = ByteArray(2048)
                    val resp = java.net.DatagramPacket(buf, buf.size)
                    s.receive(resp)
                    val d = JsonS.parse(String(buf, 0, resp.length, Charsets.UTF_8)) as? J.Obj ?: continue
                    if (d.fields["service"]?.str() == "trpg" && d.fields["url"] != null) found.add(d)
                } catch (_: Exception) { break }
            }
            s.close()
        } catch (_: Exception) {}
        val seen = mutableSetOf<String>()
        return found.filter { seen.add(it.fields["url"]?.str() ?: "") }
    }

    // ---------- 跑团主机 HTTP（对 trpg_server 的主机地址请求） ----------
    private fun httpAt(base: String, path: String, method: String = "GET", body: ByteArray? = null, contentType: String? = null, timeoutMs: Int = 8000): Pair<Int, ByteArray> {
        val url = URL(base.trimEnd('/') + path)
        val conn = url.openConnection() as HttpURLConnection
        conn.requestMethod = method
        conn.connectTimeout = timeoutMs; conn.readTimeout = timeoutMs
        if (body != null) { conn.doOutput = true; if (contentType != null) conn.setRequestProperty("Content-Type", contentType); conn.outputStream.use { it.write(body) } }
        val code = conn.responseCode
        val data = if (code < 400) conn.inputStream.use { it.readBytes() } else conn.errorStream?.use { it.readBytes() } ?: ByteArray(0)
        conn.disconnect()
        return code to data
    }

    fun trpgState(base: String): J.Obj? {
        val (c, b) = httpAt(base, "/api/state")
        if (c >= 400) return null
        return try { JsonS.parse(String(b, Charsets.UTF_8)) as? J.Obj } catch (_: Exception) { null }
    }
    fun trpgJoin(base: String, pc: String): Boolean {
        val body = JsonS.stringify(J.Obj().apply { fields["name"] = J.Str(pc) }).toByteArray(Charsets.UTF_8)
        val (c, _) = httpAt(base, "/api/join", "POST", body, "application/json")
        return c < 400
    }
    fun trpgLeave(base: String, pc: String): Boolean {
        val body = JsonS.stringify(J.Obj().apply { fields["name"] = J.Str(pc) }).toByteArray(Charsets.UTF_8)
        val (c, _) = httpAt(base, "/api/leave", "POST", body, "application/json")
        return c < 400
    }
    fun trpgAct(base: String, actor: String, action: String): J.Obj? {
        val body = JsonS.stringify(J.Obj().apply { fields["actor"] = J.Str(actor); fields["action"] = J.Str(action) }).toByteArray(Charsets.UTF_8)
        val (c, b) = httpAt(base, "/api/act", "POST", body, "application/json", 120000)
        if (c >= 400) return null
        return try { JsonS.parse(String(b, Charsets.UTF_8)) as? J.Obj } catch (_: Exception) { null }
    }

    // ---------- 房间管理（去中心化跑团 · 多房间） ----------
    /** 列出房间：返回 [{id,name,gm,pcs,turn,joined,story_len}] */
    fun trpgRooms(base: String): List<J.Obj> {
        val (c, b) = httpAt(base, "/api/rooms", "GET")
        if (c >= 400) return emptyList()
        return try {
            val o = JsonS.parse(String(b, Charsets.UTF_8)) as? J.Obj ?: return emptyList()
            (o.fields["rooms"] as? J.Arr)?.items?.filterIsInstance<J.Obj>() ?: emptyList()
        } catch (_: Exception) { emptyList() }
    }

    /** 创建房间，返回 room id 或 null。 */
    fun trpgCreateRoom(base: String, name: String, gm: String, pcs: List<String>): String? {
        val body = JsonS.stringify(J.Obj().apply {
            fields["name"] = J.Str(name)
            fields["gm"] = J.Str(gm)
            fields["pcs"] = J.Arr(pcs.map { J.Str(it) }.toMutableList())
        }).toByteArray(Charsets.UTF_8)
        val (c, b) = httpAt(base, "/api/rooms", "POST", body, "application/json")
        if (c >= 400) return null
        return try {
            val o = JsonS.parse(String(b, Charsets.UTF_8)) as? J.Obj
            (o?.fields?.get("id") as? J.Str)?.v
        } catch (_: Exception) { null }
    }

    fun trpgDeleteRoom(base: String, roomId: String): Boolean {
        val (c, _) = httpAt(base, "/api/rooms/$roomId", "DELETE")
        return c < 400
    }

    /** 房间内状态（成员连该房间用）。 */
    fun trpgRoomState(base: String, roomId: String): J.Obj? {
        val (c, b) = httpAt(base, "/api/rooms/$roomId/state")
        if (c >= 400) return null
        return try { JsonS.parse(String(b, Charsets.UTF_8)) as? J.Obj } catch (_: Exception) { null }
    }

    fun trpgRoomJoin(base: String, roomId: String, pc: String): Boolean {
        val body = JsonS.stringify(J.Obj().apply { fields["name"] = J.Str(pc) }).toByteArray(Charsets.UTF_8)
        val (c, _) = httpAt(base, "/api/rooms/$roomId/join", "POST", body, "application/json")
        return c < 400
    }

    fun trpgRoomLeave(base: String, roomId: String, pc: String): Boolean {
        val body = JsonS.stringify(J.Obj().apply { fields["name"] = J.Str(pc) }).toByteArray(Charsets.UTF_8)
        val (c, _) = httpAt(base, "/api/rooms/$roomId/leave", "POST", body, "application/json")
        return c < 400
    }

    fun trpgRoomAct(base: String, roomId: String, actor: String, action: String): J.Obj? {
        val body = JsonS.stringify(J.Obj().apply { fields["actor"] = J.Str(actor); fields["action"] = J.Str(action) }).toByteArray(Charsets.UTF_8)
        val (c, b) = httpAt(base, "/api/rooms/$roomId/act", "POST", body, "application/json", 120000)
        if (c >= 400) return null
        return try { JsonS.parse(String(b, Charsets.UTF_8)) as? J.Obj } catch (_: Exception) { null }
    }

    fun activeServer(): String {
        val now = System.currentTimeMillis()
        activeCache?.let { if (now - it.second < 30000) return it.first }
        // 1) 显式配置
        val cfg = serverUrl.trimEnd('/')
        if (cfg.isNotBlank() && healthy(cfg)) { activeCache = cfg to now; return cfg }
        // 2) 局域网自动发现（同 Wi-Fi 找电脑）
        val lan = discoverCached()
        if (lan != null && healthy(lan)) { activeCache = lan to now; return lan }
        // 3) 公网零配置兜底：局域网找不到时，自动用维护的公网工坊地址（用户零填写）。
        //    这里是稳定命名隧道地址；换主机时只需替换 DEFAULT_PUBLIC_URL。
        if (DEFAULT_PUBLIC_URL.isNotBlank() && healthy(DEFAULT_PUBLIC_URL)) { activeCache = DEFAULT_PUBLIC_URL to now; return DEFAULT_PUBLIC_URL }
        val fallback = cfg.ifBlank { lan ?: "" }
        activeCache = fallback.trimEnd('/') to now
        return fallback.trimEnd('/')
    }

    private fun urlFor(path: String): URL {
        val base = activeServer()
        if (base.isBlank()) throw IllegalStateException("未配置工坊服务器地址")
        return URL(base + path)
    }

    // 公网零配置兜底地址：局域网找不到时自动用它（用户不必手动填）。
    // 这是部署好的 dick-workshop Worker 稳定地址（永不失效，转发到你的工坊）。
    private const val DEFAULT_PUBLIC_URL = "https://dick-workshop.seiki342008.workers.dev"

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

    // ============ 树存档同步（聊天进度互通） ============

    /** 后台预热局域网发现（避免在主线程做 UDP/超时导致 ANR）。走 net 线，别自己开裸线程。 */
    fun primeDiscovery() {
        try {
            Lanes.on(Lanes.net, "预热局域网发现") {
                try { discoverCached() } catch (_: Exception) {}
            }
        } catch (_: Exception) {}
    }

    /** 是否启用进度同步：显式配置了服务器，或局域网已发现到电脑（同 Wi-Fi）。
     *  仅查缓存，不做网络/超时，主线程安全。 */
    fun syncEnabled(): Boolean = serverUrl.isNotBlank() || lanCache?.first != null || DEFAULT_PUBLIC_URL.isNotBlank()

    private fun enc(cardId: String): String =
        URLEncoder.encode(cardId, "UTF-8").replace("+", "%20")

    /** 推送某角色的聊天树（后来者胜）。返回服务器时间戳或 null。 */
    fun pushSave(cardId: String, tree: J.Obj): String? {
        val body = JsonS.stringify(
            J.Obj().apply { fields["tree"] = tree }
        ).toByteArray(Charsets.UTF_8)
        val (code, resp) = request(
            "/api/save/" + enc(cardId),
            method = "POST", body = body, contentType = "application/json",
        )
        if (code >= 400) return null
        return try {
            ((JsonS.parse(String(resp, Charsets.UTF_8)) as? J.Obj)?.fields?.get("ts") as? J.Str)?.v
        } catch (_: Exception) { null }
    }

    /** 拉取某角色最新的聊天树。返回 (服务器时间戳, tree) 或 null（无存档/失败）。 */
    fun fetchSave(cardId: String): Pair<String, J.Obj>? {
        val (code, resp) = request("/api/save/" + enc(cardId))
        if (code >= 400) return null
        return try {
            val o = JsonS.parse(String(resp, Charsets.UTF_8)) as? J.Obj ?: return null
            val ts = (o.fields["ts"] as? J.Str)?.v ?: ""
            val tree = o.fields["tree"] as? J.Obj ?: return null
            ts to tree
        } catch (_: Exception) { null }
    }

    /** 推送模型连接配置（API 码等），后来者胜。返回是否成功。 */
    fun pushApi(apiKey: String, baseUrl: String, model: String, provider: String): Boolean {
        val body = JsonS.stringify(J.Obj().apply {
            fields["api_key"] = J.Str(apiKey)
            fields["base_url"] = J.Str(baseUrl)
            fields["model"] = J.Str(model)
            fields["provider"] = J.Str(provider)
        }).toByteArray(Charsets.UTF_8)
        val (code, _) = request("/api/sync/api", method = "POST", body = body, contentType = "application/json")
        return code < 400
    }

    /** 拉取共享的模型连接配置；无则返回 null。 */
    fun fetchApi(): J.Obj? {
        val (code, resp) = request("/api/sync/api")
        if (code >= 400) return null
        return try { JsonS.parse(String(resp, Charsets.UTF_8)) as? J.Obj } catch (_: Exception) { null }
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
        AppEnv.savesDir().listFiles()?.filter { it.isFile && it.name.endsWith(".json") && !it.name.startsWith("_tree_") && !it.name.startsWith(".") }?.map { it.name }?.sorted() ?: emptyList()

    fun localWorlds(): List<String> =
        AppEnv.worldsDir().listFiles()?.filter { it.isFile && it.name.endsWith(".json") && !it.name.startsWith("_tree_") && !it.name.startsWith(".") }?.map { it.name }?.sorted() ?: emptyList()

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
