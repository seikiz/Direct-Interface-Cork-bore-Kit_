package com.dick.core

import java.io.ByteArrayOutputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.Proxy
import java.net.URL
import java.net.URLEncoder
import java.util.zip.GZIPInputStream
import java.util.zip.GZIPOutputStream

/**
 * 创意工坊（联网版）—— 与桌面版 html_app 接口协议一致：
 *   /api/health /api/stats /api/cards/list /api/worlds/list /api/search
 *   /api/cards/{id} /api/worlds/{id}（下载）
 *   POST /like、/upload（multipart）、DELETE /{id}
 *   可选请求头 X-API-Key；连接配置保存在数据目录 workshop_config.json
 *
 * gzip 传输通道（2026-10）：
 *   POST /api/{type}/upload/gz  body = gzip(JSON)，元数据走 X-Filename / X-Author / X-Tags
 *   GET  /api/{type}/{id}/gz    返回 gzip 体（Content-Encoding: gzip）
 *   能力看 /api/capabilities 的 features 里有没有 "gzip"；没有就回退 multipart。
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
            // 探活也直连：判定"这台服务器在不在"不该被系统代理干扰
            val conn = URL(base.trimEnd('/') + "/api/health").openConnection(Proxy.NO_PROXY) as HttpURLConnection
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
        // 直连：手机若在 Wi-Fi 里填了代理，系统代理会把稍大的请求体截断
        // （桌面端实测 1.3KB 包体经代理得到 502，直连 201）。跑团主机是局域网地址，更不该绕代理。
        // 用 openConnection(Proxy.NO_PROXY) 而不是 setProxy：后者在 Android 上不保证被采纳。
        val conn = url.openConnection(Proxy.NO_PROXY) as HttpURLConnection
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
    private const val DEFAULT_PUBLIC_URL = "http://154.94.226.240:8080"

    // ============ 传输节奏（与桌面端同一套契约） ============
    //  链路按"每设备每 500ms 一次"设计（40 Mbit ≈ 5MB/s）：并发/连打会把水管灌满，
    //  服务器也会按 rate_per_min 回 429。所以 gz 上传与下载都走同一个闸门：
    //  串行（同一时刻只有一个传输在飞）+ 最小间隔。
    //  间隔**优先用服务器下发的** limits.min_interval_ms（以后换 100MB/s 只改服务器
    //  环境变量、客户端不用重新发版），读不到才用下面这个兜底值。
    private const val XFER_MIN_INTERVAL_MS = 500L

    /** 429 退避重试上限（超过就如实报"链路限流"） */
    private const val XFER_MAX_RETRY = 3

    /** 上传前要剔掉的**本地历史/状态**键（与 net.py、桌面端的 LOCAL_STATE_KEYS 同一份名单）。
     *
     *  语义是"每次上传都是新卡"：聊天树里是用户真实的私密对话，传到公网工坊既
     *  泄漏隐私又白白撑大包体（实测 咲.json 16KB → 2KB）。卡面字段
     *  （name/system_prompt/personality/appearance/greeting/scenario/description/
     *  tags/author/version/params/rules/entries…）一个都不动，也**不递归**进
     *  params/rules 里 —— 那里的同名键是作者自己写的数据，不是运行期状态。 */
    private val LOCAL_STATE_KEYS = listOf(
        "history_tree", "_tree_ts", "tree_ts", "messages", "chat_history", "_history",
        "memory", "memories", "preferences", "_indices", "_trpg_lock",
        "last_leaf_id", "current_leaf_id", "session", "state"
    )

    /** 传输闸门用的锁 + 上次发送时刻。
     *  这是**阻塞**代码（HttpURLConnection，不是挂起函数），所以用 ReentrantLock
     *  而不是 kotlinx 的 Mutex —— 后者是给协程用的，在这里得 runBlocking 绕一圈，
     *  反而会让"同一时刻只有一个传输"这条保证变得不好读。
     *  时刻用 SystemClock.elapsedRealtime()：单调时钟，用户改系统时间不会变负。 */
    private val xferMutex = java.util.concurrent.locks.ReentrantLock()
    private var lastSendAt = 0L

    /** 占用一次传输窗口：串行 + 最小间隔。 */
    private fun <T> withXferSlot(block: () -> T): T {
        xferMutex.lock()
        try {
            val wait = minIntervalMs() - (android.os.SystemClock.elapsedRealtime() - lastSendAt)
            if (wait > 0) {
                try {
                    Thread.sleep(wait)      // 还没到下一次的窗口，就等着（不并发突发）
                } catch (_: InterruptedException) {
                }
            }
            lastSendAt = android.os.SystemClock.elapsedRealtime()
            return block()
        } finally {
            xferMutex.unlock()
        }
    }

    /** 两次传输的最小间隔：优先服务器下发的 limits.min_interval_ms。 */
    private fun minIntervalMs(): Long {
        val v = capabilities().limits["min_interval_ms"] ?: 0L
        return if (v in 1L..60000L) v else XFER_MIN_INTERVAL_MS
    }

    /** 读响应体：显式 Accept-Encoding: gzip 之后，HttpURLConnection **不会**自动解压
     *  （它只负责收发字节），所以这里按 Content-Encoding 用 GZIPInputStream 解；
     *  另外按 gzip 魔数 1f 8b 兜一层 —— 中间层把 Content-Encoding 头丢掉时也能解。 */
    private fun readMaybeGzip(conn: HttpURLConnection, ok: Boolean): ByteArray {
        val stream = (if (ok) conn.inputStream else conn.errorStream) ?: return ByteArray(0)
        val body = stream.use { it.readBytes() }
        val enc = (conn.getHeaderField("Content-Encoding") ?: "").lowercase()
        val looksGzip = body.size > 2 && body[0] == 0x1f.toByte() && body[1] == 0x8b.toByte()
        if (!enc.contains("gzip") && !looksGzip) return body
        if (!looksGzip) return body               // 头说压了、体却不是 gzip：别硬解
        return try {
            GZIPInputStream(body.inputStream()).use { it.readBytes() }
        } catch (_: Exception) {
            body                                  // 解不开就原样给（上层按坏 JSON 报错）
        }
    }

    private fun request(
        path: String,
        method: String = "GET",
        params: Map<String, String> = emptyMap(),
        body: ByteArray? = null,
        contentType: String? = null,
        timeoutMs: Int = 8000,
        extraHeaders: Map<String, String> = emptyMap(),
    ): Resp {
        var u = path
        if (params.isNotEmpty()) {
            u += "?" + params.entries.joinToString("&") { (k, v) ->
                URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8")
            }
        }
        // 直连优先：理由同 httpAt —— 系统代理会把较大的上传体截断成 502
        val conn = urlFor(u).openConnection(Proxy.NO_PROXY) as HttpURLConnection
        conn.requestMethod = method
        conn.connectTimeout = timeoutMs
        conn.readTimeout = timeoutMs
        if (apiKey.isNotBlank()) conn.setRequestProperty("X-API-Key", apiKey)
        // HttpURLConnection **默认不发** Accept-Encoding（浏览器才会），
        // 所以想拿到压缩响应必须显式加 —— 否则服务器的 JSON 压缩通道永远不触发。
        conn.setRequestProperty("Accept-Encoding", "gzip")
        for ((k, v) in extraHeaders) conn.setRequestProperty(k, v)
        if (body != null) {
            conn.doOutput = true
            if (contentType != null) conn.setRequestProperty("Content-Type", contentType)
            conn.outputStream.use { it.write(body) }
        }
        val code = conn.responseCode
        val data = readMaybeGzip(conn, code < 400)
        // 头也带出来：429 的 Retry-After 在头里（JSON 里也有一份 body 兜底）
        val headers = mutableMapOf<String, String>()
        try {
            for ((k, vs) in conn.headerFields) {
                if (k != null && vs != null && vs.isNotEmpty()) headers[k.lowercase()] = vs[0]
            }
        } catch (_: Exception) {
        }
        conn.disconnect()
        return Resp(code, data, headers)
    }

    /** 一次工坊响应。**刻意保留 component1/component2**：仓库里几十处
     *  `val (code, body) = request(...)` 的写法因此一行都不用改。 */
    class Resp(val code: Int, val body: ByteArray, val headers: Map<String, String> = emptyMap()) {
        operator fun component1(): Int = code
        operator fun component2(): ByteArray = body
    }

    // ============ 能力协商（与桌面端 _ws_caps 同一套形状） ============

    /** 服务器能力：types / features / limits。老服务器没有 /api/capabilities → old=true。 */
    data class Caps(
        val types: Set<String>,
        val features: Set<String>,
        val limits: Map<String, Long>,
        val old: Boolean,
    )

    private var capsCache: Pair<Caps, Long>? = null
    private const val CAPS_TTL_MS = 5 * 60 * 1000L      // 5 分钟

    /** 读 /api/capabilities（缓存 5 分钟）。客户端据此决定走不走 gzip、发多快。 */
    fun capabilities(): Caps {
        val now = System.currentTimeMillis()
        capsCache?.let { if (now - it.second < CAPS_TTL_MS) return it.first }
        var caps = Caps(emptySet(), emptySet(), emptyMap(), true)
        try {
            val (code, body) = request("/api/capabilities", timeoutMs = 6000)
            if (code < 400) {
                val o = JsonS.parse(String(body, Charsets.UTF_8)) as? J.Obj
                val types = mutableSetOf<String>()
                (o?.fields?.get("types") as? J.Arr)?.items?.forEach { t ->
                    val name = when (t) {
                        is J.Str -> t.v
                        is J.Obj -> t.fields["name"]?.str() ?: ""
                        else -> ""
                    }
                    name.trim().lowercase().takeIf { it.isNotEmpty() }?.let { types.add(it) }
                }
                val features = mutableSetOf<String>()
                (o?.fields?.get("features") as? J.Arr)?.items?.forEach { f ->
                    (f as? J.Str)?.v?.trim()?.lowercase()?.takeIf { it.isNotEmpty() }
                        ?.let { features.add(it) }
                }
                val limits = mutableMapOf<String, Long>()
                (o?.fields?.get("limits") as? J.Obj)?.fields?.forEach { (k, v) ->
                    ((v as? J.Num)?.v)?.toLong()?.let { limits[k] = it }
                }
                if (types.isNotEmpty()) caps = Caps(types, features, limits, false)
            }
        } catch (_: Exception) {
            // 老服务器 / 网络不通：当"没有能力"，所有新通道自动降级
        }
        capsCache = caps to now
        return caps
    }

    /** 服务器支持 gzip 传输通道吗？ */
    fun hasGzip(): Boolean = "gzip" in capabilities().features

    /** 上传前剔掉本地历史/状态（bytes 版）：解析 → 剔除 → 重新序列化。
     *
     *  解析不了就原样返回（让服务器去判 400）；没有可剔的键时返回**原字节**，
     *  避免"没改也重新序列化"把用户的排版/缩进悄悄改掉。 */
    private fun stripLocalStateBytes(raw: ByteArray): Pair<ByteArray, List<String>> {
        val o = try {
            JsonS.parse(String(raw, Charsets.UTF_8)) as? J.Obj
        } catch (_: Exception) {
            null
        } ?: return raw to emptyList()
        val gone = LOCAL_STATE_KEYS.filter { o.fields.containsKey(it) }
        if (gone.isEmpty()) return raw to emptyList()
        val copy = J.Obj()
        for ((k, v) in o.fields) if (k !in gone) copy.fields[k] = v
        return JsonS.stringify(copy, pretty = true).toByteArray(Charsets.UTF_8) to gone
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

    /** 下载在线作品到本地（重名自动加序号），返回保存的文件。
     *
     *  能力里有 gzip 就走 /api/<kind>/<id>/gz（省流量），否则普通下载；
     *  两条路都在传输闸门里（串行 + 最小间隔）。HttpURLConnection 不自动解压，
     *  解压由 request() → readMaybeGzip 按 Content-Encoding / gzip 魔数完成。 */
    fun download(id: String, type: String, filename: String): File {
        val kind = if (type == "角色卡") "cards" else "worlds"
        val targetDir = if (type == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir()
        var usedGz = hasGzip()
        val t0 = System.currentTimeMillis()
        val resp = withXferSlot {
            if (usedGz) {
                val gz = request("/api/" + kind + "/" + id + "/gz", timeoutMs = 30000)
                if (gz.code < 400) gz
                else {
                    usedGz = false        // 老服务器没这条 → 退回普通下载
                    request("/api/" + kind + "/" + id, timeoutMs = 30000)
                }
            } else {
                request("/api/" + kind + "/" + id, timeoutMs = 30000)
            }
        }
        if (resp.code >= 400) throw IllegalStateException("HTTP ${resp.code}")
        val body = resp.body
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
        logXfer("下载", body.size, body.size, System.currentTimeMillis() - t0, emptyList(), usedGz)
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

    /** 上传本地卡/世界卡；返回 null = 成功，否则是**能给人看的原因**。
     *
     *  流程（两端同一套，别再各写一份）：
     *    ① 剔掉本地历史/状态 —— "每次上传都是新卡"，聊天树绝不外传；
     *    ② 服务器能力里有 gzip → 压到 ByteArrayOutputStream 后 POST /upload/gz
     *       （文件名走 X-Filename，中文名 URL 编码；服务器 _url_unquote 会解回来）；
     *    ③ gz 接口不认（404/405/415/501）→ **自动回退** multipart，不让用户感知；
     *    ④ 传输在闸门里（串行 + 最小间隔），429 按 Retry-After 退避，最多 3 次。
     *
     *  以前只回 Boolean，UI 只能显示"❌ 上传失败"——线上服务器 auth=key 时，
     *  手机没填 Key 就是 401，用户完全看不出为什么（列表/下载是公开读，所以看起来
     *  "只有上传坏"）。 */
    fun uploadEx(type: String, name: String): String? {
        val kind = when (type) {
            "角色卡" -> "cards"
            "世界卡包" -> "packs"
            else -> "worlds"
        }
        val targetDir = when (kind) {
            "cards" -> AppEnv.savesDir()
            "packs" -> AppEnv.worldPacksDir()
            else -> AppEnv.worldsDir()
        }
        val fname = name.replace(Regex("[\\\\/:*?\"<>|]"), "_").take(60) + ".json"
        val f = File(targetDir, fname)
        if (!f.isFile) {
            val have = targetDir.listFiles()?.count { it.isFile && it.name.endsWith(".json") } ?: 0
            return "本地文件不存在：$fname（$targetDir 下共 $have 个 .json）"
        }
        // ① 去历史（在压缩之前做：先变小，再压，收益叠加）
        val (raw, gone) = stripLocalStateBytes(f.readBytes())
        // ② 有 gzip 能力就先压好；压不动/发不出去再回退
        var compressible = hasGzip()
        val gzBody: ByteArray? = if (compressible) gzipCompress(raw) else null
        if (compressible && gzBody == null) compressible = false
        var usedGz = false
        var resp = Resp(0, ByteArray(0))
        val t0 = System.currentTimeMillis()
        try {
            var attempt = 0
            while (true) {
                attempt++
                resp = withXferSlot {
                    var r: Resp? = null
                    if (compressible && !usedGz) {
                        r = sendGzip(kind, fname, gzBody!!)
                        if (r.code == 404 || r.code == 405 || r.code == 415 || r.code == 501) {
                            compressible = false      // 服务器没有这条接口 → 本轮改走 multipart
                            r = null
                        } else {
                            usedGz = r.code < 400
                        }
                    }
                    r ?: sendMultipart(kind, fname, name, raw)
                }
                if (resp.code != 429 || attempt >= XFER_MAX_RETRY) break
                val waitMs = retryAfterMs(resp)
                println("[工坊] 链路限流（429），${waitMs}ms 后重试（第 $attempt/$XFER_MAX_RETRY 次）")
                try {
                    Thread.sleep(waitMs)
                } catch (_: InterruptedException) {
                }
            }
        } catch (e: Exception) {
            return "网络错误：" + (e.message ?: e.javaClass.simpleName).take(80)
        }
        val costMs = System.currentTimeMillis() - t0
        if (resp.code < 400) {
            val sent = if (usedGz) (gzBody?.size ?: raw.size) else raw.size
            logXfer("上传", raw.size, sent, costMs, gone, usedGz)
            return null
        }
        if (resp.code == 429) return "链路限流，稍后再试（服务器一直回 429）"
        val detail = try {
            String(resp.body, Charsets.UTF_8).take(140)
        } catch (_: Exception) {
            ""
        }
        return when {
            resp.code == 401 || resp.code == 403 ->
                "服务器要求 Key（HTTP ${resp.code}）：请在「在线」页把 Key 填上再试" + (if (apiKey.isBlank()) "（当前没填）" else "（当前已填，可能不对）")
            resp.code == 404 ->
                "服务器没有这个接口（HTTP 404）——线上可能还是旧版，没有「$type」这一类"
            resp.code == 413 ->
                "压缩包解压后超过服务器上限（HTTP 413）：${detail.ifBlank { "换小一点的卡再试" }}"
            resp.code == 400 ->
                "服务器拒收（HTTP 400）：${detail.ifBlank { "压缩包/JSON 有问题" }}"
            else -> "HTTP ${resp.code}：" + detail
        }
    }

    /** gzip 压缩到内存（Jetpack 里没有现成的 ByteArray 版）。
     *  失败返回 null（例如 OOM）——调用方据此放弃压缩、直接发明文。 */
    private fun gzipCompress(raw: ByteArray): ByteArray? {
        return try {
            val out = ByteArrayOutputStream()
            GZIPOutputStream(out).use { it.write(raw) }
            out.toByteArray()
        } catch (_: Exception) {
            null
        }
    }

    /** 文件名放进 X-Filename 前转成 ASCII 安全的形式。
     *  HTTP 头只能带 ISO-8859-1，中文名直接塞会变乱码（甚至抛 IllegalArgumentException），
     *  所以做一次 URL 编码 —— 服务器（net.py 的 _url_unquote）会解回原名。 */
    private fun asciiHeaderName(name: String): String =
        URLEncoder.encode(name, "UTF-8").replace("+", "%20")

    /** gzip 上传：body 就是 gzip(JSON)，元数据走请求头（与桌面端同一个接口/同一套头）。 */
    private fun sendGzip(kind: String, fname: String, gzBody: ByteArray): Resp =
        request("/api/" + kind + "/upload/gz", method = "POST", body = gzBody,
            contentType = "application/json", timeoutMs = 30000,
            extraHeaders = mapOf("X-Filename" to asciiHeaderName(fname)))

    /** 老路径：multipart。保留原样（字段名 file / name、boundary 规则都不变），
     *  老服务器、以及 gz 接口不存在时的回退都走这条。 */
    private fun sendMultipart(kind: String, fname: String, name: String, raw: ByteArray): Resp {
        val boundary = "----DICK" + System.currentTimeMillis()
        val CRLF = "\r\n"
        val head = ("--" + boundary + CRLF +
            "Content-Disposition: form-data; name=\"name\"" + CRLF + CRLF + name + CRLF +
            "--" + boundary + CRLF +
            "Content-Disposition: form-data; name=\"file\"; filename=\"" + fname + "\"" + CRLF +
            "Content-Type: application/json" + CRLF + CRLF).toByteArray(Charsets.UTF_8)
        val tail = (CRLF + "--" + boundary + "--" + CRLF).toByteArray(Charsets.UTF_8)
        return request("/api/" + kind + "/upload", method = "POST", body = head + raw + tail,
            contentType = "multipart/form-data; boundary=" + boundary, timeoutMs = 30000)
    }

    /** 429 要等多久：优先 Retry-After 头（标准），其次 JSON 里的 retry_after，
     *  都没有就按最小间隔来一次。 */
    private fun retryAfterMs(resp: Resp): Long {
        val fromHeader = resp.headers["retry-after"]?.trim()?.toDoubleOrNull()
        val fromBody = try {
            ((JsonS.parse(String(resp.body, Charsets.UTF_8)) as? J.Obj)
                ?.fields?.get("retry_after") as? J.Num)?.v
        } catch (_: Exception) {
            null
        }
        val secs = fromHeader ?: fromBody ?: (XFER_MIN_INTERVAL_MS / 1000.0)
        return maxOf(XFER_MIN_INTERVAL_MS, (secs * 1000).toLong())
    }

    /** 本次耗时 / 压缩后字节数 / 平均吞吐（MB/s）：40Mbit 的水管有没有被打满，
     *  靠这行日志看，不靠感觉。 */
    private fun logXfer(what: String, rawSize: Int, sentSize: Int, costMs: Long,
                        gone: List<String>, gz: Boolean) {
        val secs = costMs / 1000.0
        val mbps = if (secs > 0) (sentSize / 1048576.0) / secs else 0.0
        val pct = if (rawSize > 0) 100.0 * sentSize / rawSize else 100.0
        val size = if (gz) "gzip ${rawSize}→${sentSize} 字节（${"%.0f".format(pct)}%）"
        else "明文 $sentSize 字节"
        val strip = if (gone.isEmpty()) "" else
            "，已剔掉 ${gone.size} 个本地键（${gone.take(3).joinToString("、")}）"
        println("[工坊] $what 完成：$size，耗时 ${"%.2f".format(secs)}s，" +
            "平均 ${"%.2f".format(mbps)} MB/s$strip")
    }

    /** 老接口：只要成败 */
    fun upload(type: String, name: String): Boolean = uploadEx(type, name) == null

    fun localRoles(): List<String> =
        AppEnv.savesDir().listFiles()?.filter { it.isFile && it.name.endsWith(".json") && !it.name.startsWith("_tree_") && !it.name.startsWith(".") }?.map { it.name }?.sorted() ?: emptyList()

    fun localWorlds(): List<String> =
        AppEnv.worldsDir().listFiles()?.filter { it.isFile && it.name.endsWith(".json") && !it.name.startsWith("_tree_") && !it.name.startsWith(".") }?.map { it.name }?.sorted() ?: emptyList()

    /** 预览用原文。
     *
     *  2026-12：上限从 6000 提到 512KB —— 已经够放下任何一张卡（实测最大的世界卡 131KB）。
     *  原来的 6000 是给「原样显示一段文本」用的；现在工坊把它当**结构化卡片**解析
     *  （ui/screens/workshop/CardPreview.kt），截断会让 JSON 解析失败、整张卡退化成原文。
     */
    fun preview(type: String, filename: String): String {
        val targetDir = if (type == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir()
        val f = File(targetDir, File(filename).name)
        return if (f.isFile) f.readText(Charsets.UTF_8).take(PREVIEW_MAX_CHARS) else ""
    }

    /** 预览原文上限（字符）。够大才能整份解析；再大就是异常文件了。 */
    private const val PREVIEW_MAX_CHARS = 512 * 1024

    fun deleteLocal(type: String, filename: String): Boolean {
        val targetDir = if (type == "角色卡") AppEnv.savesDir() else AppEnv.worldsDir()
        val f = File(targetDir, File(filename).name)
        return if (f.isFile) f.delete() else false
    }
}
