package com.dick.app

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.dick.core.ChatBridge
import com.dick.core.Commonsense
import com.dick.core.Lanes
import com.dick.core.LifeConfig
import com.dick.core.LifeCore
import com.dick.core.LifeTables
import com.dick.core.SpaceConfig
import com.dick.core.SpaceCore
import com.dick.core.WorldPacks
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * 生活 / 空间 / 世界卡库 —— 设置面板。
 *
 * 为什么要有它
 * ------------
 * 手机端这三层原来**只有命令入口**（`/生活` `/在哪` `/世界包`）：想看状态得打命令，
 * 想改年代/口味/忌口只能去写角色卡 `advanced.life` 的 JSON —— 那不叫"能设置"。
 *
 * 这一页是**全局**设置（落 `life_config.json` / `space_config.json`，与电脑端同一套字段名）。
 * 优先级必须写在脸上，否则一定有人问「我改了怎么没生效」：
 *
 *     角色卡 `advanced.life` / `advanced.space`  ＞  这一页的全局设置  ＞  自动认出（按世界卡关键词）
 *
 * 所以面板第一段就是「现在到底在用什么、来自哪儿」——直接调 `LifeCore.profileFor`，
 * 用它返回的 `eraFrom/regionFrom` 说清来源（角色卡 / 全局 / 自动认出）。
 *
 * 交互约定（照仓库其它面板）：
 *   · 开关、下拉、滑条 → 立即落盘（走 io 线，不占主线程）；
 *   · 文本框（口味/忌口/在哪儿）→ 关面板时落盘（否则每敲一个字写一次盘）；
 *   · 世界卡包列表要读目录 → 走 io 线，结果回主线程。
 */
