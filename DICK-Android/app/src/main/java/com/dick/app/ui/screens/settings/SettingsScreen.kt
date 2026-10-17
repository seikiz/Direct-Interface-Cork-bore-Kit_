package com.dick.app

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import com.dick.core.ChatEngine
import com.dick.core.Lanes
import com.dick.core.TimeScale
import com.dick.core.Workshop

/**
 * SettingsScreen —— 设置屏（「API 配置」+「DICK · 设置」两个弹窗）。
 *
 * 结构：实现从 Dialogs.kt 搬到这里（纯结构搬家）；屏内瞬态在 SettingsState.kt，
 * 对外依赖在 SettingsActions.kt，状态一律来自 ChatViewModel。
 *
 * 这一屏的三条硬规矩（2026-11 修完 UI bug 之后写下来，别再退回去）：
 *   ① **文案一律走 I18n.t(key, 中文原串)**。裸中文字面量会被
 *      `tests/test_android_settings_i18n.py` 拦下来 —— 用户截图里"一半日文一半中文"
 *      就是这么来的（主题/语言走了表，其余硬编码）。
 *   ② **提示不塞进输入框**：label 画在框上方（[DickLabeledField]），
 *      需要解释的用框下方灰色小字；框里只放用户输入的值。
 *   ③ **按钮层级按语义挑变体**（见 ui/components/Buttons.kt 的三档表）：
 *      当前值/主操作 = Primary，进另一个面板 = Secondary，行内轻动作 = Plain。
 */
