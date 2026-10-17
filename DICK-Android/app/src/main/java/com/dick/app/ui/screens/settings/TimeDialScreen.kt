package com.dick.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.LocalContentColor
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.TimeScale

/**
 * 时间流速表盘（对数刻度 + 触点换算）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `TimeScalePanel` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[TimeScalePanel]（在 Dialogs.kt 末尾），转调 [TimeDialScreen]。
 */
/** 设置（API 配置 + 主设置） */
/**
 * ⏳ 时间流速表盘（手机端）。
 *
 * 为什么用对数刻度：10 ~ 1000万 跨 6 个数量级。线性表盘 98% 的行程都挤在
 * 最前几档上，手指一动就是几百万倍，根本没法用。对数下每转一格 = ×10，
 * 而人对量级的感知本来也是对数的。
 *
 * 表盘用 240° 弧（不是整圆）：底下留缺口，手指从缺口那边进来不会误触。
 * 换算逻辑全部走 TimeScale，和 PC 端同一套参数。
 */
@Composable
fun TimeScaleDial(
    current: Double,
    accent: Color,
    dialSize: Dp = 240.dp,
    // 默认跟随环境内容色，而不是写死白 —— 写死白<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌的后果是浅色主题下白字浅底（"字不是反色"）。
    // 调用方仍可显式传主题色（面板就是传 ThemeSpec.text / muted）。
    textColor: Color = LocalContentColor.current,
    subColor: Color = LocalContentColor.current.copy(alpha = 0.62f),
    onChange: (Double) -> Unit,
) {
    // 颜色由调用方传入（这个项目没有全局主题对象，DialogDeps.theme / accent 是约定）
    val textCol = textColor
    val subCol = subColor
    val lineCol = accent.copy(alpha = 0.28f)
    var draft by remember { mutableStateOf(current) }
    LaunchedEffect(current) { draft = current }

    // 弧的起止角（度）：-210° 到 30°，共 240°
    val a0 = -210.0
    val a1 = 30.0

    // 几何按画布尺寸算【比例】，不再写死像素（原来是 r=100px / cy=118px，而外框是 dp）：
    // 高密度屏上圆盘只占框的一小块、还偏上 —— 展开成面板后这个毛病会更显眼。
    fun geom(w: Float, h: Float): Triple<Float, Float, Float> =
        Triple(w / 2f, h * 0.52f, minOf(w, h) * 0.38f)

    fun pt(t: Double, radius: Float, cx: Float, cy: Float): Pair<Float, Float> {
        val a = (a0 + (a1 - a0) * t) * Math.PI / 180.0
        val c = Math.cos(a).toFloat()
        val s = Math.sin(a).toFloat()
        return Pair(cx + radius * c, cy + radius * s)
    }

    Column(Modifier.fillMaxWidth()) {
        Box(
            Modifier.fillMaxWidth().height(dialSize),
            contentAlignment = Alignment.Center,
        ) {
            Canvas(
                Modifier
                    .fillMaxWidth()
                    .height(210.dp)
                    .pointerInput(Unit) {
                        // 拖拽过程中只改本地 draft（只重组表盘本身），
                        // 松手才 onChange 提交 —— 每帧都写 VM 状态会触发
                        // 整棵界面树重组，老手机上会明显卡（第一版就这么写的）。
                        detectDragGestures(
                            onDragStart = { off ->
                                val (cx, cy, _) = geom(size.width.toFloat(), size.height.toFloat())
                                draft = scaleFromXY(off.x, off.y, cx, cy, a0, a1)
                            },
                            onDrag = { change, _ ->
                                val (cx, cy, _) = geom(size.width.toFloat(), size.height.toFloat())
                                draft = scaleFromXY(change.position.x, change.position.y, cx, cy, a0, a1)
                            },
                            onDragEnd = { onChange(draft) },
                            onDragCancel = { draft = current },
                        )
                    }
                    .pointerInput(Unit) {
                        detectTapGestures { off ->
                            val (cx, cy, _) = geom(size.width.toFloat(), size.height.toFloat())
                            draft = scaleFromXY(off.x, off.y, cx, cy, a0, a1)
                            onChange(draft)
                        }
                    },
            ) {
                val (cx, cy, r) = geom(size.width, size.height)
                val t = TimeScale.posOf(draft)
                val arcW = r * 0.10f          // 线宽/刻度全部按半径取比例，放大缩小都不走形

                // 底弧
                drawArc(
                    color = lineCol,
                    startAngle = a0.toFloat(),
                    sweepAngle = (a1 - a0).toFloat(),
                    useCenter = false,
                    topLeft = Offset(cx - r, cy - r),
                    size = Size(r * 2f, r * 2f),
                    style = Stroke(width = arcW, cap = StrokeCap.Round),
                )
                // 进度弧
                drawArc(
                    color = accent,
                    startAngle = a0.toFloat(),
                    sweepAngle = ((a1 - a0) * t).toFloat(),
                    useCenter = false,
                    topLeft = Offset(cx - r, cy - r),
                    size = Size(r * 2f, r * 2f),
                    style = Stroke(width = arcW, cap = StrokeCap.Round),
                )
                // 刻度
                for (p in TimeScale.PRESETS) {
                    val tp = TimeScale.posOf(p.first)
                    val i0 = pt(tp, r - r * 0.17f, cx, cy)
                    val i1 = pt(tp, r + r * 0.09f, cx, cy)
                    drawLine(
                        color = subCol,
                        start = Offset(i0.first, i0.second),
                        end = Offset(i1.first, i1.second),
                        strokeWidth = r * 0.022f,
                    )
                }
                // 指针
                val tip = pt(t, r, cx, cy)
                drawLine(
                    color = textCol,
                    start = Offset(cx, cy),
                    end = Offset(tip.first, tip.second),
                    strokeWidth = r * 0.032f,
                    cap = StrokeCap.Round,
                )
                drawCircle(color = accent, radius = r * 0.070f, center = Offset(tip.first, tip.second))
                drawCircle(color = textCol, radius = r * 0.078f, center = Offset(cx, cy))
            }
            // 中央读数（叠在 Canvas 上，用文字排版更省事）
            // 偏移量跟着 dialSize 走 —— 原来写死 44dp，表盘一改尺寸读数就不在盘面里了
            Column(
                Modifier.align(Alignment.Center).offset(y = dialSize * 0.21f),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text(
                    TimeScale.describe(draft).substringBefore(" · ").replace("倍", "") + "×",
                    fontSize = 22.sp, color = textCol, fontWeight = FontWeight.Bold,
                )
                Text(TimeScale.perRoundText(draft), fontSize = 11.sp, color = subCol)
            }
        }
        val preset = TimeScale.presetName(draft)
        Text(
            if (preset != null) preset else "（不在预设档上，也可以直接用）",
            fontSize = 11.sp, color = subCol,
        )
        Spacer(Modifier.height(4.dp))
        // 预设按钮：不想拖也可以点
        FlowRowSimple(TimeScale.PRESETS) { mul, name ->
            TextButton(onClick = { draft = mul; onChange(mul) }) {
                Text(TimeScale.perRoundText(mul).replace("一轮约 ", ""), fontSize = 11.sp)
            }
        }
        if (draft >= 3600) {
            IconText(
                "⚠ 高倍率下时间过得极快：现实几分钟就等于她那边好几天。适合「跳过一段时间」的玩法。",
                fontSize = 11.sp, color = subCol, iconSize = 12.dp,
            )
        }
    }
}