@Composable
fun LifeSpaceSettingsPanel(vm: ChatViewModel, deps: DialogDeps) {
    if (!vm.showLifeSpace.value) return
    val theme = deps.theme
    val accent = deps.accent

    var life by remember { mutableStateOf(LifeCore.loadConfig()) }
    var space by remember { mutableStateOf(SpaceCore.loadConfig()) }
    // 文本框先放本地<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌：关面板才落盘
    var taste by remember { mutableStateOf(life.taste) }
    var avoid by remember { mutableStateOf(life.avoid) }
    var location by remember { mutableStateOf(life.location) }
    var packs by remember { mutableStateOf(emptyList<Pair<WorldPacks.Pack, Boolean>>()) }
    var status by remember { mutableStateOf("") }
    var pendingOverwrite by remember { mutableStateOf("") }

    fun reloadPacks() {
        Lanes.on(Lanes.io, "读世界卡库") {
            val got = listInstalled()
            withContext(Dispatchers.Main) { packs = got }
        }
    }

    // 卡包列表（名字 + 摘要 + 有没有装过）—— 读盘，走 io 线
    LaunchedEffect(Unit) { reloadPacks() }

    fun persistLife(c: LifeConfig) {
        life = c
        Lanes.on(Lanes.io, "生活层配置") { LifeCore.saveConfig(c) }
    }

    fun persistSpace(c: SpaceConfig) {
        space = c
        Lanes.on(Lanes.io, "空间层配置") { SpaceCore.saveConfig(c) }
    }

    /** 装包：默认不覆盖；`overwrite=true` 时先备份再原子写（WorldPacks.install 里做的）。 */
    fun installPack(name: String, overwrite: Boolean) {
        Lanes.on(Lanes.io, "装入世界卡包") {
            val (ok, msg) = WorldPacks.install(name, null, overwrite)
            if (ok) ChatBridge.notifyWorldsChanged()
            val got = listInstalled()
            withContext(Dispatchers.Main) {
                status = msg
                packs = got
                vm.sysMsgs.add(ChatMsg("系统", msg))
            }
        }
    }

    // 关面板：先把文本框里的东西合并进去（有变化才写）
    val close = {
        val merged = life.copy(taste = taste, avoid = avoid, location = location)
        if (merged != life) persistLife(merged)
        vm.showLifeSpace.value = false
    }

    // 当前生效的是什么、来自哪儿（角色卡会盖过这一页）
    val roleJson = deps.roleJsonFor(null)
    val worldJson = deps.worldJsonFor()
    val profile = remember(life, roleJson, worldJson) {
        try {
            LifeCore.profileFor(roleJson, life, worldJson)
        } catch (_: Exception) {
            null
        }
    }
    val mapEra = remember(roleJson, worldJson) {
        try {
            Commonsense.effectiveEra(worldJson, roleJson)
        } catch (_: Exception) {
            ""
        }
    }
    val mapKind = remember(roleJson, worldJson) {
        try {
            Commonsense.detectKind(worldJson, roleJson)
        } catch (_: Exception) {
            ""
        }
    }
    // 默认交通方式只列**这张地图**（这个年代）真有的 —— 唐宋不该冒出地铁
    val transports = remember(roleJson, worldJson) {
        try {
            SpaceCore.transportOptions(SpaceCore.mapFor(roleJson, worldJson))
        } catch (_: Exception) {
            emptyList()
        }
    }

    Dialog(onDismissRequest = close, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(
            modifier = Modifier.fillMaxWidth(0.96f),
            shape = RoundedCornerShape(16.dp),
            color = theme.bg,
        ) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("生活 / 空间 / 世界卡库", fontSize = 15.sp, color = theme.text,
                        fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = close) { Text("关闭", color = theme.muted, fontSize = 13.sp) }
                }
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    Text(
                        "这一页是全局设置。优先级：角色卡 advanced.life / advanced.space ＞ 这里的全局设置 ＞ " +
                            "自动认出（按世界卡的年代关键词）。下面第一段就是「现在到底在用什么、来自哪儿」。",
                        fontSize = 11.sp, color = theme.muted, lineHeight = 15.sp,
                    )
                    Spacer(Modifier.height(8.dp))

                    // ---------------- 现在生效的是 ----------------
                    Head("现在生效的是", theme)
                    val p = profile
                    if (p == null) {
                        Text("算不出来（读配置失败）", fontSize = 12.sp, color = theme.danger)
                    } else {
                        Text(
                            "角色：" + p.role + "　年代：" + p.era + "（来自" + p.eraFrom + "）" +
                                "　地域：" + p.region + "（来自" + p.regionFrom + "）",
                            fontSize = 12.sp, color = theme.text, lineHeight = 16.sp,
                        )
                        Text(
                            "当前地图：" + mapEra + (if (mapKind.isNotBlank()) "（设定 " + mapKind + "）" else "") +
                                "　手边家伙：" + p.tools.take(4).joinToString("、"),
                            fontSize = 11.sp, color = theme.muted, lineHeight = 15.sp,
                        )
                        if (p.eraFrom == "角色卡" || p.regionFrom == "角色卡") {
                            Text(
                                "角色卡里写了" + (if (p.eraFrom == "角色卡") "年代" else "") +
                                    (if (p.eraFrom == "角色卡" && p.regionFrom == "角色卡") "和" else "") +
                                    (if (p.regionFrom == "角色卡") "地域" else "") +
                                    "，会盖过这一页的设置（在这里改看不到效果是正常的）——" +
                                    "要按全局走，就去角色卡的高级设置里删掉那几项。",
                                fontSize = 11.sp, color = theme.danger, lineHeight = 15.sp,
                            )
                        }
                    }
                    Spacer(Modifier.height(10.dp))

                    // ---------------- 生活层 ----------------
                    Head("生活层（吃饭）", theme)
                    CheckRow("启用", life.enabled) { persistLife(life.copy(enabled = it)) }
                    if (!life.enabled) {
                        Text("已关闭：不再注入【生活·那边】—— 每轮载荷里就没有时间、菜单、厨具、忌口这些了。",
                            fontSize = 11.sp, color = theme.danger, lineHeight = 15.sp)
                    }
                    PickerRow(
                        label = "年代（决定厨具与能吃到的食材）",
                        current = if (life.era == "auto") "自动（按世界卡认）" else life.era,
                        options = listOf("auto" to "自动（按世界卡认）") +
                            Commonsense.eraKeys().map { it to it },
                        theme = theme, accent = accent,
                    ) { persistLife(life.copy(era = it)) }
                    PickerRow(
                        label = "地域（决定哪一路菜）",
                        current = if (life.region == "auto") "自动（通用）" else life.region,
                        options = listOf("auto" to "自动（通用）") +
                            LifeTables.REGIONS.filter { it != "auto" }.map { it to it },
                        theme = theme, accent = accent,
                    ) { persistLife(life.copy(region = it)) }
                    OutlinedTextField(value = taste, onValueChange = { taste = it },
                        label = { Text("口味（如 清淡 / 重口 / 嗜甜；只加权，不硬挡）") }, singleLine = true,
                        modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(6.dp))
                    OutlinedTextField(value = avoid, onValueChange = { avoid = it },
                        label = { Text("忌口（逗号分隔，如 香菜,海鲜；名字与食材都匹配）") }, singleLine = true,
                        modifier = Modifier.fillMaxWidth())
                    CheckRow("注入里带「今天吃了什么」", life.showMeals) {
                        persistLife(life.copy(showMeals = it))
                    }
                    Text("注入字数上限：" + life.maxChars + " 字（时间与今天吃了什么是必须项，先保它们）",
                        fontSize = 11.sp, color = theme.muted)
                    Slider(
                        value = life.maxChars.toFloat(),
                        onValueChange = { life = life.copy(maxChars = it.toInt()) },
                        onValueChangeFinished = { persistLife(life) },
                        valueRange = 60f..600f,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(value = location, onValueChange = { location = it },
                        label = { Text("在哪儿做/吃（家 / 出租屋 / 宿舍 / 野外…）") }, singleLine = true,
                        modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(10.dp))

                    // ---------------- 空间层 ----------------
                    Head("空间层（不能瞬移）", theme)
                    CheckRow("启用", space.enabled) { persistSpace(space.copy(enabled = it)) }
                    if (!space.enabled) {
                        Text("已关闭：不再注入【空间】—— 她可以随便瞬移，位置标注也不再记位置。",
                            fontSize = 11.sp, color = theme.danger, lineHeight = 15.sp)
                    }
                    CheckRow("注入里列「这段时间够去哪」", space.showReachable) {
                        persistSpace(space.copy(showReachable = it))
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("列几条：", fontSize = 12.sp, color = theme.text)
                        TextButton(onClick = {
                            persistSpace(space.copy(reachableLimit = maxOf(1, space.reachableLimit - 1)))
                        }) { Text("−", fontSize = 16.sp) }
                        Text(space.reachableLimit.toString(), fontSize = 13.sp, color = accent)
                        TextButton(onClick = {
                            persistSpace(space.copy(reachableLimit = minOf(8, space.reachableLimit + 1)))
                        }) { Text("＋", fontSize = 16.sp) }
                    }
                    PickerRow(
                        label = "默认交通方式（只列当前地图真有的：唐宋不会有地铁）",
                        current = space.defaultTransport,
                        options = if (transports.isEmpty()) listOf("走路" to "走路")
                        else transports.map { it.first to it.first },
                        theme = theme, accent = accent,
                    ) { persistSpace(space.copy(defaultTransport = it)) }
                    CheckRow("跳得不合理时提醒（最多两次）", space.warnWhenImpossible) {
                        persistSpace(space.copy(warnWhenImpossible = it))
                    }
                    Text("注入字数上限：" + space.maxChars + " 字（截断时先保「她在哪、有多远」）",
                        fontSize = 11.sp, color = theme.muted)
                    Slider(
                        value = space.maxChars.toFloat(),
                        onValueChange = { space = space.copy(maxChars = it.toInt()) },
                        onValueChangeFinished = { persistSpace(space) },
                        valueRange = 100f..600f,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(Modifier.height(10.dp))

                    // ---------------- 世界卡库 ----------------
                    Head("世界卡库", theme)
                    Text(
                        "随 APK 附带的成套世界卡（" + packs.size + " 张）。装进 worlds/ 之后，在「世界」里勾上它 —— " +
                            "它会带上年代与地图，生活层/空间层跟着换口径。同名默认不覆盖（覆盖前会留一份 .bak-时间戳）。",
                        fontSize = 11.sp, color = theme.muted, lineHeight = 15.sp,
                    )
                    Spacer(Modifier.height(4.dp))
                    packs.forEach { (pack, installed) ->
                        Column(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(pack.name + (if (installed) "（已装入）" else ""),
                                        fontSize = 13.sp,
                                        color = if (installed) theme.muted else theme.text)
                                    Text(WorldPacks.describe(pack), fontSize = 11.sp, color = theme.muted)
                                }
                                TextButton(onClick = {
                                    if (installed) pendingOverwrite = pack.name
                                    else installPack(pack.name, false)
                                }) { Text(if (installed) "覆盖" else "装入", fontSize = 12.sp) }
                            }
                            if (pendingOverwrite == pack.name) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text("同名卡已存在：覆盖？（会先备份）", fontSize = 11.sp, color = theme.danger)
                                    Spacer(Modifier.weight(1f))
                                    TextButton(onClick = {
                                        pendingOverwrite = ""
                                        installPack(pack.name, true)
                                    }) { Text("确认覆盖", fontSize = 12.sp, color = theme.danger) }
                                    TextButton(onClick = { pendingOverwrite = "" }) {
                                        Text("取消", fontSize = 12.sp)
                                    }
                                }
                            }
                        }
                    }
                    if (packs.isEmpty()) {
                        Text("卡包列表是空的（第一次启动会把 APK 里的卡包释放到 world_packs/，稍后再看）。",
                            fontSize = 11.sp, color = theme.muted)
                    }
                    if (status.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(status, fontSize = 11.sp, color = theme.text, lineHeight = 15.sp)
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "开关 / 下拉 / 滑条立即生效（写 life_config.json / space_config.json，与电脑端同一套字段名）；" +
                            "文本框里的内容在关面板时写入。命令入口仍然在：/生活、/在哪、/世界包。",
                        fontSize = 11.sp, color = theme.muted, lineHeight = 15.sp,
                    )
                    Spacer(Modifier.height(6.dp))
                }
            }
        }
    }
}

