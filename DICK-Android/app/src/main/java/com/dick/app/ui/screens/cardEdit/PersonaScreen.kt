package com.dick.app

import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.AppEnv
import com.dick.core.J
import com.dick.core.JsonS
import java.io.File
import kotlinx.coroutines.launch

/**
 * 玩家角色卡编辑（与角色卡同一套结构化字段）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `PersonaDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[PersonaDialog]（在 Dialogs.kt 末尾），转调 [PersonaScreen]。
 */
/** 玩家角色卡<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌编辑（结构化） */
@Composable
fun PersonaScreen(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    val personaFields = deps.personaFields
    val saveConfig = deps.saveConfig
    val userDisplayName = deps.userDisplayName
    val avatarPicker = deps.avatarPicker
    val avatarCache = vm.avatarCache
    var persona by vm.persona
    var avatarTarget by vm.avatarTarget
    var showPersonaEdit by vm.showPersonaEdit
    if (showPersonaEdit) {
    var pf = personaFields()
    var pName by remember { mutableStateOf(pf["name"] ?: "") }
    var pLegacy by remember { mutableStateOf(pf["legacy"] ?: "") }
    var pAppearance by remember { mutableStateOf(pf["appearance"] ?: "") }
    var pPersonality by remember { mutableStateOf(pf["personality"] ?: "") }
    var pBackground by remember { mutableStateOf(pf["background"] ?: "") }
    var pSpeech by remember { mutableStateOf(pf["speech"] ?: "") }
    var pFirstMes by remember { mutableStateOf(pf["first_mes"] ?: "") }
    var pMesExample by remember { mutableStateOf(pf["mes_example"] ?: "") }
    var pNotes by remember { mutableStateOf(pf["notes"] ?: "") }
    val pAdvInit = try {
        (JsonS.parse(persona) as? J.Obj)?.fields?.get("advanced") as? J.Obj
    } catch (_: Exception) {
        null
    }
    val pBattleInit = pAdvInit?.fields?.get("battle") as? J.Obj
    var pBattleEnabled by remember { mutableStateOf(pBattleInit?.fields?.get("enabled")?.bool() == true) }
    var pBattleAttrs by remember {
        mutableStateOf((pBattleInit?.fields?.get("attrs") as? J.Obj)?.fields?.mapNotNull { (k, v) ->
            val a = v as? J.Obj ?: return@mapNotNull null
            listOf(k, a.fields["label"]?.str() ?: k,
                a.fields["initial"]?.int()?.toString() ?: "10",
                a.fields["max"]?.int()?.toString() ?: "").joinToString("|")
        }?.joinToString("\n") ?: "hp|生命|100|100\natk|攻击|10\ndef|防御|5")
    }
    var pBattleMech by remember {
        mutableStateOf((pBattleInit?.fields?.get("mech_attrs") as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { a ->
            val key = a.fields["key"]?.str() ?: return@mapNotNull null
            listOf(key, a.fields["label"]?.str() ?: key,
                a.fields["initial"]?.int()?.toString() ?: "10",
                a.fields["max"]?.int()?.toString() ?: "").joinToString("|")
        }?.joinToString("\n") ?: "")
    }
    var pRegex by remember {
        mutableStateOf((pAdvInit?.fields?.get("regex_rules") as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { x ->
            val id = x.fields["id"]?.str() ?: return@mapNotNull null
            listOf(id, x.fields["name"]?.str() ?: id, x.fields["pattern"]?.str() ?: "",
                x.fields["replace"]?.str() ?: "", x.fields["scope"]?.str() ?: "both").joinToString("|")
        }?.joinToString("\n") ?: "")
    }
    var foldPBattle by remember { mutableStateOf(pBattleEnabled) }
    var foldPRegex by remember { mutableStateOf(pRegex.isNotBlank()) }
    AlertDialog(
        onDismissRequest = { showPersonaEdit = false },
        title = { Text(I18n.t("btn_persona_card", "玩家角色卡")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(value = pName, onValueChange = { pName = it }, label = { Text("名字") }, singleLine = true)
                IconText("📜 完整设定（旧版原文，填了会整体覆盖，可留空）", fontSize = 11.sp, color = theme.muted, modifier = Modifier.padding(top = 6.dp))
                OutlinedTextField(value = pLegacy, onValueChange = { pLegacy = it }, label = { Text("Legacy 原文") }, minLines = 2)
                IconText("🎨 结构化字段（与角色卡同标准）", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 10.dp))
                OutlinedTextField(value = pAppearance, onValueChange = { pAppearance = it }, label = { Text("外貌") }, minLines = 2)
                OutlinedTextField(value = pPersonality, onValueChange = { pPersonality = it }, label = { Text("性格") }, minLines = 2)
                OutlinedTextField(value = pBackground, onValueChange = { pBackground = it }, label = { Text("过去经历") }, minLines = 2)
                OutlinedTextField(value = pSpeech, onValueChange = { pSpeech = it }, label = { Text("说话方式（语气/口癖/句式）") }, minLines = 2)
                OutlinedTextField(value = pFirstMes, onValueChange = { pFirstMes = it }, label = { Text("开场白") }, minLines = 2)
                OutlinedTextField(value = pMesExample, onValueChange = { pMesExample = it }, label = { Text("对话示例") }, minLines = 2)
                OutlinedTextField(value = pNotes, onValueChange = { pNotes = it }, label = { Text("备注") }, minLines = 2)
                FoldHead("⚔️ 玩家战斗属性（可选）", foldPBattle, onToggle = { foldPBattle = !foldPBattle })
                if (foldPBattle) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = pBattleEnabled, onCheckedChange = { pBattleEnabled = it })
                        Text("启用玩家战斗属性（结算用玩家属性；AI 用 [ph:-N] 打你）", fontSize = 12.sp)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedTextField(value = pBattleAttrs, onValueChange = { pBattleAttrs = it }, label = { Text("基础属性（每行 键|名|初值|上限）\n例：hp|生命|100|100") }, minLines = 4, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = pBattleMech, onValueChange = { pBattleMech = it }, label = { Text("机制属性（每行 键|名|初值|上限）\n例：spd|速度|8|100") }, minLines = 4, modifier = Modifier.weight(1f))
                    }
                }
                FoldHead("🔤 玩家专属正则（可选）", foldPRegex, onToggle = { foldPRegex = !foldPRegex })
                if (foldPRegex) {
                    OutlinedTextField(value = pRegex, onValueChange = { pRegex = it }, label = { Text("正则（每行 id|名称|正则|替换|作用域，对玩家输入生效）") }, minLines = 3)
                }
                TextButton(onClick = { avatarTarget = userDisplayName(); avatarPicker.launch("image/*") }) {
                    IconText("🧑 " + I18n.t("btn_avatar_persona", "玩家头像"), fontSize = 12.sp)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val oldName = personaFields()["name"]?.trim() ?: ""
                val newName = pName.trim()
                val o = J.Obj()
                o.fields["name"] = J.Str(newName)
                o.fields["legacy"] = J.Str(pLegacy.trim())
                o.fields["appearance"] = J.Str(pAppearance.trim())
                o.fields["personality"] = J.Str(pPersonality.trim())
                o.fields["background"] = J.Str(pBackground.trim())
                o.fields["speech"] = J.Str(pSpeech.trim())
                o.fields["first_mes"] = J.Str(pFirstMes.trim())
                o.fields["mes_example"] = J.Str(pMesExample.trim())
                o.fields["notes"] = J.Str(pNotes.trim())
                val padv = J.Obj()
                if (pBattleEnabled) {
                    val pb = J.Obj()
                    pb.fields["enabled"] = J.Bool(true)
                    val battrs = J.Obj()
                    pBattleAttrs.split("\n").forEach { line ->
                        val t = line.trim()
                        if (t.isEmpty()) return@forEach
                        val q = t.split("|")
                        if (q.size < 2) return@forEach
                        val key = q[0].trim()
                        if (key.isEmpty()) return@forEach
                        val a = J.Obj()
                        a.fields["label"] = J.Str(q[1].trim().ifEmpty { key })
                        a.fields["initial"] = J.Num((q.getOrNull(2)?.toIntOrNull() ?: 10).toDouble())
                        if (key == "hp" || q.getOrNull(3)?.isNotBlank() == true) {
                            a.fields["max"] = J.Num((q.getOrNull(3)?.toIntOrNull() ?: if (key == "hp") 100 else 999999).toDouble())
                        }
                        battrs.fields[key] = a
                    }
                    if (battrs.fields.isNotEmpty()) pb.fields["attrs"] = battrs
                    val bmech = J.Arr()
                    pBattleMech.split("\n").forEach { line ->
                        val t = line.trim()
                        if (t.isEmpty()) return@forEach
                        val q = t.split("|")
                        if (q.size < 2) return@forEach
                        val key = q[0].trim()
                        if (key.isEmpty()) return@forEach
                        val a = J.Obj()
                        a.fields["key"] = J.Str(key)
                        a.fields["label"] = J.Str(q[1].trim().ifEmpty { key })
                        a.fields["initial"] = J.Num((q.getOrNull(2)?.toIntOrNull() ?: 10).toDouble())
                        a.fields["max"] = J.Num((q.getOrNull(3)?.toIntOrNull() ?: 999999).toDouble())
                        bmech.items.add(a)
                    }
                    if (bmech.items.isNotEmpty()) pb.fields["mech_attrs"] = bmech
                    padv.fields["battle"] = pb
                }
                val prr = J.Arr()
                pRegex.split("\n").forEach { line ->
                    val t = line.trim()
                    if (t.isEmpty()) return@forEach
                    val q = t.split("|")
                    if (q.size < 4) return@forEach
                    val scope = q.getOrNull(4)?.trim()?.takeIf { it in setOf("ai", "user", "both") } ?: "both"
                    val x = J.Obj()
                    x.fields["id"] = J.Str(q[0].trim())
                    x.fields["name"] = J.Str(q[1].trim().ifEmpty { q[0].trim() })
                    x.fields["pattern"] = J.Str(q[2])
                    x.fields["replace"] = J.Str(q.drop(3).joinToString("|"))
                    x.fields["scope"] = J.Str(scope)
                    x.fields["enabled"] = J.Bool(true)
                    prr.items.add(x)
                }
                if (prr.items.isNotEmpty()) padv.fields["regex_rules"] = prr
                if (padv.fields.isNotEmpty()) o.fields["advanced"] = padv
                persona = JsonS.stringify(o, pretty = true)
                saveConfig()
                val effNew = newName.ifBlank { "你" }
                if (oldName != newName && oldName.isNotBlank() && oldName != effNew) {
                    val avDir = File(AppEnv.savesDir(), "avatars")
                    for (from in listOf(oldName, "你")) {
                        for (ext in listOf("png", "jpg", "jpeg", "webp")) {
                            val f = File(avDir, from + "." + ext)
                            if (f.exists()) {
                                val nf = File(avDir, effNew + "." + ext)
                                try {
                                    if (nf.exists()) nf.delete()
                                    f.renameTo(nf)
                                } catch (_: Exception) {
                                }
                                break
                            }
                        }
                    }
                    avatarCache.remove(oldName)
                    avatarCache.remove("你")
                    avatarCache.remove(effNew)
                }
                showPersonaEdit = false
            }) { Text(I18n.t("btn_save", "保存")) }
        },
        dismissButton = { TextButton(onClick = { showPersonaEdit = false }) { Text(I18n.t("btn_cancel", "取消")) } },
    )
    }
}
