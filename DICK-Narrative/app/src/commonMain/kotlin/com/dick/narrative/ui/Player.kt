package com.dick.narrative.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.narrative.engine.NarrativeEngine
import com.dick.narrative.engine.NarrativeSpec
import com.dick.narrative.platform.joinPath
import com.dick.narrative.platform.platformName
import com.dick.narrative.platform.playAudio
import com.dick.narrative.platform.setFullscreen
import com.dick.narrative.platform.stopAllAudio
import kotlinx.coroutines.delay

private enum class Overlay { None, Menu, Backlog, Settings, Save, Load, Gallery }

/**
 * 播放器（桌面与手机共用）。
 *
 * 引擎负责「故事怎么走」，这里只负责「画出来 + 接输入」。
 * 交互：点任意处推进 → 正在打字时先出完字；Esc 菜单；空格/回车推进。
 */
@Composable
fun NarrativePlayer(
    root: String,
    spec: NarrativeSpec,
    onQuit: () -> Unit = {},
) {
    val engine = remember { NarrativeEngine(spec) }

    var frame by remember { mutableStateOf(engine.frame()) }
    var tick by remember { mutableStateOf(0) }
    var settings by remember { mutableStateOf(SettingsStore.load()) }
    var overlay by remember { mutableStateOf(Overlay.None) }
    var showTitle by remember { mutableStateOf(true) }
    var revealed by remember { mutableStateOf(0) }
    var shake by remember { mutableStateOf(0f) }
    var flash by remember { mutableStateOf(0f) }
    var toast by remember { mutableStateOf("") }

    val focus = remember { FocusRequester() }

    fun sync() {
        frame = engine.frame()
        tick++
    }

    // 启动：应用<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌设置里的全屏
    LaunchedEffect(Unit) {
        setFullscreen(settings.fullscreen)
        focus.requestFocus()
    }

    // 设置变了就落盘
    LaunchedEffect(settings) { SettingsStore.save(settings) }

    // 打字机
    LaunchedEffect(tick, settings.textSpeed) {
        val full = displayText(frame)
        revealed = 0
        if (settings.textSpeed <= 0f || full.isEmpty()) {
            revealed = full.length
            return@LaunchedEffect
        }
        val per = (1000f / settings.textSpeed).toLong().coerceIn(8L, 500L)
        var i = 0
        while (i < full.length) {
            delay(per)
            i++
            revealed = i
        }
    }

    // 音频
    LaunchedEffect(frame.bgm) {
        if (frame.bgm.isNotBlank()) playAudio(joinPath(root, frame.bgm), true, settings.volume)
    }
    LaunchedEffect(frame.voiceTick) {
        if (frame.voiceTick > 0 && frame.voice.isNotBlank()) {
            playAudio(joinPath(root, frame.voice), false, settings.volume)
        }
    }
    LaunchedEffect(frame.sfxTick) {
        if (frame.sfxTick > 0 && frame.sfx.isNotBlank()) {
            playAudio(joinPath(root, frame.sfx), false, settings.volume)
        }
    }

    // 特效
    LaunchedEffect(frame.effectTick) {
        if (frame.effectTick == 0) return@LaunchedEffect
        val e = frame.effect.lowercase()
        when {
            e.contains("shake") || e.contains("震") -> {
                for (i in 0 until 14) {
                    shake = if (i % 2 == 0) 16f else -16f
                    delay(30)
                }
                shake = 0f
            }
            e.contains("flash") || e.contains("闪") -> {
                flash = 0.85f
                repeat(14) {
                    flash = (flash - 0.065f).coerceAtLeast(0f)
                    delay(28)
                }
                flash = 0f
            }
        }
    }

    // 自动存档：每进入新的一条线存一次
    LaunchedEffect(frame.lineId, showTitle) {
        if (!showTitle && frame.lineId.isNotBlank()) SaveStore.save(SaveStore.AUTO, engine)
    }

    LaunchedEffect(toast) {
        if (toast.isNotBlank()) {
            delay(1600)
            toast = ""
        }
    }

    fun advance() {
        if (overlay != Overlay.None || showTitle) return
        if (frame.choices.isNotEmpty() || frame.ended) return
        val full = displayText(frame)
        if (revealed < full.length) {
            revealed = full.length          // 第一次点：把字出完
            return
        }
        engine.advance()
        sync()
    }

    fun startNew() {
        stopAllAudio()
        engine.start()
        sync()
        showTitle = false
        overlay = Overlay.None
    }

    fun loadSlot(slot: Int) {
        if (SaveStore.load(slot, engine)) {
            sync()
            showTitle = false
            overlay = Overlay.None
        } else {
            toast = "这个存档是空的"
        }
    }

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(Ink)
            .focusRequester(focus)
            .focusable()
            .onPreviewKeyEvent { e ->
                if (e.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                when (e.key) {
                    Key.Spacebar, Key.Enter -> {
                        advance(); true
                    }
                    Key.Escape -> {
                        overlay = if (overlay == Overlay.None) Overlay.Menu else Overlay.None
                        showTitle = false
                        true
                    }
                    else -> false
                }
            }
    ) {
        val wide = maxWidth > 720.dp

        Box(
            modifier = Modifier
                .fillMaxSize()
                .offset(x = shake.dp, y = (shake * 0.4f).dp)
                .clickable(
                    indication = null,
                    interactionSource = remember { MutableInteractionSource() }
                ) { advance() }
        ) {
            // ---- 背景 ----
            if (frame.bg.isNotBlank()) {
                StoryImage(root, frame.bg, Modifier.fillMaxSize(), ContentScale.Crop)
            }

            // ---- 立绘 ----
            Row(
                modifier = Modifier.fillMaxSize(),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.Bottom,
            ) {
                frame.sprites.forEach { sp ->
                    StoryImage(
                        root,
                        sp.file,
                        Modifier.fillMaxHeight(0.92f).widthIn(max = if (wide) 520.dp else 320.dp),
                        ContentScale.Fit,
                    )
                }
            }

            // ---- 剧照 / CG ----
            frame.images.firstOrNull()?.let { img ->
                StoryImage(root, img, Modifier.fillMaxSize(), ContentScale.Fit)
            }

            // ---- 顶部：线名 + 按钮 ----
            Row(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(if (wide) 18.dp else 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (frame.lineTitle.isNotBlank() && !showTitle) {
                    Text(
                        frame.lineTitle,
                        color = TextSub,
                        fontSize = if (wide) 13.sp else 11.sp,
                        modifier = Modifier.padding(end = 12.dp),
                    )
                }
                TinyBtn("回想") { overlay = Overlay.Backlog }
                Spacer(Modifier.width(6.dp))
                TinyBtn("设置") { overlay = Overlay.Settings }
                Spacer(Modifier.width(6.dp))
                TinyBtn("菜单") { overlay = Overlay.Menu }
            }

            // ---- 对话框 ----
            if (!showTitle && frame.choices.isEmpty() && !frame.ended) {
                Column(
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .fillMaxWidth()
                        .padding(
                            start = if (wide) 48.dp else 10.dp,
                            end = if (wide) 48.dp else 10.dp,
                            bottom = if (wide) 28.dp else 12.dp,
                        ),
                ) {
                    if (frame.speaker.isNotBlank()) {
                        Surface(
                            color = Panel,
                            border = BorderStroke(1.dp, AccentDim),
                            shape = RoundedCornerShape(2.dp),
                        ) {
                            Text(
                                frame.speaker,
                                color = Accent,
                                fontSize = if (wide) 16.sp else 14.sp,
                                fontWeight = FontWeight.Medium,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp),
                            )
                        }
                        Spacer(Modifier.height(6.dp))
                    }
                    Surface(
                        color = Panel.copy(alpha = 0.94f),
                        border = BorderStroke(1.dp, LineCol),
                        shape = RoundedCornerShape(2.dp),
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(min = if (wide) 140.dp else 108.dp, max = if (wide) 220.dp else 190.dp)
                                .padding(if (wide) 20.dp else 14.dp),
                        ) {
                            Text(
                                displayText(frame).take(revealed),
                                color = if (frame.note.isNotBlank()) TextSub else TextMain,
                                fontSize = if (wide) 17.sp else 15.sp,
                                lineHeight = if (wide) 28.sp else 24.sp,
                            )
                        }
                    }
                }
            }

            // ---- 分支选项 ----
            if (frame.choices.isNotEmpty()) {
                Column(
                    modifier = Modifier.align(Alignment.Center),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    frame.choices.forEach { c ->
                        ChoiceBtn(c.text) {
                            engine.choose(c.index)
                            sync()
                        }
                        Spacer(Modifier.height(12.dp))
                    }
                }
            }

            // ---- 结局 ----
            if (frame.ended && !showTitle) {
                Box(
                    Modifier.fillMaxSize().background(Ink.copy(alpha = 0.88f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("— " + frame.endTitle + " —", color = Accent, fontSize = if (wide) 30.sp else 22.sp)
                        Spacer(Modifier.height(28.dp))
                        BigBtn("重新开始") { startNew() }
                        Spacer(Modifier.height(10.dp))
                        BigBtn("读档") { overlay = Overlay.Load }
                        Spacer(Modifier.height(10.dp))
                        BigBtn("退出") { onQuit() }
                    }
                }
            }

            // ---- 闪光 ----
            if (flash > 0f) {
                Box(Modifier.fillMaxSize().background(Color.White.copy(alpha = flash)))
            }

            // ---- 标题界面 ----
            if (showTitle) {
                TitleScreen(
                    spec = spec,
                    onStart = { startNew() },
                    onContinue = { loadSlot(SaveStore.AUTO) },
                    onGallery = { overlay = Overlay.Gallery },
                    onSettings = { overlay = Overlay.Settings },
                    onQuit = onQuit,
                )
            }

            // ---- 提示条 ----
            if (toast.isNotBlank()) {
                Surface(
                    color = Panel,
                    border = BorderStroke(1.dp, AccentDim),
                    shape = RoundedCornerShape(2.dp),
                    modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 16.dp),
                ) {
                    Text(toast, color = TextMain, fontSize = 13.sp, modifier = Modifier.padding(12.dp))
                }
            }

            // ---- 叠加层 ----
            when (overlay) {
                Overlay.Menu -> MenuOverlay(
                    onResume = { overlay = Overlay.None },
                    onSave = { overlay = Overlay.Save },
                    onLoad = { overlay = Overlay.Load },
                    onBacklog = { overlay = Overlay.Backlog },
                    onSettings = { overlay = Overlay.Settings },
                    onGallery = { overlay = Overlay.Gallery },
                    onTitle = { overlay = Overlay.None; showTitle = true },
                    onQuit = onQuit,
                )

                Overlay.Backlog -> BacklogOverlay(engine, onClose = { overlay = Overlay.None })

                Overlay.Settings -> SettingsOverlay(
                    settings = settings,
                    onChange = { settings = it },
                    onClose = { overlay = Overlay.None },
                )

                Overlay.Save -> SaveOverlay(
                    engine = engine,
                    loadMode = false,
                    onPick = { slot ->
                        if (SaveStore.save(slot, engine)) toast = "已存入存档 $slot" else toast = "存档失败"
                        overlay = Overlay.Menu
                    },
                    onClose = { overlay = Overlay.None },
                )

                Overlay.Load -> SaveOverlay(
                    engine = engine,
                    loadMode = true,
                    onPick = { slot -> loadSlot(slot) },
                    onClose = { overlay = Overlay.None },
                )

                Overlay.Gallery -> GalleryOverlay(root, spec, onClose = { overlay = Overlay.None })

                Overlay.None -> Unit
            }
        }
    }
}

