package com.dick.core

import java.net.Inet4Address
import java.net.NetworkInterface
import java.net.ServerSocket
import java.util.UUID

/**
 * 手机端局域网跑团 HTTP 服务器 —— 让"手机当 GM 开房"真正可加入：
 * 本机跑一个 ServerSocket，暴露与 PC 端 trpg_server.py 一致的接口：
 *   GET  /api/rooms            -> 房间列表
 *   POST /api/rooms            -> 创建房间 {name,gm,pcs}
 *   GET  /api/rooms/<id>/state
 *   POST /api/rooms/<id>/join|leave|act
 * 别的设备（手机/PC/浏览器）连本机局域网 IP:端口 即可看到并加入这些房间。
 *
 * 与 TrpgSession 配合：本类持有所有房间（id -> TrpgSession），
 * GM 推理用各房间的 ChatEngine（手机本地跑）。
 */
class TrpgServer(private val engine: ChatEngine) {

    private val rooms = HashMap<String, TrpgSession>()   // roomId -> session
    private val roomNames = HashMap<String, String>()     // roomId -> name
    private var server: ServerSocket? = null
    private var running = false
    private var port = 0

    /** 本地局域网 IP（供其它设备连接；失败回环） */
    fun lanIp(): String {
        try {
            for (n in NetworkInterface.getNetworkInterfaces()) {
                for (a in n.inetAddresses) {
                    if (a is Inet4Address && !a.isLoopbackAddress && a.hostAddress != null) {
                        val ip = a.hostAddress
                        if (ip.startsWith("192.168.") || ip.startsWith("10.") || ip.startsWith("172.")) return ip
                    }
                }
            }
        } catch (_: Exception) {}
        return "127.0.0.1"
    }

    fun start(listenPort: Int = 5080): Int {
        if (running) return port
        try {
            val s = ServerSocket(listenPort)
            server = s; port = s.localPort; running = true
            Thread { acceptLoop(s) }.apply { isDaemon = true }.start()
            return port
        } catch (e: Exception) {
            // 端口占用 → 试 0（自动分配）
            try {
                val s = ServerSocket(0)
                server = s; port = s.localPort; running = true
                Thread { acceptLoop(s) }.apply { isDaemon = true }.start()
                return port
            } catch (_: Exception) { return -1 }
        }
    }

    fun stop() {
        running = false
        try { server?.close() } catch (_: Exception) {}
        server = null
    }

    val isRunning: Boolean get() = running
    val port_: Int get() = port

    /** 本机直接创建房间（无需 HTTP）。返回 id。 */
    fun createRoom(name: String = "房间", gm: String = "", pcs: List<String> = emptyList()): String {
        val id = UUID.randomUUID().toString().substring(0, 8)
        rooms[id] = TrpgSession(engine, gm = gm, pcs = pcs, cardPrompt = { "" })
        roomNames[id] = name
        return id
    }

    /** 访问某个房间实例（本机当 GM 直接拿它操作/轮询）。 */
    fun roomSession(id: String): TrpgSession? = rooms[id]

    fun roomNamesList(): Map<String, String> = roomNames

    private fun acceptLoop(s: ServerSocket) {
        while (running) {
            try {
                val sock = s.accept()
                Thread { handle(sock) }.apply { isDaemon = true }.start()
            } catch (_: Exception) { if (running) continue else break }
        }
    }