@Composable
fun SettingsScreen(vm: ChatViewModel, acts: SettingsActions) {

    val context = acts.context
    val theme = acts.theme
    val accent = acts.accent
    val engine = acts.engine
    val registry = acts.registry
    val gal = acts.gal
    val uiPlugin = acts.uiPlugin
    val apiKeysMap = vm.apiKeysMap
    var providerId by vm.providerId
    var baseUrl by vm.baseUrl
    var model by vm.model
    var apiKey by vm.apiKey
    var ollamaOnline by vm.ollamaOnline
    var customModelInput by vm.customModelInput
    var proxy by vm.proxy
    var relayUrl by vm.relayUrl
    var stopInput by vm.stopInput
    var regexInput by vm.regexInput
    var tempInput by vm.tempInput
    var topPInput by vm.topPInput
    var budgetIdx by vm.budgetIdx
    var speakReplies by vm.speakReplies
    var showPersonaEdit by vm.showPersonaEdit
    var themeIdx by vm.themeIdx
    var accentIdx by vm.accentIdx
    var presetIdx by vm.presetIdx
    var devMode by vm.devMode
    var humanize by vm.humanize
    var styleGuard by vm.styleGuard
    var styleGuardLong by vm.styleGuardLong
    var autoTurn by vm.autoTurn
    var language by vm.language
    val personaDisplayName = acts.personaDisplayName
    val saveConfig = acts.saveConfig
    val saveGlobalRegex = acts.saveGlobalRegex
    val appIconPicker = acts.appIconPicker
    var appIcon by vm.appIcon
    val wallpaperPicker = acts.wallpaperPicker
    val clearWallpaper = acts.clearWallpaper
    var wallpaper by vm.wallpaper
    if (vm.showApiSetup.value) {
    // 2026-11：向导化 —— 原先是"一屏塞下模型商/<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌模型/Key/Base/代理/中转/停止序列"的长表单，
    // 用户的原话是"这套引导不够"。现在拆成三步，每步只问一件事：
    //   ① 选服务商（卡片列表，免 Key 的会标出来）
    //   ② 填 Key（一个输入框 + 一行「去哪里拿」可点链接）
    //   ③ 点「测试并保存」—— ChatEngine.probeApi() 真连一次，通了才写 config；
    //      不通就把人话原因 + 下一步建议贴在按钮上方。
    // 「稍后再说」= 切到免费链厂商（不用 Key）直接保存，下次启动不再弹。
    // 高级项（代理/中转/停止序列/自定义模型）留在下面的「设置」里，不再挡在第①步前面。
    val wiz = rememberSettingsState()
    var step = wiz.apiStep
    var testing = wiz.apiTesting
    var testLine = wiz.apiTestLine
    val curProvider = PROVIDERS.firstOrNull { it.id == providerId }
    val freeNow = curProvider?.free == true
    fun persist() {
        apiKeysMap[providerId] = apiKey.trim()
        engine.apiKey = apiKey.trim()
        engine.model = model
        engine.baseUrl = baseUrl.trim().ifBlank { "https://api.deepseek.com" }
        engine.proxy = proxy.trim().ifBlank { null }
        val effRelay = relayUrl.trim().ifBlank { BUILTIN_RELAY }.ifBlank { null }
        if (engine.relayBase != effRelay) engine.relayOn = false
        engine.relayBase = effRelay
        engine.stopSequences = parseStops(stopInput)
        engine.allowEmptyKey = PROVIDERS.firstOrNull { it.id == providerId }?.free == true
        saveConfig()
        val k = apiKey.trim()
        Lanes.on(Lanes.net, "推送连接配置") {
            try { Workshop.pushApi(k, baseUrl.trim().ifBlank { "https://api.deepseek.com" }, model, providerId) } catch (_: Exception) {}
        }
    }
    fun runProbe() {
        testing = true
        testLine = I18n.t("apiWizTesting", "正在测试…（真实请求一次 /models）")
        val base = baseUrl.trim()
        val key = if (freeNow) "" else apiKey.trim()
        val mdl = model
        Lanes.on(Lanes.net, "测试 API Key") {
            val r = ChatEngine.probeApi(base, key, proxy.trim(), freeNow, mdl)
            testing = false
            if (r.first) {
                testLine = I18n.t("apiWizOk", "通了，已保存")
                persist()
                vm.showApiSetup.value = false
            } else {
                testLine = I18n.t("apiWizFail", "没通") + " — " + r.second
            }
        }
    }
    DickDialog(
        onDismissRequest = { vm.showApiSetup.value = false },
        title = { IconText(I18n.t("st_api_title", "API 配置（模型商 / 模型 / Key）"), icon = "key") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                // ---- 步骤指示（三步一句一档，当前步用强调色） ----
                Row(Modifier.fillMaxWidth()) {
                    listOf(
                        I18n.t("apiWizStep1", "① 选服务商"),
                        I18n.t("apiWizStep2", "② 填 Key"),
                        I18n.t("apiWizStep3", "③ 测试并保存"),
                    ).forEachIndexed { i, label ->
                        Text(
                            label,
                            fontSize = 11.sp,
                            color = if (i == step) accent else theme.muted,
                            modifier = Modifier.padding(end = 10.dp, bottom = 8.dp),
                        )
                    }
                }
                if (step == 0) {
                    // ---- ① 选服务商：卡片列表 ----
                    Text(I18n.t("st_provider", "模型商"), fontSize = 13.sp, color = theme.muted)
                    PROVIDERS.forEach { p ->
                        DickActionButton(
                            label = (if (p.id == providerId) "● " else "○ ") + p.name +
                                (if (p.free) I18n.t("st_free_suffix", "（免 Key）") else "") +
                                (if (p.id == "ollama") (if (ollamaOnline) I18n.t("st_ollama_online", " · 本地已连接")
                                                         else I18n.t("st_ollama_offline", " · 本地未检测到")) else ""),
                            onClick = {
                                providerId = p.id
                                baseUrl = p.baseUrl
                                model = p.models.first()
                                apiKey = apiKeysMap[p.id] ?: ""
                                testLine = ""
                            },
                            variant = DickButtonVariant.Plain,
                            modifier = Modifier.fillMaxWidth(),
                            fontSize = 13.sp,
                            color = if (p.id == providerId) accent else Color.Unspecified,
                        )
                    }
                } else if (step == 1) {
                    // ---- ② 填 Key：一个输入框 + 一行「去哪里拿」 ----
                    Text(curProvider?.name ?: "", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                        color = theme.text, modifier = Modifier.padding(bottom = 6.dp))
                    DickLabeledField(
                        value = apiKey, onValueChange = { apiKey = it },
                        label = if (freeNow) I18n.t("st_api_key_free", "API Key（免 Key，可留空）")
                                else I18n.t("st_api_key", "API Key"),
                        singleLine = true,
                        enabled = !freeNow,
                    )
                    if (freeNow) {
                        Text(I18n.t("apiWizFree", "这家免 Key，直接可用"), fontSize = 11.sp,
                            color = theme.muted, modifier = Modifier.padding(top = 4.dp))
                    } else {
                        val where = curProvider?.buyUrl ?: ""
                        DickActionButton(
                            label = I18n.t("btn_buy", "去官网注册/充值"),
                            variant = DickButtonVariant.Plain,
                            fontSize = 12.sp,
                            onClick = {
                                if (where.isNotBlank()) {
                                    try {
                                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(where)))
                                    } catch (_: Exception) {
                                    }
                                }
                            }, icon = "key"
                        )
                        DickActionButton(
                            label = I18n.t("apiWizWhere", "去哪里拿 Key") + " → " + where,
                            variant = DickButtonVariant.Plain,
                            fontSize = 11.sp,
                            onClick = {
                                if (where.isNotBlank()) {
                                    try {
                                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(where)))
                                    } catch (_: Exception) {
                                    }
                                }
                            },
                        )
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(I18n.t("st_base_url", "Base URL") + "：" + (curProvider?.baseUrl ?: baseUrl),
                        fontSize = 11.sp, color = theme.muted)
                    Text(I18n.t("st_model", "模型") + "：" + model, fontSize = 11.sp, color = theme.muted)
                } else {
                    // ---- ③ 测试并保存 ----
                    Text(curProvider?.name ?: "", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                        color = theme.text, modifier = Modifier.padding(bottom = 6.dp))
                    Text(I18n.t("st_base_url", "Base URL") + "：" +
                        baseUrl.trim().ifBlank { curProvider?.baseUrl ?: "" },
                        fontSize = 11.sp, color = theme.muted)
                    Text(I18n.t("st_model", "模型") + "：" + model, fontSize = 11.sp, color = theme.muted)
                    Spacer(Modifier.height(8.dp))
                    Text(testLine, fontSize = 12.sp,
                        color = if (testLine == I18n.t("apiWizOk", "通了，已保存")) theme.palette.ok else theme.muted)
                    Spacer(Modifier.height(8.dp))
                    // ---- 高级连线项 ----
                    // 这些字段原来在那个"一屏塞到底"的长表单里；改成向导之后**不能丢**——
                    // 直连被墙的人只有在这里填代理才连得上。放在第③步（测试那一步）最顺手：
                    // 测不通 → 就地改 → 再测。
                    Text(I18n.t("st_model", "模型"), fontSize = 12.sp, color = theme.muted)
                    (curProvider?.models ?: emptyList()).forEach { m ->
                        DickActionButton(
                            label = (if (m == model) "● " else "○ ") + m,
                            onClick = { model = m },
                            variant = DickButtonVariant.Plain,
                            modifier = Modifier.fillMaxWidth(),
                            fontSize = 12.sp,
                            color = if (m == model) accent else Color.Unspecified,
                        )
                    }
                    if (model.isNotBlank() && model !in (curProvider?.models ?: emptyList())) {
                        DickActionButton(
                            label = "● " + model + I18n.t("st_current_suffix", "（当前）"),
                            onClick = {},
                            variant = DickButtonVariant.Plain,
                            modifier = Modifier.fillMaxWidth(),
                            fontSize = 12.sp, color = accent,
                        )
                    }
                    DickLabeledField(value = customModelInput, onValueChange = { customModelInput = it },
                        label = I18n.t("st_custom_model", "自定义模型 ID"), singleLine = true)
                    DickActionButton(
                        label = I18n.t("st_use_custom", "使用自定义模型"),
                        onClick = { if (customModelInput.isNotBlank()) model = customModelInput.trim() },
                        variant = DickButtonVariant.Plain,
                        fontSize = 12.sp,
                    )
                    DickLabeledField(value = baseUrl, onValueChange = { baseUrl = it },
                        label = I18n.t("st_base_url", "Base URL"),
                        hint = I18n.t("st_base_hint", "选模型商时自动填"), singleLine = true)
                    Spacer(Modifier.height(6.dp))
                    DickLabeledField(value = proxy, onValueChange = { proxy = it },
                        label = I18n.t("st_proxy", "代理"),
                        hint = I18n.t("st_proxy_hint", "通道不通时填，如 http://127.0.0.1:7890"), singleLine = true)
                    Spacer(Modifier.height(6.dp))
                    DickLabeledField(value = relayUrl, onValueChange = { relayUrl = it },
                        label = I18n.t("st_relay", "内置代理通道"),
                        hint = I18n.t("st_relay_hint", "直连失败自动走中转"), singleLine = true)
                    Text(if (engine.relayOn) I18n.t("st_relay_on", "● 中转通道已启用（直连失败已自动切换）")
                         else I18n.t("st_relay_off", "○ 直连模式（直连失败自动走中转）"),
                        fontSize = 11.sp, color = theme.muted)
                    Spacer(Modifier.height(6.dp))
                    DickLabeledField(value = stopInput, onValueChange = { stopInput = it },
                        label = I18n.t("st_stop", "停止序列"),
                        hint = I18n.t("st_stop_hint", "逗号分隔，如 <|im_end|>, </s>"), singleLine = true)
                    Spacer(Modifier.height(4.dp))
                    DickActionButton(
                        label = I18n.t("apiWizLater", "稍后再说（先用免费链）"),
                        variant = DickButtonVariant.Plain,
                        fontSize = 12.sp,
                        onClick = {
                            val f = PROVIDERS.firstOrNull { it.free }
                            if (f != null) {
                                providerId = f.id
                                baseUrl = f.baseUrl
                                model = f.models.first()
                                apiKey = ""
                                runProbe()
                            } else {
                                vm.showApiSetup.value = false
                            }
                        },
                    )
                }
            }
        },
        confirmButton = {
            Row {
                if (step > 0) {
                    DickActionButton(label = I18n.t("apiWizPrev", "上一步"),
                        variant = DickButtonVariant.Plain, fontSize = 12.sp,
                        onClick = { step -= 1; testLine = ""; wiz.apiStep = step })
                }
                if (step < 2) {
                    DickActionButton(label = I18n.t("apiWizNext", "下一步"),
                        variant = DickButtonVariant.Primary, fontSize = 12.sp,
                        onClick = { step += 1; testLine = ""; wiz.apiStep = step })
                } else {
                    DickActionButton(
                        label = if (testing) I18n.t("apiWizTesting", "正在测试…（真实请求一次 /models）")
                                else I18n.t("apiWizStep3", "③ 测试并保存"),
                        variant = DickButtonVariant.Primary, fontSize = 12.sp,
                        enabled = !testing,
                        onClick = { runProbe() },
                    )
                }
            }
        },
        dismissButton = {
            DickActionButton(label = I18n.t("btn_cancel", "取消"), variant = DickButtonVariant.Plain,
                onClick = { vm.showApiSetup.value = false })
        },
    )
    }
    if (vm.showSettings.value) {
    // 屏内瞬态（原来就住在弹窗里：弹窗一关就重置）—— 位置没动，只是搬进了 SettingsState
    val state = rememberSettingsState()
    DickDialog(
        onDismissRequest = { vm.showSettings.value = false },
        title = { Text(I18n.t("dlg_settings", "DICK · 设置")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Spacer(Modifier.height(6.dp))
                // 2026-11：API 教程 + 重开向导。位置在**最上面** —— 用户填不动的那一刻
                // 就在找这两个入口，塞到最底下等于没有。
                Row {
                    DickActionButton(
                        label = I18n.t("apiGuideBtn", "API 教程"),
                        variant = DickButtonVariant.Secondary, fontSize = 12.sp,
                        onClick = { vm.showApiGuide.value = true }, icon = "menu_book"
                    )
                    Spacer(Modifier.width(6.dp))
                    DickActionButton(
                        label = I18n.t("apiWizardBtn", "重新打开配置向导"),
                        variant = DickButtonVariant.Plain, fontSize = 12.sp,
                        onClick = { vm.showApiSetup.value = true }, icon = "explore"
                    )
                }
                Spacer(Modifier.height(6.dp))
                DickLabeledField(value = regexInput, onValueChange = { regexInput = it },
                    label = I18n.t("st_regex", "正则规则（每行 id|名称|正则|替换|作用域；ai/user/both）"),
                    minLines = 4)
                Spacer(Modifier.height(6.dp))
                Row {
                    DickLabeledField(value = tempInput, onValueChange = { tempInput = it },
                        label = I18n.t("st_temp", "温度"),
                        hint = I18n.t("st_hint_default", "留空 = 默认"),
                        singleLine = true, modifier = Modifier.weight(1f))
                    Spacer(Modifier.width(6.dp))
                    DickLabeledField(value = topPInput, onValueChange = { topPInput = it },
                        label = I18n.t("st_topp", "top_p"),
                        hint = I18n.t("st_hint_default", "留空 = 默认"),
                        singleLine = true, modifier = Modifier.weight(1f))
                }
                Spacer(Modifier.height(6.dp))
                // 界面语言：三选一（中文 / English / 日本語）。当前那档是实心按钮，
                // 点别的档立刻生效并落盘（config.json 的 language）。
                Text(I18n.t("st_lang", "语言"), fontSize = 13.sp, color = theme.muted)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    for (code in I18n.LANGS) {
                        val label = I18n.langName(code)
                        DickActionButton(
                            label = label,
                            onClick = if (code == language) ({ }) else ({ language = code; I18n.lang = code; saveConfig() }),
                            variant = if (code == language) DickButtonVariant.Primary else DickButtonVariant.Plain,
                            modifier = Modifier.heightIn(min = 34.dp),
                            fontSize = 12.sp,
                        )
                        Spacer(Modifier.width(4.dp))
                    }
                }
                Spacer(Modifier.height(6.dp))
                // 预设 / 预算 / 主题 / 强调色：都是"点一下换到下一个值"，形状统一用 Primary
                //（当前值就摆在这儿，它本身就是主信息）。
                DickActionButton(
                    label = I18n.t("lbl_preset", "预设：") + presetLabel(presetIdx),
                    onClick = { presetIdx = (presetIdx + 1) % PRESETS.size },
                    variant = DickButtonVariant.Primary,
                )
                Spacer(Modifier.height(6.dp))
                DickActionButton(
                    label = I18n.budgetLabel(BUDGETS[budgetIdx].first),
                    onClick = { budgetIdx = (budgetIdx + 1) % BUDGETS.size },
                    variant = DickButtonVariant.Primary,
                )
                Spacer(Modifier.height(6.dp))
                //  时间流速 / 生活空间 / 应用图标 / 壁纸 / 玩家卡：都是"进另一个面板"，
                // 统一 Secondary（描边）—— 次级入口不该和"当前值"抢同一档视觉。
                DickActionButton(
                    label = I18n.t("st_timedial", "时间流速") + "　" + TimeScale.describe(vm.timeScale.value),
                    onClick = { vm.showTimeDial.value = true },
                    variant = DickButtonVariant.Secondary,
                    modifier = Modifier.fillMaxWidth(),
                    fontSize = 13.sp, icon = "hourglass_empty"
                )
                Spacer(Modifier.height(6.dp))
                DickActionButton(
                    label = I18n.t("st_lifespace", "生活 / 空间 / 世界卡库（吃饭 · 不能瞬移 · 卡包）"),
                    onClick = { vm.showLifeSpace.value = true },
                    variant = DickButtonVariant.Secondary,
                    modifier = Modifier.fillMaxWidth(),
                    fontSize = 13.sp,
                )
                Spacer(Modifier.height(6.dp))
                DickActionButton(
                    label = I18n.t("st_appicon", "应用图标") +
                        (if (appIcon != null) I18n.t("st_set_hint", "（已设置，点击更换）")
                         else I18n.t("st_pick_hint", "（点击从相册选择）")),
                    onClick = { appIconPicker.launch("image/*") },
                    variant = DickButtonVariant.Secondary,
                    modifier = Modifier.fillMaxWidth(),
                    fontSize = 13.sp, icon = "palette"
                )
                Spacer(Modifier.height(6.dp))
                DickActionButton(
                    label = I18n.t("st_wallpaper", "壁纸（聊天背景）") +
                        (if (wallpaper != null) I18n.t("st_set_hint", "（已设置，点击更换）")
                         else I18n.t("st_pick_hint", "（点击从相册选择）")),
                    onClick = { wallpaperPicker.launch("image/*") },
                    variant = DickButtonVariant.Secondary,
                    modifier = Modifier.fillMaxWidth(),
                    fontSize = 13.sp, icon = "image"
                )
                if (wallpaper != null) {
                    Spacer(Modifier.height(4.dp))
                    DickActionButton(
                        label = I18n.t("st_wallpaper_clear", "恢复默认背景"),
                        onClick = { clearWallpaper() },
                        variant = DickButtonVariant.Secondary,
                        modifier = Modifier.fillMaxWidth(),
                        fontSize = 13.sp, icon = "delete_sweep"
                    )
                }
                Spacer(Modifier.height(6.dp))
                DickActionButton(
                    label = I18n.t("btn_persona_card", "玩家角色卡") +
                        (if (personaDisplayName().isNotBlank()) "：" + personaDisplayName() else ""),
                    onClick = { showPersonaEdit = true },
                    variant = DickButtonVariant.Secondary,
                    modifier = Modifier.fillMaxWidth(),
                    fontSize = 13.sp, icon = "person"
                )
                Spacer(Modifier.height(6.dp))
                DickCheckRow(label = I18n.t("chk_auto", "自动接话（群聊时其他角色自动跟进）"),
                    checked = autoTurn, onCheckedChange = { autoTurn = it }, icon = "smart_toy")
                DickCheckRow(label = I18n.t("chk_tts", "朗读 AI 回复（系统 TTS）"),
                    checked = speakReplies, onCheckedChange = { speakReplies = it })
                DickCheckRow(label = I18n.t("st_dev", "开发者模式（解锁角色卡高级设置/内置游戏）"),
                    checked = devMode, onCheckedChange = { devMode = it }, icon = "build")
                DickCheckRow(label = I18n.t("st_humanize", "去 AI 味（具体细节/生活有变化/口语不完美/引用共同记忆）"),
                    checked = humanize, onCheckedChange = { humanize = it }, icon = "accessibility_new")
                DickCheckRow(label = I18n.t("st_style", "风格闸（去文学化漂移：生活词/比喻→事实/拆长句）"),
                    checked = styleGuard, onCheckedChange = { styleGuard = it }, topPadding = 8.dp, icon = "tune")
                DickCheckRow(label = I18n.t("st_long", "长句模式（不拆长句，允许更流畅/文学化表达）"),
                    checked = styleGuardLong, onCheckedChange = { styleGuardLong = it }, topPadding = 4.dp, icon = "waves")
                Spacer(Modifier.height(10.dp))
                FoldHead(I18n.t("st_plugins", "插件"), state.foldPlugins, onToggle = { state.foldPlugins = !state.foldPlugins }, icon = "extension")
                if (state.foldPlugins) {
                for (p in registry.plugins) {
                    var enabled by remember(p) { mutableStateOf(p.enabled) }
                    Row {
                        Checkbox(checked = enabled, onCheckedChange = { enabled = it; p.enabled = it })
                        Column(Modifier.padding(top = 10.dp)) {
                            Text(p.name + " v" + p.version, fontSize = 13.sp)
                            Text(p.description, fontSize = 11.sp, color = theme.muted)
                        }
                    }
                    if (p === uiPlugin && enabled) {
                        Row {
                            DickActionButton(
                                label = I18n.t("lbl_theme", "主题：") + themeLabel(themeIdx),
                                onClick = { themeIdx = (themeIdx + 1) % THEMES.size },
                                variant = DickButtonVariant.Primary,
                                fontSize = 12.sp,
                            )
                            Spacer(Modifier.width(8.dp))
                            DickActionButton(
                                label = I18n.t("lbl_accent", "强调色：") + accentLabel(accentIdx),
                                onClick = { accentIdx = (accentIdx + 1) % ACCENTS.size },
                                variant = DickButtonVariant.Primary,
                                fontSize = 12.sp,
                            )
                        }
                        Spacer(Modifier.height(6.dp))
                    }
                    if (p === gal && enabled) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(I18n.t("st_gal_count", "每轮选项："), fontSize = 12.sp)
                            DickActionButton(label = "−", onClick = { gal.count = maxOf(2, gal.count - 1) },
                                variant = DickButtonVariant.Plain, fontSize = 16.sp)
                            Text(gal.count.toString(), fontSize = 13.sp)
                            DickActionButton(label = "＋", onClick = { gal.count = minOf(4, gal.count + 1) },
                                variant = DickButtonVariant.Plain, fontSize = 16.sp)
                            Spacer(Modifier.width(12.dp))
                            Checkbox(checked = gal.auto, onCheckedChange = { gal.auto = it })
                            Text(I18n.t("st_gal_auto", "自动生成"), fontSize = 12.sp, modifier = Modifier.padding(top = 14.dp))
                        }
                        Spacer(Modifier.height(4.dp))
                    }
                }
                }
            }
        },
        confirmButton = {
            DickActionButton(label = I18n.t("btn_save", "保存"), variant = DickButtonVariant.Primary, onClick = {
                apiKeysMap[providerId] = apiKey.trim()
                engine.apiKey = apiKey.trim()
                engine.model = model
                engine.baseUrl = baseUrl.trim().ifBlank { "https://api.deepseek.com" }
                engine.proxy = proxy.trim().ifBlank { null }
                val effRelay = relayUrl.trim().ifBlank { BUILTIN_RELAY }.ifBlank { null }
                if (engine.relayBase != effRelay) engine.relayOn = false  // 改了中转地址 → 回到直连优先
                engine.relayBase = effRelay
                engine.stopSequences = parseStops(stopInput)
                engine.temperature = tempInput.toFloatOrNull()
                engine.topP = topPInput.toFloatOrNull()
                engine.allowEmptyKey = PROVIDERS.firstOrNull { it.id == providerId }?.free == true
                saveGlobalRegex(regexInput)
                saveConfig()
                val k = apiKey.trim()
                // 同上：推送共享连接配置走 net 线
                Lanes.on(Lanes.net, "推送连接配置") {
                    try {
                        Workshop.pushApi(k, baseUrl.trim().ifBlank { "https://api.deepseek.com" }, model, providerId)
                    } catch (_: Exception) {}
                }
                vm.showSettings.value = false
            })
        },
        dismissButton = {
            DickActionButton(label = I18n.t("btn_cancel", "取消"), variant = DickButtonVariant.Plain,
                onClick = { vm.showSettings.value = false })
        },
    )
    }
}
