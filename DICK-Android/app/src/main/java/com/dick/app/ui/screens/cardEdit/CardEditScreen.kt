package com.dick.app

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.AppEnv
import com.dick.core.J
import com.dick.core.JsonS
import java.io.File
import kotlinx.coroutines.launch

/**
 * 角色卡编辑（结构化字段 + 机制卡/战斗系统折叠）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `RoleEditDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[RoleEditDialog]（在 Dialogs.kt 末尾），转调 [CardEditScreen]。
 */
/** 角色编辑（新手友好：结构化字段 + 机制卡/战斗系统折叠） */
@Composable
fun CardEditScreen(vm: ChatViewModel, deps: DialogDeps) {
    val context = deps.context
    val theme = deps.theme
    val roles = vm.roles
    var selectedRoles by vm.selectedRoles
    val roleUnlocked = vm.roleUnlocked
    val advancedByRole = vm.advancedByRole
    var roleEditName by vm.roleEditName
    var devMode by deps.devMode
    val reloadMech = deps.reloadMech
    if (roleEditName != null) {
    val editing = roleEditName!!
    var rName by remember { mutableStateOf(editing) }
    var rLegacy by remember { mutableStateOf("") }
    var rAppearance by remember { mutableStateOf("") }
    var rPersonality by remember { mutableStateOf("") }
    var rBackground by remember { mutableStateOf("") }
    var rSpeech by remember { mutableStateOf("") }
    var rFirstMes by remember { mutableStateOf("") }
    var rMesExample by remember { mutableStateOf("") }
    var rNotes by remember { mutableStateOf("") }
    var rUnlocked by remember { mutableStateOf(false) }
    var rGameName by remember { mutableStateOf("") }
    var rGameRules by remember { mutableStateOf("") }
    var rGameState by remember { mutableStateOf("") }
    var rExtraPrompt by remember { mutableStateOf("") }
    var rCardFace by remember { mutableStateOf("") }
    var rCardFacePrev by remember { mutableStateOf(false) }
    val cardFaceImpLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let { u ->
            try {
                val bytes = context.contentResolver.openInputStream(u)?.use { it.readBytes() }
                if (bytes != null) rCardFace = String(bytes, Charsets.UTF_8)
            } catch (_: Exception) {}
        }
    }
    var rDevNotes by remember { mutableStateOf("") }
    var rCardQr by remember { mutableStateOf("") }
    var rRegex by remember { mutableStateOf("") }
    var rMechAff by remember { mutableStateOf(false) }
    var rMechAffInit by remember { mutableStateOf("50") }
    var rMechAffMax by remember { mutableStateOf("100") }
    var rMechAffCrit by remember { mutableStateOf("0.001") }
    var rMechSt by remember { mutableStateOf("") }
    var rMechEv by remember { mutableStateOf("") }
    var rEndings by remember { mutableStateOf("") }
    var foldEndings by remember { mutableStateOf(false) }
    var rBattleEnabled by remember { mutableStateOf(false) }
    var rBattleAttrs by remember { mutableStateOf("hp|生命|100|100\natk|攻击|10\ndef|防御|5") }
    var rBattleMech by remember { mutableStateOf("") }
    var rBattleFormulas by remember { mutableStateOf("damage=max(1, player_atk*2-def)\ncrit_chance=0.1\ncrit_mult=2") }
    var rBattleMoves by remember { mutableStateOf("") }
    var rBattleBuffs by remember { mutableStateOf("") }
    var foldMech by remember { mutableStateOf(false) }
    var foldSt by remember { mutableStateOf(false) }
    var foldBattle by remember { mutableStateOf(false) }
    var foldCardFace by remember { mutableStateOf(false) }
    LaunchedEffect(editing) {
        if (editing.isNotBlank() && rLegacy.isEmpty() && rPersonality.isEmpty() && rAppearance.isEmpty()) {
            try {
                val o = JsonS.parse(File(AppEnv.savesDir(), editing + ".json").readText(Charsets.UTF_8)) as? J.Obj
                if (o != null) {
                    rLegacy = o.fields["legacy"]?.str() ?: ""
                    rAppearance = o.fields["appearance"]?.str() ?: ""
                    rPersonality = o.fields["personality"]?.str() ?: ""
                    rBackground = o.fields["background"]?.str() ?: ""
                    rSpeech = o.fields["speech"]?.str() ?: ""
                    rFirstMes = o.fields["first_mes"]?.str() ?: ""
                    rMesExample = o.fields["mes_example"]?.str() ?: ""
                    rNotes = o.fields["notes"]?.str() ?: ""
                    rUnlocked = (o.fields["unlocked"] as? J.Bool)?.v ?: false
                    val adv = o.fields["advanced"] as? J.Obj
                    val game = adv?.fields?.get("game") as? J.Obj
                    rGameName = game?.fields?.get("name")?.str() ?: ""
                    rGameRules = game?.fields?.get("rules")?.str() ?: ""
                    rGameState = game?.fields?.get("state")?.str() ?: ""
                    rExtraPrompt = adv?.fields?.get("extra_prompt")?.str() ?: ""
                    rCardFace = adv?.fields?.get("card_face")?.str() ?: ""
                    rDevNotes = adv?.fields?.get("dev_notes")?.str() ?: ""
                    rCardQr = (adv?.fields?.get("card_quick_replies") as? J.Arr)
                        ?.items?.mapNotNull { q ->
                            val qo = q as? J.Obj ?: return@mapNotNull null
                            val l = qo.fields["label"]?.str() ?: return@mapNotNull null
                            l + "|" + (qo.fields["text"]?.str() ?: "")
                        }?.joinToString("\n") ?: ""
                    rRegex = (adv?.fields?.get("regex_rules") as? J.Arr)
                        ?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { x ->
                            val id = x.fields["id"]?.str() ?: return@mapNotNull null
                            listOf(id, x.fields["name"]?.str() ?: id,
                                x.fields["pattern"]?.str() ?: "",
                                x.fields["replace"]?.str() ?: "",
                                x.fields["scope"]?.str() ?: "both").joinToString("|")
                        }?.joinToString("\n") ?: ""
                    val mech = adv?.fields?.get("mechanics") as? J.Obj
                    val maff = mech?.fields?.get("affection") as? J.Obj
                    rMechAff = maff?.fields?.get("enabled")?.bool() == true
                    rMechAffInit = maff?.fields?.get("initial")?.int()?.toString() ?: "50"
                    rMechAffMax = maff?.fields?.get("max")?.int()?.toString() ?: "100"
                    rMechAffCrit = ((maff?.fields?.get("crit") as? J.Num)?.v ?: 0.001).toString()
                    rMechSt = ((mech?.fields?.get("status") as? J.Obj)?.fields?.get("fields") as? J.Arr)
                        ?.items?.mapNotNull { f ->
                            val fo = f as? J.Obj ?: return@mapNotNull null
                            val key = fo.fields["key"]?.str() ?: return@mapNotNull null
                            val name = fo.fields["name"]?.str() ?: key
                            val type = fo.fields["type"]?.str() ?: "enum"
                            val init = fo.fields["initial"]?.str() ?: (fo.fields["initial"]?.int()?.toString() ?: "")
                            val extra = if (type == "int") {
                                (fo.fields["min"]?.int() ?: 0).toString() + "-" + (fo.fields["max"]?.int() ?: 100)
                            } else {
                                (fo.fields["options"] as? J.Arr)?.items?.mapNotNull { it.str() }?.joinToString(",") ?: ""
                            }
                            listOf(key, name, type, init, extra).joinToString("|")
                        }?.joinToString("\n") ?: ""
                    // 事件回填：支持可选的扩展列<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌（好感加成|可重复|冷却）。
                    // 老卡只有 5 列；once/cooldown/aff 若在扩展列里没有，就从
                    // mechanics.ev_ext 这个 sidecar 里取 —— PC 端编辑器写的就是它。
                    // 不读 sidecar 的话，在手机上编辑一次保存就会把它们全清掉。
                    val evExt = mech?.fields?.get("ev_ext") as? J.Obj
                    rMechEv = (mech?.fields?.get("events") as? J.Arr)
                        ?.items?.mapNotNull { e ->
                            val eo = e as? J.Obj ?: return@mapNotNull null
                            val id = eo.fields["id"]?.str() ?: return@mapNotNull null
                            val name = eo.fields["name"]?.str() ?: ""
                            val affGe = eo.fields["aff_ge"]?.int()?.toString() ?: ""
                            val kws = (eo.fields["keywords"] as? J.Arr)?.items?.mapNotNull { it.str() }?.joinToString(",") ?: ""
                            val prompt = eo.fields["prompt"]?.str() ?: ""
                            val side = evExt?.fields?.get(id) as? J.Obj
                            val affBonus = (eo.fields["aff"]?.int()
                                ?: side?.fields?.get("aff")?.int())?.toString() ?: ""
                            val repeat = if ((eo.fields["once"]?.bool() == false)
                                || (side?.fields?.get("once")?.bool() == false)) "可重复" else ""
                            val cd = (eo.fields["cooldown"]?.int()
                                ?: side?.fields?.get("cooldown")?.int())?.toString() ?: ""
                            listOf(id, name, affGe, kws, prompt, affBonus, repeat, cd).joinToString("|")
                        }?.joinToString("\n") ?: ""
                    rEndings = endingsToText(mech?.fields?.get("endings") as? J.Arr)
                    foldEndings = rEndings.isNotBlank()
                    val battle = adv?.fields?.get("battle") as? J.Obj
                    rBattleEnabled = battle?.fields?.get("enabled")?.bool() == true
                    if (battle != null) {
                        val battrs = battle.fields["attrs"] as? J.Obj
                        rBattleAttrs = battrs?.fields?.mapNotNull { (k, v) ->
                            val a = v as? J.Obj ?: return@mapNotNull null
                            listOf(k, a.fields["label"]?.str() ?: k,
                                a.fields["initial"]?.int()?.toString() ?: "10",
                                a.fields["max"]?.int()?.toString() ?: "").joinToString("|")
                        }?.joinToString("\n") ?: rBattleAttrs
                        rBattleMech = (battle.fields["mech_attrs"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { a ->
                            val key = a.fields["key"]?.str() ?: return@mapNotNull null
                            listOf(key, a.fields["label"]?.str() ?: key,
                                a.fields["initial"]?.int()?.toString() ?: "10",
                                a.fields["max"]?.int()?.toString() ?: "").joinToString("|")
                        }?.joinToString("\n") ?: ""
                        rBattleFormulas = (battle.fields["formulas"] as? J.Obj)?.fields
                            ?.map { (k, v) -> "$k=${v.str() ?: ""}" }?.joinToString("\n") ?: rBattleFormulas
                        rBattleMoves = (battle.fields["moves"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { m ->
                            val id = m.fields["id"]?.str() ?: return@mapNotNull null
                            val cost = (m.fields["cost"] as? J.Obj)?.fields?.map { (k, v) -> "$k:${v.int()}" }?.joinToString(",") ?: ""
                            val bf = (m.fields["buffs"] as? J.Arr)?.items?.firstOrNull() as? J.Obj
                            val bfTxt = bf?.let { "${it.fields["id"]?.str() ?: ""}:${it.fields["turns"]?.int() ?: 3}" } ?: ""
                            listOf(id, m.fields["name"]?.str() ?: id,
                                m.fields["formula"]?.str() ?: "", cost, bfTxt,
                                m.fields["desc"]?.str() ?: "").joinToString("|")
                        }?.joinToString("\n") ?: ""
                        rBattleBuffs = (battle.fields["buffs"] as? J.Arr)?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { b ->
                            val id = b.fields["id"]?.str() ?: return@mapNotNull null
                            val at = (b.fields["attrs"] as? J.Obj)?.fields?.map { (k, v) -> "$k:${v.int()}" }?.joinToString(",") ?: ""
                            listOf(id, b.fields["name"]?.str() ?: id,
                                b.fields["turns"]?.int()?.toString() ?: "3", at,
                                b.fields["desc"]?.str() ?: "").joinToString("|")
                        }?.joinToString("\n") ?: ""
                    }
                    foldMech = rMechAff || rMechEv.isNotBlank()
                    foldSt = rMechSt.isNotBlank()
                    foldBattle = rBattleEnabled
                    if (rLegacy.isEmpty() && rPersonality.isEmpty() && rAppearance.isEmpty()) {
                        rLegacy = o.fields["system_prompt"]?.str() ?: ""
                    }
                }
            } catch (_: Exception) {
            }
        }
    }
    AlertDialog(
        onDismissRequest = { roleEditName = null },
        title = { Text(if (editing.isBlank()) I18n.t("btn_new_role", "新建角色") else "编辑角色：" + editing) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                OutlinedTextField(value = rName, onValueChange = { rName = it }, label = { Text(I18n.t("lbl_name", "名字")) }, singleLine = true, enabled = editing.isBlank())
                IconText("📜 完整设定（旧版原文，填了会整体覆盖，可留空）", fontSize = 11.sp, color = theme.muted, modifier = Modifier.padding(top = 6.dp))
                OutlinedTextField(value = rLegacy, onValueChange = { rLegacy = it }, label = { Text("Legacy 原文") }, minLines = 2)
                IconText("🎨 结构化字段（精细设定）", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 10.dp))
                OutlinedTextField(value = rAppearance, onValueChange = { rAppearance = it }, label = { Text("外貌") }, minLines = 2)
                OutlinedTextField(value = rPersonality, onValueChange = { rPersonality = it }, label = { Text("性格") }, minLines = 2)
                OutlinedTextField(value = rBackground, onValueChange = { rBackground = it }, label = { Text("过去经历") }, minLines = 2)
                OutlinedTextField(value = rSpeech, onValueChange = { rSpeech = it }, label = { Text("说话方式（语气/口癖/句式）") }, minLines = 2)
                OutlinedTextField(value = rFirstMes, onValueChange = { rFirstMes = it }, label = { Text("开场白") }, minLines = 2)
                OutlinedTextField(value = rMesExample, onValueChange = { rMesExample = it }, label = { Text("对话示例") }, minLines = 2)
                OutlinedTextField(value = rNotes, onValueChange = { rNotes = it }, label = { Text("备注") }, minLines = 2)
                Row {
                    Checkbox(checked = rUnlocked, onCheckedChange = { rUnlocked = it })
                    IconText("🔥 启用破甲模式（无限制对话）", Modifier.padding(top = 14.dp), fontSize = 12.sp)
                }
                FoldHead("🎛️ 机制卡（好感度 / 事件）", foldMech, onToggle = { foldMech = !foldMech })
                if (foldMech) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(bottom = 4.dp)) {
                        TextButton(onClick = {
                            rMechAff = true; rMechAffInit = "50"; rMechAffMax = "100"; rMechAffCrit = "0.001"
                            rMechSt = "mood|心情|enum|平静|平静,开心,害羞,生气,委屈\nenergy|精力|int|100|0-100"
                            rMechEv = "confess|告白|80|告白,喜欢|她鼓起勇气向你告白，请演出这一重要时刻"
                            foldMech = true; foldSt = true
                        }) { IconText("💘 恋爱日常", fontSize = 12.sp, iconSize = 13.dp) }
                        TextButton(onClick = {
                            rBattleEnabled = true
                            rBattleAttrs = "hp|生命|100|100\natk|攻击|10\ndef|防御|5"
                            rBattleMech = "spd|速度|8|100\nmp|灵力|20|50"
                            rBattleFormulas = "damage=max(1, player_atk*2-def)\ncrit_chance=0.1\ncrit_mult=2"
                            rBattleMoves = "fire|火球术|player_atk*3-def|mp:5||投掷火球\nstrike|平砍|player_atk-def|\nheal|治愈|20||regen:2|恢复体力"
                            rBattleBuffs = "regen|再生|2|hp:5|每回合恢复5生命\npoison|中毒|3|hp:-5|每回合损失5生命"
                            foldBattle = true
                        }) { IconText("⚔️ 战斗冒险", fontSize = 12.sp, iconSize = 13.dp) }
                        TextButton(onClick = {
                            // 模板里带一个"可重复 + 好感加成"的例子，作者照着抄就会用
                            rMechEv = "meet|初遇|0|你好,初次见面|第一次相遇，自然演出|5\nstorm|风暴夜|30|暴风雨,打雷|暴风雨夜，她害怕地靠近你|10\nconfess|告白|80|告白,喜欢|她鼓起勇气向你告白|20\ndaily|日常闲聊|||来一段轻松的日常||可重复|3"
                            foldMech = true
                        }) { IconText("🎬 事件剧本", fontSize = 12.sp, iconSize = 13.dp) }
                        TextButton(onClick = {
                            rMechAff = false; rMechSt = ""; rMechEv = ""
                            rBattleEnabled = false; rBattleAttrs = ""; rBattleMech = ""
                            rBattleFormulas = ""; rBattleMoves = ""; rBattleBuffs = ""
                        }) { IconText("🗑️ 清空", fontSize = 12.sp, iconSize = 13.dp) }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = rMechAff, onCheckedChange = { rMechAff = it })
                        IconText("❤ 启用好感度（AI 每轮用 [aff:+N] 标注变化）", fontSize = 12.sp, iconSize = 13.dp)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedTextField(value = rMechAffInit, onValueChange = { rMechAffInit = it }, label = { Text("初始值") }, singleLine = true, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = rMechAffMax, onValueChange = { rMechAffMax = it }, label = { Text("上限") }, singleLine = true, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = rMechAffCrit, onValueChange = { rMechAffCrit = it }, label = { Text("暴击概率") }, singleLine = true, modifier = Modifier.weight(1f))
                    }
                    OutlinedTextField(value = rMechEv, onValueChange = { rMechEv = it }, label = { Text("事件（每行 ID|名称|好感≥|关键词,逗号|触发提示|好感加成|可重复|冷却）") }, minLines = 3)
                }
                FoldHead("📊 状态字段", foldSt, onToggle = { foldSt = !foldSt })
                if (foldSt) {
                    OutlinedTextField(value = rMechSt, onValueChange = { rMechSt = it }, label = { Text("状态字段（每行 键|显示名|类型|初始值|范围或选项）\n例：mood|心情|enum|平静|平静,开心,生气") }, minLines = 3)
                }
                FoldHead("⚔️ 战斗系统（可选）", foldBattle, onToggle = { foldBattle = !foldBattle })
                if (foldBattle) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = rBattleEnabled, onCheckedChange = { rBattleEnabled = it })
                        Text("启用战斗（出招结算 / 伤害公式 / buff）", fontSize = 12.sp)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedTextField(value = rBattleAttrs, onValueChange = { rBattleAttrs = it }, label = { Text("基础属性（每行 键|名|初值|上限）\n例：hp|生命|100|100") }, minLines = 4, modifier = Modifier.weight(1f))
                        OutlinedTextField(value = rBattleMech, onValueChange = { rBattleMech = it }, label = { Text("机制属性·第四属性（每行 键|名|初值|上限）\n例：spd|速度|8|100") }, minLines = 4, modifier = Modifier.weight(1f))
                    }
                    OutlinedTextField(value = rBattleFormulas, onValueChange = { rBattleFormulas = it }, label = { Text("伤害公式（每行 名称=表达式，变量用属性键）\n例：damage=max(1, player_atk*2-def)") }, minLines = 3)
                    OutlinedTextField(value = rBattleMoves, onValueChange = { rBattleMoves = it }, label = { Text("招式（每行 ID|名称|公式|消耗键:值|效果:id:回合|描述）") }, minLines = 3)
                    OutlinedTextField(value = rBattleBuffs, onValueChange = { rBattleBuffs = it }, label = { Text("状态效果 buff（每行 ID|名称|回合|效果键:值|描述）") }, minLines = 3)
                }
                FoldHead("🏁 结局预设（达成事件链）", foldEndings, onToggle = { foldEndings = !foldEndings })
                if (foldEndings) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(bottom = 2.dp)) {
                        TextButton(onClick = {
                            rEndings = "good|告白成功|初见,约会,告白|90||她终于说出了那句喜欢\nbad|形同陌路|争吵,决裂|20||你们最终还是走散了\nhidden|雨夜告白|初见,雨夜,告白|1|藏|只有走完整条线才会亮起的结局……"
                        }) { IconText("💘 恋爱线", fontSize = 12.sp, iconSize = 13.dp) }
                        TextButton(onClick = {
                            rEndings = "bad|平淡收场|疏远,淡忘|30||日子照常，只是再也没了心动"
                        }) { IconText("🌧 平淡/坏", fontSize = 12.sp, iconSize = 13.dp) }
                        TextButton(onClick = {
                            rEndings = "hidden|雨夜告白|初见,雨夜,告白|1|藏|只有走完整条线才会亮起的隐藏结局……\n" +
                                "hidden|真相大白|秘密,线索,摊牌|1|藏|你终于问出了那句藏在心底很久的话。\n" +
                                "hidden|时间线|重来,循环,抉择|1|藏|这一次，你没有选择离开。\n" +
                                "hidden|幻梦|沉睡,迷梦,醒来|1|藏|你睁开眼，分不清刚才是不是一场梦。\n" +
                                "hidden|失控|占有,出格,失控|1|藏|她笑着看着你，眼里却没了光。"
                        }) { IconText("🎁 隐藏结局", fontSize = 12.sp, iconSize = 13.dp) }
                        TextButton(onClick = {
                            rEndings = "ghost|幻灭|误会,离开|10||你回头时，她已不在原处。"
                        }) { IconText("👻 幻灭", fontSize = 12.sp, iconSize = 13.dp) }
                    }
                    OutlinedTextField(value = rEndings, onValueChange = { rEndings = it }, label = { Text("结局（每行 id|结局名|事件链,逗号|好感≥|隐藏|描述）\n例：good|告白成功|初见,约会,告白|90||她终于说出了那句喜欢") }, minLines = 3)
                    Text("达成条件：按序触发全部事件链(id)即解锁结局；可与好感/隐藏条件叠加。", fontSize = 11.sp, color = theme.muted)
                }
                if (devMode) {
                    IconText("⚙️ 高级设置（开发者模式）", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 10.dp))
                    OutlinedTextField(value = rGameName, onValueChange = { rGameName = it }, label = { Text("内置游戏名") }, singleLine = true)
                    OutlinedTextField(value = rGameRules, onValueChange = { rGameRules = it }, label = { Text("游戏规则（注入系统提示）") }, minLines = 3)
                    OutlinedTextField(value = rGameState, onValueChange = { rGameState = it }, label = { Text("初始状态（注入）") }, minLines = 2)
                    OutlinedTextField(value = rExtraPrompt, onValueChange = { rExtraPrompt = it }, label = { Text("额外系统提示") }, minLines = 2)
                    FoldHead("🎴 卡面（HTML，可选）", foldCardFace, onToggle = { foldCardFace = !foldCardFace })
                    if (foldCardFace) {
                        OutlinedTextField(value = rCardFace, onValueChange = { rCardFace = it },
                            label = { Text("卡面 HTML（导入或自写；聊天顶栏 🎴 查看；非强制）") }, minLines = 4)
                        Row {
                            TextButton(onClick = { cardFaceImpLauncher.launch(arrayOf("text/html", "text/plain", "*/*")) }) { IconText("📥 导入HTML文件", fontSize = 12.sp) }
                            TextButton(onClick = { rCardFacePrev = true }) { IconText("👁 预览", fontSize = 12.sp) }
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = { rCardFace = "" }) { IconText("🧹 清空", fontSize = 12.sp) }
                        }
                    }
                    OutlinedTextField(value = rCardQr, onValueChange = { rCardQr = it }, label = { Text("卡片快捷回复（每行 按钮名|内容）") }, minLines = 3)
                    OutlinedTextField(value = rRegex, onValueChange = { rRegex = it }, label = { IconText("🔤 角色专属正则（每行 id|名称|正则|替换|作用域，叠加全局）", iconSize = 14.dp) }, minLines = 3)
                    OutlinedTextField(value = rDevNotes, onValueChange = { rDevNotes = it }, label = { Text("开发者备注（不注入）") }, minLines = 2)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val nm = rName.trim()
                val fields = mapOf(
                    "appearance" to rAppearance.trim(), "personality" to rPersonality.trim(),
                    "background" to rBackground.trim(), "speech" to rSpeech.trim(),
                    "first_mes" to rFirstMes.trim(), "mes_example" to rMesExample.trim(),
                    "notes" to rNotes.trim(),
                )
                val prompt = assembleRolePrompt(nm, fields, rLegacy.trim())
                if (nm.isNotBlank() && prompt.isNotBlank()) {
                    try {
                        val f = File(AppEnv.savesDir(), nm + ".json")
                        val o = if (f.exists()) (JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj) ?: J.Obj() else J.Obj()
                        o.fields["name"] = J.Str(nm)
                        o.fields["system_prompt"] = J.Str(prompt)
                        o.fields["legacy"] = J.Str(rLegacy.trim())
                        o.fields["unlocked"] = J.Bool(rUnlocked)
                        roleUnlocked[nm] = rUnlocked
                        val advDirty = devMode && (rGameRules.isNotBlank() || rGameName.isNotBlank() ||
                                rExtraPrompt.isNotBlank() || rDevNotes.isNotBlank() || rCardQr.isNotBlank())
                        val mechDirty = rMechAff || rMechSt.isNotBlank() || rMechEv.isNotBlank() || rEndings.isNotBlank()
                        val battleDirty = rBattleEnabled
                        if (advDirty || mechDirty || battleDirty) {
                            val orig = o.fields["advanced"] as? J.Obj
                            val adv = J.Obj()
                            orig?.fields?.forEach { (k, v) -> adv.fields[k] = v }
                            if (devMode) {
                                if (rGameRules.isNotBlank() || rGameName.isNotBlank()) {
                                    val g = J.Obj()
                                    g.fields["name"] = J.Str(rGameName.trim())
                                    g.fields["rules"] = J.Str(rGameRules.trim())
                                    g.fields["state"] = J.Str(rGameState.trim())
                                    adv.fields["game"] = g
                                } else {
                                    adv.fields.remove("game")
                                }
                                adv.fields["extra_prompt"] = J.Str(rExtraPrompt.trim())
                                if (rCardFace.isNotBlank()) adv.fields["card_face"] = J.Str(rCardFace.trim())
                                else adv.fields.remove("card_face")
                                adv.fields["dev_notes"] = J.Str(rDevNotes.trim())
                                val qrs = J.Arr()
                                rCardQr.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val i = t.indexOf('|')
                                    if (i > 0) {
                                        val qo = J.Obj()
                                        qo.fields["label"] = J.Str(t.substring(0, i).trim())
                                        qo.fields["text"] = J.Str(t.substring(i + 1).trim())
                                        qrs.items.add(qo)
                                    }
                                }
                                adv.fields["card_quick_replies"] = qrs
                                val rrArr = J.Arr()
                                rRegex.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 4) return@forEach
                                    val scope = p.getOrNull(4)?.trim()?.takeIf { it in setOf("ai", "user", "both") } ?: "both"
                                    val o = J.Obj()
                                    o.fields["id"] = J.Str(p[0].trim())
                                    o.fields["name"] = J.Str(p[1].trim().ifEmpty { p[0].trim() })
                                    o.fields["pattern"] = J.Str(p[2])
                                    o.fields["replace"] = J.Str(p.drop(3).joinToString("|"))
                                    o.fields["scope"] = J.Str(scope)
                                    o.fields["enabled"] = J.Bool(true)
                                    rrArr.items.add(o)
                                }
                                if (rrArr.items.isNotEmpty()) adv.fields["regex_rules"] = rrArr
                            }
                            if (mechDirty) {
                                val mechObj = J.Obj()
                                if (rMechAff) {
                                    val a = J.Obj()
                                    a.fields["enabled"] = J.Bool(true)
                                    val affInit = (rMechAffInit.toIntOrNull() ?: 50).coerceIn(0, 99999)
                                    val affMax = (rMechAffMax.toIntOrNull() ?: 100).coerceIn(1, 99999)
                                    a.fields["initial"] = J.Num(affInit.coerceAtMost(affMax).toDouble())
                                    a.fields["min"] = J.Num(0.0)
                                    a.fields["max"] = J.Num(affMax.toDouble())
                                    a.fields["crit"] = J.Num((rMechAffCrit.toDoubleOrNull() ?: 0.001).coerceIn(0.0, 1.0))
                                    mechObj.fields["affection"] = a
                                }
                                val stFields = J.Arr()
                                rMechSt.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 3) return@forEach
                                    val fo = J.Obj()
                                    fo.fields["key"] = J.Str(p[0].trim())
                                    fo.fields["name"] = J.Str(p[1].trim().ifEmpty { p[0].trim() })
                                    val type = if (p[2].trim() == "int") "int" else "enum"
                                    fo.fields["type"] = J.Str(type)
                                    val initRaw = p.getOrNull(3)?.trim() ?: ""
                                    if (type == "int") {
                                        val mm = Regex("^(\\d+)\\s*-\\s*(\\d+)$").find(p.getOrNull(4)?.trim() ?: "")
                                        val mn = mm?.groupValues?.get(1)?.toIntOrNull() ?: 0
                                        val mx = mm?.groupValues?.get(2)?.toIntOrNull() ?: 100
                                        fo.fields["min"] = J.Num(mn.toDouble())
                                        fo.fields["max"] = J.Num(mx.toDouble())
                                        fo.fields["initial"] = J.Num((initRaw.toIntOrNull() ?: mn).coerceIn(mn, mx).toDouble())
                                    } else {
                                        val opts = J.Arr()
                                        (p.getOrNull(4) ?: "").split(",").map { it.trim() }
                                            .filter { it.isNotEmpty() }.forEach { opts.items.add(J.Str(it)) }
                                        fo.fields["options"] = opts
                                        fo.fields["initial"] = J.Str(initRaw.ifEmpty { (opts.items.firstOrNull() as? J.Str)?.v ?: "" })
                                    }
                                    stFields.items.add(fo)
                                }
                                if (stFields.items.isNotEmpty()) {
                                    val s = J.Obj()
                                    s.fields["enabled"] = J.Bool(true)
                                    s.fields["fields"] = stFields
                                    mechObj.fields["status"] = s
                                }
                                val evArr = J.Arr()
                                val evExtWrite = J.Obj()
                                rMechEv.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 5) return@forEach
                                    val eo = J.Obj()
                                    val eid = p[0].trim()
                                    eo.fields["id"] = J.Str(eid)
                                    eo.fields["name"] = J.Str(p[1].trim())
                                    p[2].trim().toIntOrNull()?.let { eo.fields["aff_ge"] = J.Num(it.toDouble()) }
                                    val kws = J.Arr()
                                    p[3].split(",").map { it.trim() }.filter { it.isNotEmpty() }.forEach { kws.items.add(J.Str(it)) }
                                    if (kws.items.isNotEmpty()) eo.fields["keywords"] = kws
                                    eo.fields["prompt"] = J.Str(p.drop(4).joinToString("|").trim())
                                    // 扩展列（可选）：好感加成 | 可重复 | 冷却
                                    val affBonus = p.getOrNull(5)?.trim()?.toIntOrNull()
                                    val repeat = p.getOrNull(6)?.trim() == "可重复"
                                    val cd = p.getOrNull(7)?.trim()?.toIntOrNull() ?: 0
                                    eo.fields["once"] = J.Bool(!repeat)
                                    if (affBonus != null && affBonus != 0) eo.fields["aff"] = J.Num(affBonus.toDouble())
                                    if (repeat && cd > 0) eo.fields["cooldown"] = J.Num(cd.toDouble())
                                    evArr.items.add(eo)
                                    // sidecar：管道格式放不下的属性另存一份，
                                    // PC 端编辑器读的就是它（不清掉才算不丢数据）
                                    val ext = J.Obj()
                                    if (repeat) ext.fields["once"] = J.Bool(false)
                                    if (repeat && cd > 0) ext.fields["cooldown"] = J.Num(cd.toDouble())
                                    if (affBonus != null && affBonus != 0) ext.fields["aff"] = J.Num(affBonus.toDouble())
                                    if (ext.fields.isNotEmpty()) evExtWrite.fields[eid] = ext
                                }
                                if (evArr.items.isNotEmpty()) {
                                    mechObj.fields["events"] = evArr
                                    if (evExtWrite.fields.isNotEmpty()) mechObj.fields["ev_ext"] = evExtWrite
                                }
                                val endingsArr = parseEndings(rEndings)
                                if (endingsArr.items.isNotEmpty()) mechObj.fields["endings"] = endingsArr
                                if (mechObj.fields.isNotEmpty()) adv.fields["mechanics"] = mechObj
                            }
                            if (battleDirty) {
                                val battle = J.Obj()
                                battle.fields["enabled"] = J.Bool(true)
                                val battrs = J.Obj()
                                rBattleAttrs.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 2) return@forEach
                                    val key = p[0].trim()
                                    if (key.isEmpty()) return@forEach
                                    val a = J.Obj()
                                    a.fields["label"] = J.Str(p[1].trim().ifEmpty { key })
                                    a.fields["initial"] = J.Num((p.getOrNull(2)?.toIntOrNull() ?: 10).toDouble())
                                    if (key == "hp" || p.getOrNull(3)?.isNotBlank() == true) {
                                        a.fields["max"] = J.Num((p.getOrNull(3)?.toIntOrNull() ?: if (key == "hp") 100 else 999999).toDouble())
                                    }
                                    battrs.fields[key] = a
                                }
                                if (battrs.fields.isNotEmpty()) battle.fields["attrs"] = battrs
                                val bmech = J.Arr()
                                rBattleMech.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 2) return@forEach
                                    val key = p[0].trim()
                                    if (key.isEmpty()) return@forEach
                                    val a = J.Obj()
                                    a.fields["key"] = J.Str(key)
                                    a.fields["label"] = J.Str(p[1].trim().ifEmpty { key })
                                    a.fields["initial"] = J.Num((p.getOrNull(2)?.toIntOrNull() ?: 10).toDouble())
                                    a.fields["max"] = J.Num((p.getOrNull(3)?.toIntOrNull() ?: 999999).toDouble())
                                    bmech.items.add(a)
                                }
                                if (bmech.items.isNotEmpty()) battle.fields["mech_attrs"] = bmech
                                val bform = J.Obj()
                                rBattleFormulas.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val i = t.indexOf('=')
                                    if (i <= 0) return@forEach
                                    val name = t.substring(0, i).trim()
                                    val expr = t.substring(i + 1).trim()
                                    if (name.isNotEmpty() && expr.isNotEmpty()) bform.fields[name] = J.Str(expr)
                                }
                                if (bform.fields.isNotEmpty()) battle.fields["formulas"] = bform
                                val bmoves = J.Arr()
                                rBattleMoves.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 2) return@forEach
                                    val id = p[0].trim()
                                    if (id.isEmpty()) return@forEach
                                    val m = J.Obj()
                                    m.fields["id"] = J.Str(id)
                                    m.fields["name"] = J.Str(p[1].trim().ifEmpty { id })
                                    p.getOrNull(2)?.trim()?.takeIf { it.isNotEmpty() }?.let { m.fields["formula"] = J.Str(it) }
                                    p.getOrNull(3)?.trim()?.takeIf { it.isNotEmpty() }?.let { costStr ->
                                        val cost = J.Obj()
                                        costStr.split(",").forEach { kv ->
                                            val sp = kv.split(":")
                                            if (sp.size == 2 && sp[0].isNotBlank() && sp[1].toIntOrNull() != null) {
                                                cost.fields[sp[0].trim()] = J.Num((sp[1].toIntOrNull() ?: 0).toDouble())
                                            }
                                        }
                                        if (cost.fields.isNotEmpty()) m.fields["cost"] = cost
                                    }
                                    p.getOrNull(4)?.trim()?.takeIf { it.isNotEmpty() }?.let { bfStr ->
                                        val sp = bfStr.split(":")
                                        if (sp.size == 2 && sp[0].isNotBlank()) {
                                            val bf = J.Obj()
                                            bf.fields["id"] = J.Str(sp[0].trim())
                                            bf.fields["turns"] = J.Num((sp[1].toIntOrNull() ?: 3).toDouble())
                                            val arr = J.Arr()
                                            arr.items.add(bf)
                                            m.fields["buffs"] = arr
                                        }
                                    }
                                    p.getOrNull(5)?.trim()?.takeIf { it.isNotEmpty() }?.let { m.fields["desc"] = J.Str(it) }
                                    bmoves.items.add(m)
                                }
                                if (bmoves.items.isNotEmpty()) battle.fields["moves"] = bmoves
                                val bbuffs = J.Arr()
                                rBattleBuffs.split("\n").forEach { line ->
                                    val t = line.trim()
                                    if (t.isEmpty()) return@forEach
                                    val p = t.split("|")
                                    if (p.size < 2) return@forEach
                                    val id = p[0].trim()
                                    if (id.isEmpty()) return@forEach
                                    val b = J.Obj()
                                    b.fields["id"] = J.Str(id)
                                    b.fields["name"] = J.Str(p[1].trim().ifEmpty { id })
                                    b.fields["turns"] = J.Num((p.getOrNull(2)?.toIntOrNull() ?: 3).toDouble())
                                    p.getOrNull(3)?.trim()?.takeIf { it.isNotEmpty() }?.let { atStr ->
                                        val at = J.Obj()
                                        atStr.split(",").forEach { kv ->
                                            val sp = kv.split(":")
                                            if (sp.size == 2 && sp[0].isNotBlank() && sp[1].toIntOrNull() != null) {
                                                at.fields[sp[0].trim()] = J.Num((sp[1].toIntOrNull() ?: 0).toDouble())
                                            }
                                        }
                                        if (at.fields.isNotEmpty()) b.fields["attrs"] = at
                                    }
                                    p.getOrNull(4)?.trim()?.takeIf { it.isNotEmpty() }?.let { b.fields["desc"] = J.Str(it) }
                                    bbuffs.items.add(b)
                                }
                                if (bbuffs.items.isNotEmpty()) battle.fields["buffs"] = bbuffs
                                adv.fields["battle"] = battle
                            }
                            o.fields["advanced"] = adv
                            advancedByRole[nm] = adv
                        }
                        for ((k, v) in fields) {
                            if (v.isNotBlank()) o.fields[k] = J.Str(v)
                        }
                        f.writeText(JsonS.stringify(o, pretty = true), Charsets.UTF_8)
                        val idx = roles.indexOfFirst { it.first == nm }
                        if (idx >= 0) roles[idx] = nm to prompt else roles.add(nm to prompt)
                        if (selectedRoles.contains(nm)) {
                            reloadMech()
                        }
                    } catch (_: Exception) {
                    }
                }
                roleEditName = null
            }) { Text(I18n.t("btn_save", "保存")) }
        },
        dismissButton = { TextButton(onClick = { roleEditName = null }) { Text(I18n.t("btn_cancel", "取消")) } },
    )
    if (rCardFacePrev) {
        AlertDialog(
            onDismissRequest = { rCardFacePrev = false },
            text = { HtmlCard(rCardFace.ifBlank { "<div style='color:#888;padding:20px'>（空卡面，保存后生效）</div>" }, Modifier.fillMaxWidth().height(400.dp)) },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { rCardFacePrev = false }) { Text(I18n.t("btn_cancel", "关闭")) } },
        )
    }
    }
}