private fun displayText(f: Frame): String = if (f.text.isNotBlank()) f.text else f.note

// ---------------- 小控件 ----------------

@Composable
private fun TinyBtn(text: String, onClick: () -> Unit) {
    Surface(
        color = Panel.copy(alpha = 0.75f),
        border = BorderStroke(1.dp, LineCol),
        shape = RoundedCornerShape(2.dp),
        modifier = Modifier.clickable { onClick() },
    ) {
        Text(text, color = TextSub, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp))
    }
}

@Composable
private fun ChoiceBtn(text: String, onClick: () -> Unit) {
    Surface(
        color = Panel.copy(alpha = 0.95f),
        border = BorderStroke(1.dp, AccentDim),
        shape = RoundedCornerShape(2.dp),
        modifier = Modifier.widthIn(min = 280.dp, max = 560.dp).clickable { onClick() },
    ) {
        Text(
            text,
            color = TextMain,
            fontSize = 16.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 13.dp),
        )
    }
}

@Composable
private fun BigBtn(text: String, onClick: () -> Unit) {
    Surface(
        color = Panel,
        border = BorderStroke(1.dp, AccentDim),
        shape = RoundedCornerShape(2.dp),
        modifier = Modifier.width(240.dp).clickable { onClick() },
    ) {
        Text(
            text,
            color = TextMain,
            fontSize = 16.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp),
        )
    }
}