    private fun handle(sock: java.net.Socket) {
        try {
            sock.soTimeout = 20000
            val reader = sock.getInputStream().bufferedReader(Charsets.UTF_8)
            // 读请求行 + 头
            val requestLine = reader.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 2) return
            val method = parts[0].uppercase()
            val rawPath = parts[1]
            val path = rawPath.substringBefore("?")
            // 读 body（有 Content-Length 才读；小请求直接按行读）
            val body = StringBuilder()
            var len = 0
            var line: String?
            while (true) {
                line = reader.readLine() ?: break
                if (line.isEmpty()) break
                if (line.lowercase().startsWith("content-length:")) len = line.substringAfter(":").trim().toIntOrNull() ?: 0
            }
            if (len > 0) { val buf = CharArray(len); val r = reader.read(buf); if (r > 0) body.append(buf, 0, r) }

            val (code, resp) = route(method, path, body.toString())
            val out = sock.getOutputStream()
            out.write(("HTTP/1.1 $code ${reason(code)}\r\nContent-Type: application/json; charset=utf-8\r\nAccess-Control-Allow-Origin: *\r\n\r\n$resp").toByteArray(Charsets.UTF_8))
            out.flush()
        } catch (_: Exception) {
        } finally {
            try { sock.close() } catch (_: Exception) {}
        }
    }

    private fun route(method: String, path: String, body: String): Pair<Int, String> {
        // 解析 JSON body（若空则空对象）
        val bodyObj = try { if (body.isNotBlank()) JsonS.parse(body) as? J.Obj else J.Obj() } catch (_: Exception) { J.Obj() }

        when {
            path == "/api/rooms" && method == "GET" -> return 200 to roomsListJson()
            path == "/api/rooms" && method == "POST" -> {
                val name = (bodyObj?.fields?.get("name") as? J.Str)?.v ?: "房间"
                val gm = (bodyObj?.fields?.get("gm") as? J.Str)?.v ?: ""
                val pcs = (bodyObj?.fields?.get("pcs") as? J.Arr)?.items?.mapNotNull { it.str() } ?: emptyList()
                val id = UUID.randomUUID().toString().substring(0, 8)
                val s = TrpgSession(engine, gm = gm, pcs = pcs, cardPrompt = { "" })
                rooms[id] = s; roomNames[id] = name
                return 200 to JsonS.stringify(J.Obj().apply { fields["ok"] = J.Str("true"); fields["id"] = J.Str(id); fields["name"] = J.Str(name) })
            }
            path.matches(Regex("""/api/rooms/[^/]+/state""")) && method == "GET" -> {
                val id = path.split("/")[3]
                val s = rooms[id] ?: return 404 to "{\"error\":\"房间不存在\"}"
                return 200 to s.stateJson()
            }
            path.matches(Regex("""/api/rooms/[^/]+/join""")) && method == "POST" -> {
                val id = path.split("/")[3]; val s = rooms[id] ?: return 404 to "{\"error\":\"房间不存在\"}"
                val name = (bodyObj?.fields?.get("name") as? J.Str)?.v ?: ""
                val player = (bodyObj?.fields?.get("player") as? J.Str)?.v ?: ""
                return 200 to s.join(name, player).first
            }
            path.matches(Regex("""/api/rooms/[^/]+/leave""")) && method == "POST" -> {
                val id = path.split("/")[3]; val s = rooms[id] ?: return 404 to "{\"error\":\"房间不存在\"}"
                val name = (bodyObj?.fields?.get("name") as? J.Str)?.v ?: ""
                return 200 to s.leave(name)
            }
            path.matches(Regex("""/api/rooms/[^/]+/act""")) && method == "POST" -> {
                val id = path.split("/")[3]; val s = rooms[id] ?: return 404 to "{\"error\":\"房间不存在\"}"
                val actor = (bodyObj?.fields?.get("actor") as? J.Str)?.v ?: ""
                val action = (bodyObj?.fields?.get("action") as? J.Str)?.v ?: ""
                val r = s.act(actor, action) ?: return 400 to "{\"error\":\"行动不能为空\"}"
                return 200 to r
            }
            path == "/api/state" -> return 200 to (rooms.values.firstOrNull()?.stateJson() ?: "{}")
            else -> return 404 to "{\"error\":\"not found\"}"
        }
    }

    private fun roomsListJson(): String {
        val arr = J.Arr(mutableListOf())
        rooms.forEach { (id, s) ->
            val o = J.Obj()
            o.fields["id"] = J.Str(id)
            o.fields["name"] = J.Str(roomNames[id] ?: "房间")
            o.fields["gm"] = J.Str(s.gm)
            o.fields["pcs"] = J.Arr(s.pcs.map { J.Str(it) }.toMutableList())
            o.fields["turn"] = J.Str(s.turn)
            o.fields["joined"] = J.Str(s.joined.size.toString())
            arr.items.add(o)
        }
        return JsonS.stringify(J.Obj().apply { fields["rooms"] = arr; fields["count"] = J.Str(rooms.size.toString()) })
    }

    private fun reason(code: Int): String = when (code) {
        200 -> "OK"; 400 -> "Bad Request"; 404 -> "Not Found"; else -> "OK"
    }
}
