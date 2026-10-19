package com.dick.app

import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.AppEnv
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.WorldData
import com.dick.core.WorldEntry
import java.io.File

/**
 * 世界卡编辑（含世界书条目）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `WorldEditDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[WorldEditDialog]（在 Dialogs.kt 末尾），转调 [WorldEditScreen]。
 */
/** 世<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌界卡编辑 */
@Composable
fun WorldEditScreen(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val worlds = vm.worlds
    val worldEntries = vm.worldEntries
    var showWorldEdit by vm.showWorldEdit
    if (showWorldEdit != null) {
        val editing = showWorldEdit!!
        var wName by remember { mutableStateOf(editing) }
        var wDesc by remember { mutableStateOf("") }
        var wRules by remember { mutableStateOf("") }
        val paramsState = remember { mutableStateMapOf<String, String>() }
        val entriesState = remember { mutableStateListOf<WorldEntry>() }
        LaunchedEffect(editing) {
            if (editing.isNotBlank() && wDesc.isEmpty() && entriesState.isEmpty()) {
                try {
                    val wo = JsonS.parse(File(AppEnv.worldsDir(), editing + ".json").readText(Charsets.UTF_8)) as? J.Obj
                    if (wo != null) {
                        wDesc = wo.fields["description"]?.str() ?: ""
                        (wo.fields["params"] as? J.Obj)?.fields?.forEach { (k, v) -> v.str()?.let { paramsState[k] = it } }
                    }
                } catch (_: Exception) {
                }
                worldEntries[editing]?.let { entriesState.addAll(it) }
            }
        }
        DickDialog(
            onDismissRequest = { showWorldEdit = null },
            title = { Text(I18n.t("dlg_world_edit", "编辑世界卡")) },
            text = {
                Column(Modifier.verticalScroll(rememberScrollState())) {
                    OutlinedTextField(value = wName, onValueChange = { wName = it }, label = { Text(I18n.t("lbl_world_name", "名字")) }, singleLine = true)
                    OutlinedTextField(value = wDesc, onValueChange = { wDesc = it }, label = { Text(I18n.t("lbl_world_desc", "背景描述")) }, minLines = 2)
                    OutlinedTextField(value = wRules, onValueChange = { wRules = it }, label = { Text(I18n.t("lbl_world_rules", "规则（每行一条）")) }, minLines = 2)
                    Spacer(Modifier.height(6.dp))
                    Text(I18n.t("wm_params", "世界参数（物理系统等）"), color = theme.muted, fontSize = 13.sp)
                    for ((k, label) in WORLD_PARAM_LABELS) {
                        OutlinedTextField(
                            value = paramsState[k] ?: "",
                            onValueChange = { paramsState[k] = it },
                            label = { Text(label) },
                            singleLine = true,
                        )
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(I18n.t("world_entries", "世界书条目（关键词触发，可空）"), color = theme.muted, fontSize = 13.sp)
                    entriesState.forEachIndexed { idx, e ->
                        Column(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                            Row {
                                Checkbox(checked = e.enabled, onCheckedChange = { entriesState[idx] = e.copy(enabled = it) })
                                Text(I18n.t("entry_enabled", "启用"), Modifier.padding(top = 14.dp), fontSize = 12.sp)
                                Checkbox(checked = e.constant, onCheckedChange = { entriesState[idx] = e.copy(constant = it) })
                                Text(I18n.t("entry_constant", "常驻"), Modifier.padding(top = 14.dp), fontSize = 12.sp)
                                Spacer(Modifier.weight(1f))
                                TextButton(onClick = { entriesState.removeAt(idx) }) {
                                    // 图标按钮：图标名走 icon（文案表里不再有 entry_delete 这个 emoji 键）
                                    IconText("", color = theme.danger, fontSize = 12.sp, iconSize = 13.dp, icon = "close")
                                }
                            }
                            OutlinedTextField(
                                value = e.keywords.joinToString(", "),
                                onValueChange = { v ->
                                    entriesState[idx] = e.copy(keywords = v.split(',').map { it.trim() }.filter { it.isNotEmpty() }.toMutableList())
                                },
                                label = { Text(I18n.t("entry_keywords", "关键词（逗号分隔）")) },
                                singleLine = true,
                            )
                            Row {
                                TextButton(onClick = {
                                    entriesState[idx] = e.copy(match = when (e.match) { "any" -> "all"; "all" -> "regex"; else -> "any" })
                                }) {
                                    Text(
                                        I18n.t("entry_match", "匹配") + "：" + when (e.match) {
                                            "all" -> I18n.t("match_all", "all")
                                            "regex" -> I18n.t("match_regex", "regex")
                                            else -> I18n.t("match_any", "any")
                                        },
                                        fontSize = 12.sp,
                                    )
                                }
                                OutlinedTextField(
                                    value = e.weight.toString(),
                                    onValueChange = { v -> entriesState[idx] = e.copy(weight = v.toIntOrNull() ?: 0) },
                                    label = { Text(I18n.t("entry_weight", "权重")) },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                )
                                OutlinedTextField(
                                    value = e.probability.toString(),
                                    onValueChange = { v -> entriesState[idx] = e.copy(probability = v.toIntOrNull() ?: 100) },
                                    label = { Text(I18n.t("entry_probability", "概率%")) },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                )
                                OutlinedTextField(
                                    value = e.depth.toString(),
                                    onValueChange = { v -> entriesState[idx] = e.copy(depth = (v.toIntOrNull() ?: 1).coerceIn(1, 4)) },
                                    label = { Text(I18n.t("entry_depth", "深度")) },
                                    modifier = Modifier.weight(1f),
                                    singleLine = true,
                                )
                            }
                            OutlinedTextField(
                                value = e.content,
                                onValueChange = { v -> entriesState[idx] = e.copy(content = v) },
                                label = { Text(I18n.t("entry_content", "内容")) },
                                minLines = 2,
                            )
                        }
                    }
                    TextButton(onClick = { entriesState.add(WorldEntry()) }) { Text(I18n.t("btn_add_entry", "＋ 添加条目")) }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val nm = wName.trim()
                    if (nm.isNotBlank() && wDesc.isNotBlank()) {
                        val wd = WorldData(
                            name = nm,
                            description = wDesc.trim(),
                            rules = wRules.split('\n').map { it.trim() }.filter { it.isNotEmpty() }.toMutableList(),
                            entries = entriesState.toMutableList(),
                            params = paramsState.toMutableMap(),
                        )
                        File(AppEnv.worldsDir(), nm + ".json").writeText(JsonS.stringify(wd.toJson(), pretty = true), Charsets.UTF_8)
                        worldEntries[nm] = entriesState.toMutableList()
                        val renderedDesc = renderWorldDesc(wDesc.trim(), paramsState.toMap())
                        val idx = worlds.indexOfFirst { it.first == nm }
                        if (idx >= 0) worlds[idx] = nm to renderedDesc else worlds.add(nm to renderedDesc)
                        if (editing.isNotBlank() && editing != nm) {
                            worlds.removeAll { it.first == editing }
                            worldEntries.remove(editing)
                            try { File(AppEnv.worldsDir(), editing + ".json").delete() } catch (_: Exception) {}
                        }
                        showWorldEdit = null
                    }
                }) { Text(I18n.t("btn_save", "保存")) }
            },
            dismissButton = { TextButton(onClick = { showWorldEdit = null }) { Text(I18n.t("btn_cancel", "取消")) } },
        )
    }
}
