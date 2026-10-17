package com.dick.app

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.J
import com.dick.core.Workshop
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/** 工坊列表的「类型」图标名（角色卡 / 世界卡包 / 世界卡）：返回的是 Material Symbols
 *  图标名，由 IconText 的 icon 参数画出来（名称取 icons/icons.json，别再往这里塞 emoji）。 */
private fun wsTypeIcon(t: String): String = when (t) {
    "角色卡" -> "theater_comedy"
    "世界卡包" -> "inventory_2"
    else -> "public"
}

/**
 * WorkshopScreen —— 创意工坊屏（本地 / 在线 / 插件 三个页签）。
 *
 * 纯结构搬家：内容从 Dialogs.kt 的 WorkshopDialog 逐字搬过来，只换住址。
 * 布局数值、文案、页签顺序、点击后的行为全部保持原样（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读（`by vm.xxx`）；派生读法在 WorkshopState.kt；
 *   · 对外依赖只认 WorkshopActions（一组回调 + 只读对象）；
 *   · 控件一律用 ui/components/ 的 Dick*。
 */
@Composable
fun WorkshopScreen(vm: ChatViewModel, acts: WorkshopActions) {
    val theme = acts.theme
    val scope = acts.scope
    val importCardLauncher = acts.importCardLauncher
    val wsExportLauncher = acts.wsExportLauncher
    val wsRefreshLocal = acts.refreshLocal
    val wsLoadOnline = acts.loadOnline
    val wsLoadPlugins = acts.loadPlugins
    val wsUploadLocal = acts.uploadLocal
    val wsSearchOnline = acts.searchOnline
    val wsDownloadSelected = acts.downloadSelected
    val wsLikeSelected = acts.likeSelected
    val wsDeleteSelected = acts.deleteSelected
    val wsInstallPlugin = acts.installPlugin
    val reloadRolesFromDisk = acts.reloadRolesFromDisk
    val reloadWorldsFromDisk = acts.reloadWorldsFromDisk
    var showWorkshop by vm.showWorkshop
    var wsTabOnline by vm.wsTabOnline
    var wsTabPlugin by vm.wsTabPlugin
    var wsPlugins by vm.wsPlugins
    var wsLocalPlugins by vm.wsLocalPlugins
    var wsInstallingId by vm.wsInstallingId
    val wsLocalRoles = vm.wsLocalRoles
    val wsLocalWorlds = vm.wsLocalWorlds
    var wsLocalType by vm.wsLocalType
    var wsLocalIdx by vm.wsLocalIdx
    var wsPreview by vm.wsPreview
    var wsServerInput by vm.wsServerInput
    var wsKeyInput by vm.wsKeyInput
    var wsStatus by vm.wsStatus
    var wsStatusIcon by vm.wsStatusIcon
    // 状态行 = 纯文本 + 图标名：图标由产生状态那一处点<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌名（→check_circle、→error…），
    // 文案里不再塞 emoji 字符。渲染点只有一个（下面的 DickTag），所以不必往回猜。
    fun wsSetStatus(text: String, icon: String? = null) {
        wsStatus = text
        wsStatusIcon = icon
    }
    val wsOnlineList = vm.wsOnlineList
    var wsOnlineIdx by vm.wsOnlineIdx
    var wsSearchInput by vm.wsSearchInput
    var wsExportTarget by vm.wsExportTarget
    if (showWorkshop) {
    DickDialog(
        onDismissRequest = { showWorkshop = false },
        title = { IconText(I18n.t("btn_workshop", "创意工坊"), icon = "home_repair_service") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Row {
                    DickTextButton(
                        label = if (!wsTabOnline && !wsTabPlugin) I18n.t("ws_local", "本地 ▾") else I18n.t("ws_local", "本地"),
                        onClick = { wsTabOnline = false; wsTabPlugin = false; wsRefreshLocal() },
                        fontSize = 12.sp, icon = "folder"
                    )
                    DickTextButton(
                        label = if (wsTabOnline) I18n.t("ws_online", "在线 ▾") else I18n.t("ws_online", "在线"),
                        onClick = { wsTabOnline = true; wsTabPlugin = false; wsLoadOnline() },
                        fontSize = 12.sp, icon = "language"
                    )
                    DickTextButton(
                        label = if (wsTabPlugin) "插件 ▾" else "插件",
                        onClick = { wsTabPlugin = true; wsTabOnline = false; wsLoadPlugins() },
                        fontSize = 12.sp, icon = "extension"
                    )
                    Spacer(Modifier.weight(1f))
                    // 状态串（上传成功 / 连接失败 / 要先填 Key …）：文案纯文本，图标走 icon 参数
                    DickTag(wsStatus, fontSize = 11.sp, iconSize = 12.dp, icon = wsStatusIcon)
                }
                if (!wsTabOnline && !wsTabPlugin) {
                    // 本地文件列表 = **白底卡片**（2026-12）：底色只从令牌来
                    //   · 未选：surface（浅色 = 白）+ line 描边（不描边就是白压白，看不见卡片）
                    //   · 选中：surface_2 + accent 描边（浅色主题下 surface_2 也是白，
                    //     所以选中只能靠强调色描边认出来 —— 原来那整块灰底在浅色弹窗里最扎眼）
                    Row {
                        Column(Modifier.weight(1f)) {
                            DickTag("角色卡", fontSize = 12.sp, icon = "folder")
                            wsLocalRoles.forEachIndexed { i, f ->
                                val sel = wsLocalType == "角色卡" && wsLocalIdx == i
                                DickCard(
                                    radius = 8.dp,
                                    tone = if (sel) DickSurfaceTone.Surface2 else DickSurfaceTone.Surface,
                                    outline = if (sel) theme.palette.accent else theme.line,
                                    outlineWidth = if (sel) 2.dp else 1.dp,
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp).clickable {
                                        wsLocalType = "角色卡"; wsLocalIdx = i
                                        wsPreview = Workshop.preview("角色卡", f)
                                    },
                                ) {
                                    Text(f.removeSuffix(".json"), fontSize = 12.sp, color = theme.text, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp), maxLines = 1)
                                }
                            }
                        }
                        Column(Modifier.weight(1f)) {
                            DickTag("世界卡", fontSize = 12.sp, icon = "public")
                            wsLocalWorlds.forEachIndexed { i, f ->
                                val sel = wsLocalType == "世界卡" && wsLocalIdx == i
                                DickCard(
                                    radius = 8.dp,
                                    tone = if (sel) DickSurfaceTone.Surface2 else DickSurfaceTone.Surface,
                                    outline = if (sel) theme.palette.accent else theme.line,
                                    outlineWidth = if (sel) 2.dp else 1.dp,
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp).clickable {
                                        wsLocalType = "世界卡"; wsLocalIdx = i
                                        wsPreview = Workshop.preview("世界卡", f)
                                    },
                                ) {
                                    Text(f.removeSuffix(".json"), fontSize = 12.sp, color = theme.text, modifier = Modifier.padding(horizontal = 8.dp, vertical = 6.dp), maxLines = 1)
                                }
                            }
                        }
                    }
                    if (wsPreview.isNotBlank()) {
                        // 结构化卡片（CardPreview.kt）：字段清单来自 CardFields（唯一真相
                        // design/card_fields.json），这里**不再**把整份 JSON 原样画出来。
                        DickCard(
                            radius = 10.dp,
                            tone = DickSurfaceTone.Surface,
                            outline = theme.line,
                            modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                        ) {
                            WsCardPreview(
                                text = wsPreview,
                                fileName = WorkshopState.selectedLocalFile(
                                    wsLocalType, wsLocalIdx, wsLocalRoles, wsLocalWorlds) ?: "",
                                modifier = Modifier.padding(10.dp),
                            )
                        }
                    }
                    Row {
                        DickTextButton(
                            label = I18n.t("btn_import_card", "导入"),
                            onClick = {
                                importCardLauncher.launch(arrayOf("image/png", "image/webp", "application/json"))
                            },
                            fontSize = 12.sp, icon = "inbox"
                        )
                        DickTextButton(
                            label = I18n.t("ws_export", "导出"),
                            onClick = {
                                val fname = WorkshopState.selectedLocalFile(wsLocalType, wsLocalIdx, wsLocalRoles, wsLocalWorlds)
                                if (fname != null) { wsExportTarget = fname; wsExportLauncher.launch(fname) }
                            },
                            fontSize = 12.sp, icon = "upload"
                        )
                        DickTextButton(
                            label = I18n.t("ws_delete", "删除"),
                            onClick = {
                                val fname = WorkshopState.selectedLocalFile(wsLocalType, wsLocalIdx, wsLocalRoles, wsLocalWorlds)
                                if (fname != null) {
                                    if (Workshop.deleteLocal(wsLocalType, fname)) {
                                        wsPreview = ""
                                        wsLocalIdx = -1
                                        wsRefreshLocal()
                                        reloadRolesFromDisk()
                                        reloadWorldsFromDisk()
                                        wsSetStatus("已删除", "check_circle")
                                    }
                                }
                            },
                            fontSize = 12.sp, color = theme.danger, icon = "delete"
                        )
                        DickTextButton(label = I18n.t("ws_upload", "上传"), onClick = { wsUploadLocal() }, fontSize = 12.sp, icon = "upload")
                    }
                } else if (wsTabOnline) {
                    if (wsServerInput.isNotBlank()) {
                        DickTag("自动连接：" + wsServerInput,
                            fontSize = 12.sp, iconSize = 13.dp,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp), icon = "satellite_alt")
                    } else {
                        DickLoading("自动连接中...",
                            fontSize = 12.sp, iconSize = 13.dp,
                            modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp), icon = "satellite_alt")
                    }
                    DickField(value = wsKeyInput, onValueChange = { wsKeyInput = it },
                        label = I18n.t("ws_key", "Key（可选）"), singleLine = true)
                    Row {
                        DickTextButton(
                            label = I18n.t("ws_test", "重新检测"),
                            onClick = {
                                Workshop.saveConfig(Workshop.serverUrl, wsKeyInput)
                                wsSetStatus("检测中...")
                                scope.launch(Dispatchers.IO) {
                                    val active = try { Workshop.activeServer() } catch (e: Exception) { "" }
                                    val h = try { Workshop.health() } catch (e: Exception) { null }
                                    val s = try { Workshop.stats() } catch (e: Exception) { null }
                                    scope.launch(Dispatchers.Main) {
                                        if (active.isNotBlank()) wsServerInput = active
                                        if (h != null) {
                                            val auth = h.fields["auth"]?.str() ?: "open"
                                            val dl = (s?.fields?.get("downloads") as? J.Num)?.v?.toInt() ?: 0
                                            val lk = (s?.fields?.get("likes") as? J.Num)?.v?.toInt() ?: 0
                                            // auth=key 的服务器：上传/删除没 Key 就是 401，这里直接说清楚，
                                            // 否则用户只看到" 上传失败"，会以为是网络或服务器坏了。
                                            val needKey = auth == "key" && wsKeyInput.isBlank()
                                            wsSetStatus("已连接（认证:" + auth + " · ↓" + dl + " 赞" + lk + "）" +
                                                if (needKey) " · 上传/删除要先填 Key" else "", "check_circle")
                                        } else wsSetStatus("连接失败", "error")
                                    }
                                }
                            },
                            fontSize = 12.sp, icon = "refresh"
                        )
                        Spacer(Modifier.weight(1f))
                        DickField(value = wsSearchInput, onValueChange = { wsSearchInput = it },
                            label = I18n.t("ws_search", "搜索"), singleLine = true, modifier = Modifier.width(110.dp))
                        DickIconButton(icon = "search", onClick = { wsSearchOnline() })
                    }
                    DickTextButton(label = "全部作品", onClick = { wsLoadOnline() }, fontSize = 12.sp)
                    wsOnlineList.forEachIndexed { i, r ->
                        val t = r.fields["_type"]?.str() ?: "角色卡"
                        val name = r.fields["name"]?.str() ?: "?"
                        val author = r.fields["author"]?.str() ?: "?"
                        val dl = (r.fields["downloads"] as? J.Num)?.v?.toInt() ?: 0
                        val lk = (r.fields["likes"] as? J.Num)?.v?.toInt() ?: 0
                        val tags = (r.fields["tags"] as? J.Arr)?.items?.mapNotNull { it.str() } ?: emptyList()
                        val desc = r.fields["description"]?.str() ?: ""
                        val sel = i == wsOnlineIdx
                        DickCard(
                            radius = 12.dp,
                            tone = if (sel) DickSurfaceTone.Surface2 else DickSurfaceTone.Surface,
                            outline = if (sel) theme.palette.accent else theme.line,
                            outlineWidth = if (sel) 2.dp else 1.dp,
                            modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp).clickable { wsOnlineIdx = i },
                        ) {
                            Column(Modifier.padding(10.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    IconText(name, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                                        modifier = Modifier.weight(1f), iconSize = 16.dp, icon = wsTypeIcon(t))
                                    DickTag("↓" + dl + "  赞" + lk, fontSize = 11.sp, iconSize = 12.dp)
                                }
                                Text(author, fontSize = 11.sp, color = theme.muted)
                                if (tags.isNotEmpty()) Text(tags.joinToString(" · "), fontSize = 10.sp, color = theme.muted)
                                if (desc.isNotBlank()) Text(desc, fontSize = 11.sp, color = theme.text, maxLines = 2)
                            }
                        }
                    }
                    val selR = wsOnlineList.getOrNull(wsOnlineIdx)
                    if (selR != null) {
                        val t = selR.fields["_type"]?.str() ?: "角色卡"
                        val name = selR.fields["name"]?.str() ?: "?"
                        val author = selR.fields["author"]?.str() ?: "?"
                        val dl = (selR.fields["downloads"] as? J.Num)?.v?.toInt() ?: 0
                        val lk = (selR.fields["likes"] as? J.Num)?.v?.toInt() ?: 0
                        val tags = (selR.fields["tags"] as? J.Arr)?.items?.mapNotNull { it.str() } ?: emptyList()
                        val desc = selR.fields["description"]?.str() ?: ""
                        val created = selR.fields["created_at"]?.str() ?: ""
                        val preview = selR.fields["system_prompt_preview"]?.str() ?: ""
                        DickCard(
                            radius = 12.dp,
                            tone = DickSurfaceTone.Surface,
                            outline = theme.line,
                            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                        ) {
                            Column(Modifier.padding(12.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    IconText(name, fontSize = 15.sp, fontWeight = FontWeight.Bold,
                                        modifier = Modifier.weight(1f), iconSize = 17.dp, icon = wsTypeIcon(t))
                                    DickTag("↓" + dl + "  赞" + lk, fontSize = 12.sp, iconSize = 13.dp)
                                }
                                Text("作者：" + author, fontSize = 12.sp, color = theme.muted)
                                if (created.isNotBlank()) Text("上传：" + created.take(10), fontSize = 10.sp, color = theme.muted)
                                if (tags.isNotEmpty()) Text("标签：" + tags.joinToString(" · "), fontSize = 11.sp, color = theme.muted)
                                if (desc.isNotBlank()) Text(desc, fontSize = 13.sp, color = theme.text)
                                if (preview.isNotBlank()) Text("人设：" + preview.take(120), fontSize = 11.sp, color = theme.muted, maxLines = 4)
                            }
                        }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        DickTextButton(label = I18n.t("ws_download", "下载"), onClick = { wsDownloadSelected() }, fontSize = 12.sp, icon = "download")
                        DickTextButton(label = I18n.t("ws_like", "点赞"), onClick = { wsLikeSelected() }, fontSize = 12.sp, icon = "favorite")
                        DickTextButton(label = I18n.t("ws_delete", "删除"), onClick = { wsDeleteSelected() }, fontSize = 12.sp, color = theme.danger, icon = "delete")
                    }
                } else {
                    if (wsPlugins.isEmpty()) {
                        DickEmptyState("插件市场暂无内容（工坊服务器未启动或未上传插件）", icon = "extension")
                    }
                    wsPlugins.forEach { p ->
                        val id = p.fields["id"]?.str() ?: return@forEach
                        val name = p.fields["name"]?.str() ?: "?"
                        val ver = p.fields["version"]?.str() ?: "1.0"
                        val author = p.fields["author"]?.str() ?: "?"
                        val desc = p.fields["description"]?.str() ?: ""
                        val dl = (p.fields["downloads"] as? J.Num)?.v?.toInt() ?: 0
                        val installed = wsLocalPlugins.any {
                            it == name || it == (p.fields["original_name"]?.str()?.removeSuffix(".py"))
                        }
                        DickCard(
                            radius = 10.dp,
                            tone = DickSurfaceTone.Surface,
                            outline = theme.line,
                            modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp),
                        ) {
                            Column(Modifier.padding(8.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    IconText("$name", fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                                        modifier = Modifier.weight(1f), iconSize = 14.dp, icon = "extension")
                                    DickTag("v$ver · $author · ↓$dl", fontSize = 10.sp, iconSize = 11.dp)
                                }
                                if (desc.isNotBlank()) {
                                    Text(desc, fontSize = 11.sp, color = theme.muted, maxLines = 2)
                                }
                                if (installed) {
                                    DickTag("已安装", fontSize = 11.sp, tone = DickTone.Ok, iconSize = 12.dp, icon = "check_circle")
                                } else {
                                    DickTextButton(
                                        label = if (wsInstallingId == id) "安装中..." else "安装",
                                        onClick = { wsInstallPlugin(id) },
                                        enabled = wsInstallingId != id,
                                        fontSize = 12.sp,
                                        icon = if (wsInstallingId == id) "hourglass_empty" else "download",
                                    )
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = { DickTextButton(label = I18n.t("btn_cancel", "取消"), onClick = { showWorkshop = false }) },
    )
    }
}