/** 卡包列表 + 是否已装进 worlds/（读盘，只在 io 线上调）。 */
private fun listInstalled(): List<Pair<WorldPacks.Pack, Boolean>> =
    WorldPacks.listPacks().map { p ->
        p to File(WorldPacks.worldsDir(), WorldPacks.safeName(p.name) + ".json").isFile
    }

@Composable
private fun Head(title: String, theme: ThemeSpec) {
    Text(title, fontSize = 12.sp, color = theme.text, fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(bottom = 2.dp))
}

/** 勾选一行（照设置页里既有的写法：Checkbox + Text）。 */
@Composable
private fun CheckRow(text: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = checked, onCheckedChange = onChange)
        Text(text, fontSize = 13.sp, modifier = Modifier.padding(top = 2.dp))
    }
}

/**
 * 下拉一行。
 *
 * 用下拉而不是「点一下循环下一个」：年代有 12 个、交通方式按地图来，循环点选要按十几次，
 * 而用户是在找一个**特定**的年代（「明清」），不是在找「下一个」。
 */
@Composable
private fun PickerRow(
    label: String,
    current: String,
    options: List<Pair<String, String>>,
    theme: ThemeSpec,
    accent: Color,
    onPick: (String) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(label, fontSize = 11.sp, color = theme.muted)
        Box {
            OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) {
                Text(current, fontSize = 13.sp, color = accent)
            }
            DropdownMenu(
                expanded = open,
                onDismissRequest = { open = false },
                modifier = Modifier.width(240.dp),
            ) {
                // 内容直接放 DropdownMenu 的 ColumnScope 里（它自带滚动；外面再套滚动会测量递归）
                options.forEach { (show, value) ->
                    DropdownMenuItem(
                        text = { Text(show, fontSize = 13.sp) },
                        onClick = { open = false; onPick(value) },
                    )
                }
            }
        }
    }
}