@Composable
private fun Scrim(content: @Composable () -> Unit) {
    Box(
        Modifier.fillMaxSize().background(Ink.copy(alpha = 0.9f)),
        contentAlignment = Alignment.Center,
    ) { content() }
}

@Composable
private fun Panel(title: String, width: Int = 520, content: @Composable () -> Unit) {
    Surface(
        color = Panel,
        border = BorderStroke(1.dp, LineCol),
        shape = RoundedCornerShape(2.dp),
        modifier = Modifier.widthIn(max = width.dp).padding(18.dp),
    ) {
        Column(Modifier.padding(20.dp)) {
            Text(title, color = Accent, fontSize = 18.sp)
            Spacer(Modifier.height(14.dp))
            content()
        }
    }
}

// ---------------- 叠加层 ----------------

@Composable
private fun TitleScreen(
    spec: NarrativeSpec,
    onStart: () -> Unit,
    onContinue: () -> Unit,
    onGallery: () -> Unit,
    onSettings: () -> Unit,
    onQuit: () -> Unit,
) {
    Box(Modifier.fillMaxSize().background(Ink), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(spec.name, color = TextMain, fontSize = 40.sp, fontWeight = FontWeight.Light)
            if (spec.intro.isNotBlank()) {
                Spacer(Modifier.height(14.dp))
                Text(spec.intro, color = TextSub, fontSize = 14.sp, textAlign = TextAlign.Center,
                    modifier = Modifier.widthIn(max = 520.dp))
            }
            Spacer(Modifier.height(10.dp))
            Box(Modifier.width(120.dp).height(1.dp).background(AccentDim))
            Spacer(Modifier.height(34.dp))
            BigBtn("开始新游戏") { onStart() }
            Spacer(Modifier.height(10.dp))
            BigBtn("继续游戏") { onContinue() }
            Spacer(Modifier.height(10.dp))
            BigBtn("CG 鉴赏") { onGallery() }
            Spacer(Modifier.height(10.dp))
            BigBtn("设置") { onSettings() }
            Spacer(Modifier.height(10.dp))
            BigBtn("退出") { onQuit() }
        }
    }
}

