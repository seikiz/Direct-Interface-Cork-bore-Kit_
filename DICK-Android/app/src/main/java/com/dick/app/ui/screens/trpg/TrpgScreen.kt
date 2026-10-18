package com.dick.app

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.TrpgSession
import com.dick.core.TrpgServer
import com.dick.core.Workshop
import kotlinx.coroutines.delay

/**
 * 跑团（去中心化 · 局域网房间管理）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `TrpgDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[TrpgDialog]（在 Dialogs.kt 末尾），转调 [TrpgScreen]。
 */
/** 跑团（去中心化 · 房间管理） */
@Composable
fun TrpgScreen(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    if (vm.showTrpg.value) {
    val context = deps.context
    val engine = deps.engine
    var sessions by remember { mutableStateOf(listOf<J.Obj>()) }   // 发现的房间
    var base by remember { mutableStateOf("") }                    // 主机地址（连到某房间前）
    var roomId by remember { mutableStateOf("") }                  // 当前房间 id
    var roomInfo by remember { mutableStateOf<J.Obj?>(null) }      // 当前房间元数据
    var myPc by remember { mutableStateOf("") }
    var story by remember { mutableStateOf(listOf<J.Obj>()) }
    var pcs by remember { mutableStateOf(listOf<String>()) }
    var turn by remember { mutableStateOf("") }
    var action by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var gmSession by remember { mutableStateOf<TrpgSession?>(null) }  // 手机当 GM 的本地会话
    var gmStarted by remember { mutableStateOf(false) }               // 本机 GM 已开始（进入游玩）
    var gmRoomId by remember { mutableStateOf("") }                   // 本机 GM 开的房间 id
    var gmServer by remember { mutableStateOf<TrpgServer?>(null) }    // 手机当 GM 的 HTTP 服务器
    var lanAddr by remember { mutableStateOf("") }                    // 本机局域网地址（别人加入用）
    var rooms by remember { mutableStateOf(listOf<J.Obj>()) }         // 当前主机的房间列表

    // 房间内状态轮询<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（成员连房间）
    LaunchedEffect(base, roomId) {
        if (base.isBlank() || roomId.isBlank()) return@LaunchedEffect
        while (vm.showTrpg.value && base.isNotBlank() && roomId.isNotBlank()) {
            try {
                val st = if (gmSession != null) {
                    JsonS.parse((gmSession!!).stateJson()) as? J.Obj
                } else Workshop.trpgRoomState(base, roomId)
                if (st != null) {
                    story = (st.fields["story"] as? J.Arr)?.items?.filterIsInstance<J.Obj>() ?: emptyList()
                    pcs = (st.fields["pcs"] as? J.Arr)?.items?.mapNotNull { it.str() } ?: emptyList()
                    turn = st.fields["turn"]?.str() ?: ""
                    if (gmSession != null) { roomInfo = null } // 本地当GM无需元数据
                }
            } catch (_: Exception) {}
            delay(2000)
        }
    }

    fun leaveAll() {
        if (base.isNotBlank() && roomId.isNotBlank() && myPc.isNotBlank() && gmSession == null) {
            try { Workshop.trpgRoomLeave(base, roomId, myPc) } catch (_: Exception) {}
        }
        gmSession = null; gmStarted = false; gmRoomId = ""
        try { gmServer?.stop() } catch (_: Exception) {}
        gmServer = null; lanAddr = ""
        vm.showTrpg.value = false; base = ""; roomId = ""; myPc = ""; story = emptyList(); pcs = emptyList(); action = ""; roomInfo = null
    }

    AlertDialog(
        onDismissRequest = { leaveAll() },
        title = { IconText("跑团 · 房间", icon = "theater_comedy") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                if (base.isBlank()) {
                    // ---- 一：选主机 / 当 GM ----
                    Button(onClick = {
                        // 手机当 GM：起一个局域网 HTTP 服务器，本机开房，别人连本机 IP 加入
                        val srv = TrpgServer(engine)
                        val p = srv.start(5080)
                        gmServer = srv
                        val roomId0 = srv.createRoom("我的房间", "", listOf("凛","咲"))
                        gmRoomId = roomId0
                        gmSession = srv.roomSession(roomId0)
                        lanAddr = srv.lanIp() + ":" + p
                        base = "local://gm"
                        roomId = roomId0
                        roomInfo = null
                    }, modifier = Modifier.fillMaxWidth()) { IconText("我当 GM（本机开房）", iconSize = 15.dp, icon = "mic") }
                    Text("或连接局域网主机：", fontSize = 11.sp, color = theme.muted)
                    Button(onClick = { sessions = Workshop.discoverTrpg() }, modifier = Modifier.fillMaxWidth()) { IconText("查找附近跑团", iconSize = 15.dp, icon = "radio") }
                    if (sessions.isEmpty()) Text("同一 Wi-Fi 让任一设备开房（PC 或手机当 GM），再查找；也可直接输入地址", fontSize = 11.sp, color = theme.muted)
                    sessions.forEach { s ->
                        TextButton(onClick = { base = s.fields["url"]?.str() ?: ""; rooms = Workshop.trpgRooms(base) }, modifier = Modifier.fillMaxWidth()) {
                            IconText((s.fields["gm"]?.str() ?: "房间") + " @ " + (s.fields["url"]?.str() ?: ""), fontSize = 13.sp, iconSize = 14.dp, icon = "casino")
                        }
                    }
                } else if (gmSession != null && !gmStarted) {
                    // ---- 二：本机当 GM 模式（未开始配置） ----
                    IconText("本机 GM · 设 GM/队伍", fontSize = 12.sp, iconSize = 13.dp, icon = "mic")
                    // 2026-12 文案清理：这里必须给用户一个"照抄就能连"的地址，所以保留地址本身，
                    // 但不再带 http:// 这种协议前缀（用户原话：别把技术说明摊在界面上）。
                    if (lanAddr.isNotBlank()) IconText("别的设备输入 $lanAddr 加入", fontSize = 12.sp, color = deps.accent, iconSize = 13.dp, icon = "link")
                    OutlinedTextField(value = gmSession!!.gm, onValueChange = { gmSession!!.gm = it },
                        label = { Text("GM 卡名") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Text("房间名：", fontSize = 11.sp)
                    val roomNameS = remember { mutableStateOf("") }
                    OutlinedTextField(value = roomNameS.value, onValueChange = { roomNameS.value = it },
                        label = { Text("给房间起名") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    if (pcs.isEmpty()) Text("点下方「开始」用默认队伍（凛、咲）", fontSize = 11.sp, color = theme.muted)
                    Button(onClick = {
                        val gm = gmSession!!.gm.ifBlank { "咲" }
                        val pcList = if (pcs.isEmpty()) listOf("凛","咲") else pcs
                        gmSession!!.let { s -> s.gm = gm; s.pcs.clear(); s.pcs.addAll(pcList); s.turn = pcList.firstOrNull() ?: "" }
                        myPc = pcList.firstOrNull() ?: ""   // 本机 GM 默认操控第一名 PC
                        gmStarted = true
                        busy = false
                    }, modifier = Modifier.fillMaxWidth()) { Text("▶ 开始跑团") }
                } else if (roomId.isBlank()) {
                    // ---- 三：选房间（连接主机后） ----
                    Text("房间：${base}", fontSize = 11.sp, color = theme.muted)
                    TextButton(onClick = { rooms = Workshop.trpgRooms(base) }, modifier = Modifier.fillMaxWidth()) { Text("↻ 刷新房间列表") }
                    if (rooms.isEmpty()) Text("主机暂无房间，或点击下方创建", fontSize = 11.sp, color = theme.muted)
                    rooms.forEach { r ->
                        val n = r.fields["name"]?.str() ?: "未命名房间"
                        val g = r.fields["gm"]?.str() ?: ""; val j = r.fields["joined"]?.str() ?: "0"
                        TextButton(onClick = { roomId = r.fields["id"]?.str() ?: ""; roomInfo = r }, modifier = Modifier.fillMaxWidth()) {
                            IconText("$n · GM:$g · ${j}人", fontSize = 13.sp, iconSize = 14.dp, icon = "home")
                        }
                    }
                    // 创建房间（连到主机）
                    val createName = remember { mutableStateOf("") }
                    val createGm = remember { mutableStateOf("") }
                    OutlinedTextField(value = createName.value, onValueChange = { createName.value = it }, label = { Text("新房间名") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(value = createGm.value, onValueChange = { createGm.value = it }, label = { Text("GM 卡名") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Button(onClick = {
                        val id = Workshop.trpgCreateRoom(base, createName.value.ifBlank { "新房间" }, createGm.value.ifBlank { "咲" }, listOf("凛","咲"))
                        if (id != null) { roomId = id; rooms = Workshop.trpgRooms(base) }
                    }, modifier = Modifier.fillMaxWidth()) { IconText("在此主机创建房间", iconSize = 15.dp, icon = "add") }
                } else {
                    // ---- 四：房间内游玩（成员或本地GM） ----
                    Text("已入房间：" + (roomInfo?.fields?.get("name")?.str() ?: roomId), fontSize = 11.sp, color = theme.muted)
                    if (myPc.isBlank()) {
                        Text("选择你的角色：", fontSize = 12.sp)
                        pcs.forEach { pc ->
                            TextButton(onClick = {
                                val ok = gmSession != null || Workshop.trpgRoomJoin(base, roomId, pc)
                                if (ok) myPc = pc
                            }, modifier = Modifier.fillMaxWidth()) { IconText(pc, fontSize = 13.sp, iconSize = 14.dp, icon = "person") }
                        }
                        if (pcs.isEmpty()) Text("等待主机设置队伍…", fontSize = 11.sp, color = theme.muted)
                    } else {
                        Text("当前行动者：" + (turn.ifBlank { myPc }), fontSize = 12.sp, color = theme.muted)
                        story.forEach { s ->
                            val actor = s.fields["actor"]?.str() ?: ""
                            val gm = s.fields["gm"]?.str() ?: ""
                            IconText(actor + "：" + (s.fields["action"]?.str() ?: ""), fontSize = 12.sp, color = theme.muted, iconSize = 13.dp, icon = "person")
                            if (gm.isNotBlank()) IconText("GM：" + gm, fontSize = 13.sp, color = theme.text, iconSize = 14.dp, icon = "record_voice_over")
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            OutlinedTextField(value = action, onValueChange = { action = it },
                                label = { Text("$myPc 的行动") }, singleLine = true, modifier = Modifier.weight(1f))
                            Button(onClick = {
                                if (action.isBlank()) return@Button
                                busy = true
                                if (gmSession != null) {
                                    gmSession!!.act(myPc, action)
                                } else {
                                    Workshop.trpgRoomAct(base, roomId, myPc, action)
                                }
                                action = ""; busy = false
                            }, enabled = !busy) { Text("行动") }
                        }
                        TextButton(onClick = { leaveAll() }, modifier = Modifier.fillMaxWidth()) { IconText("退出本局", fontSize = 13.sp, color = theme.danger, iconSize = 14.dp, icon = "sports_score") }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { leaveAll() }) { Text("完成") } },
        dismissButton = { TextButton(onClick = { leaveAll() }) { Text("取消") } },
    )
    }
}