/**
 * ⏳ 时间流速面板（独立展开）。
 *
 * 为什么从设置弹窗里搬出来：
 *   ① 一块表盘夹在一长串设置项中间，既挤又不像"一个功能"；
 *   ② 表盘用 detectDragGestures，而设置列表是 verticalScroll ——
 *      竖向拖表盘会和页面滚动抢手势（拖到一半页面跟着滚）。
 * 现在设置里只留一行入口，点开就是这块独立面板：表盘更大、读数居中、预设横排。
 * 面板高度按屏幕算，保证里面【不需要滚动容器】→ 抢手势的问题从根上没有了。
 */
@Composable
fun TimeDialScreen(vm: ChatViewModel, deps: DialogDeps) {
    if (!vm.showTimeDial.value) return
    val theme = deps.theme
    // 表盘尺寸跟着屏幕走：矮屏收一点，换"整块面板不用滚动"
    val screenH = LocalConfiguration.current.screenHeightDp
    val dialSize = (screenH * 0.36f).coerceIn(190f, 300f).dp
    val close = { vm.showTimeDial.value = false }

    Dialog(
        onDismissRequest = close,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(0.94f),
            shape = RoundedCornerShape(16.dp),
            color = theme.bg,
        ) {
            Column(Modifier.padding(horizontal = 18.dp, vertical = 14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconText("⏳ 时间流速", fontSize = 15.sp, color = theme.text, fontWeight = FontWeight.SemiBold, iconSize = 16.dp)
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = close) { Text("关闭", color = theme.muted, fontSize = 13.sp) }
                }
                Text(
                    "世界那边过得比现实快多少倍。倍率越高，一段时间没说话她那边过得越久；" +
                        "刻度是对数的（每格 ×10）。拖表盘、点指针或点下方预设都行。",
                    fontSize = 11.sp, color = theme.muted, lineHeight = 15.sp,
                )
                Spacer(Modifier.height(6.dp))
                TimeScaleDial(
                    current = vm.timeScale.value,
                    accent = deps.accent,
                    dialSize = dialSize,
                    textColor = theme.text,
                    subColor = theme.muted,
                    onChange = {
                        vm.timeScale.value = it
                        // 必须同步进 TimeScale.current —— 引擎组装载荷时（TimeContext）
                        // 读的是它，不同步的话拨了表盘也不生效。
                        TimeScale.current = it
                    },
                )
            }
        }
    }
}

/** 极简流式布局：预设按钮不多，够用就行 */
@Composable
private fun FlowRowSimple(
    items: List<Pair<Double, String>>,
    content: @Composable (Double, String) -> Unit,
) {
    Column {
        var i = 0
        while (i < items.size) {
            Row {
                for (j in i until minOf(i + 4, items.size)) {
                    content(items[j].first, items[j].second)
                }
            }
            i += 4
        }
    }
}

/** 触点角度 → 倍率。角度归一到 [a0, a1] 再反查对数刻度。 */
private fun scaleFromXY(x: Float, y: Float, cx: Float, cy: Float, a0: Double, a1: Double): Double {
    val ang = Math.toDegrees(Math.atan2((y - cy).toDouble(), (x - cx).toDouble()))
    var a = ang
    while (a < a0) a += 360.0
    val t = ((a - a0) / (a1 - a0)).coerceIn(0.0, 1.0)
    return TimeScale.scaleAt(t)
}