@Composable
private fun MenuOverlay(
    onResume: () -> Unit,
    onSave: () -> Unit,
    onLoad: () -> Unit,
    onBacklog: () -> Unit,
    onSettings: () -> Unit,
    onGallery: () -> Unit,
    onTitle: () -> Unit,
    onQuit: () -> Unit,
) {
    Scrim {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("菜 单", color = Accent, fontSize = 22.sp)
            Spacer(Modifier.height(22.dp))
            BigBtn("继续") { onResume() }
            Spacer(Modifier.height(9.dp))
            BigBtn("存档") { onSave() }
            Spacer(Modifier.height(9.dp))
            BigBtn("读档") { onLoad() }
            Spacer(Modifier.height(9.dp))
            BigBtn("回想") { onBacklog() }
            Spacer(Modifier.height(9.dp))
            BigBtn("设置") { onSettings() }
            Spacer(Modifier.height(9.dp))
            BigBtn("CG 鉴赏") { onGallery() }
            Spacer(Modifier.height(9.dp))
            BigBtn("回到标题") { onTitle() }
            Spacer(Modifier.height(9.dp))
            BigBtn("退出") { onQuit() }
        }
    }
}

@Composable
private fun BacklogOverlay(engine: NarrativeEngine, onClose: () -> Unit) {
    Scrim {
        Panel("回 想", 700) {
            Column(
                Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())
            ) {
                engine.backlog.takeLast(200).forEach { e ->
                    if (e.speaker.isNotBlank()) {
                        Text(e.speaker, color = Accent, fontSize = 13.sp)
                    }
                    Text(e.text, color = TextMain, fontSize = 14.sp,
                        modifier = Modifier.padding(bottom = 10.dp))
                }
                if (engine.backlog.isEmpty()) Text("（还没有台词）", color = TextSub, fontSize = 13.sp)
            }
            Spacer(Modifier.height(16.dp))
            BigBtn("关闭") { onClose() }
        }
    }
}

@Composable
private fun SettingsOverlay(settings: Settings, onChange: (Settings) -> Unit, onClose: () -> Unit) {
    Scrim {
        Panel("设 置", 520) {
            Text("文字速度  ${settings.textSpeed.toInt()} 字/秒", color = TextSub, fontSize = 13.sp)
            Slider(
                value = settings.textSpeed.coerceIn(0f, 120f),
                onValueChange = { onChange(settings.copy(textSpeed = it)) },
                valueRange = 0f..120f,
            )
            Spacer(Modifier.height(6.dp))
            Text("音量  ${(settings.volume * 100).toInt()}%", color = TextSub, fontSize = 13.sp)
            Slider(
                value = settings.volume,
                onValueChange = { onChange(settings.copy(volume = it)) },
                valueRange = 0f..1f,
            )
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                TinyBtn(if (settings.fullscreen) "全屏：开" else "全屏：关") {
                    val v = !settings.fullscreen
                    setFullscreen(v)
                    onChange(settings.copy(fullscreen = v))
                }
                Spacer(Modifier.width(12.dp))
                Text(platformName, color = TextSub, fontSize = 12.sp)
            }
            Spacer(Modifier.height(18.dp))
            BigBtn("关闭") { onClose() }
        }
    }
}

@Composable
private fun SaveOverlay(
    engine: NarrativeEngine,
    loadMode: Boolean,
    onPick: (Int) -> Unit,
    onClose: () -> Unit,
) {
    Scrim {
        Panel(if (loadMode) "读 档" else "存 档", 640) {
            Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                for (slot in 0 until SaveStore.SLOTS) {
                    val info = remember(slot, loadMode) { SaveStore.info(slot) }
                    val label = if (slot == SaveStore.AUTO) "自动存档" else "存档 $slot"
                    Surface(
                        color = PanelHi,
                        border = BorderStroke(1.dp, LineCol),
                        shape = RoundedCornerShape(2.dp),
                        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
                            .clickable { onPick(slot) },
                    ) {
                        Column(Modifier.padding(12.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(label, color = Accent, fontSize = 13.sp)
                                Spacer(Modifier.width(10.dp))
                                Text(
                                    if (info.exists) info.time else "空",
                                    color = TextSub, fontSize = 12.sp,
                                )
                            }
                            Text(
                                if (info.exists) info.preview else "———",
                                color = TextMain, fontSize = 13.sp,
                                modifier = Modifier.padding(top = 4.dp),
                            )
                        }
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
            BigBtn("返回") { onClose() }
        }
    }
}

@Composable
private fun GalleryOverlay(root: String, spec: NarrativeSpec, onClose: () -> Unit) {
    val images = remember(spec) {
        (spec.lines.flatMap { it.images } + spec.lines.flatMap { l -> l.steps.flatMap { it.images } }).distinct()
    }
    Scrim {
        Panel("CG 鉴 赏", 820) {
            if (images.isEmpty()) {
                Text("这个故事还没有剧照。", color = TextSub, fontSize = 13.sp)
            } else {
                Column(Modifier.heightIn(max = 460.dp).verticalScroll(rememberScrollState())) {
                    images.forEach { img ->
                        Box(Modifier.fillMaxWidth().padding(bottom = 10.dp)) {
                            StoryImage(root, img, Modifier.fillMaxWidth().heightIn(max = 300.dp), ContentScale.Fit)
                        }
                    }
                }
            }
            Spacer(Modifier.height(14.dp))
            BigBtn("关闭") { onClose() }
        }
    }
}
