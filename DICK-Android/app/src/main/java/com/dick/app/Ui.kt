package com.dick.app

import android.graphics.BitmapFactory
import android.speech.tts.TextToSpeech
import android.webkit.WebView
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.TextButton
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.viewinterop.AndroidView
import com.dick.core.AppEnv
import java.io.File
import java.util.Locale
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.text.InlineTextContent
import androidx.compose.foundation.text.appendInlineContent
import androidx.compose.runtime.remember
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.Placeholder
import androidx.compose.ui.text.PlaceholderVerticalAlign
import androidx.compose.ui.text.buildAnnotatedString

/** 把字符串开头的 emoji 前缀提取出来，返回 (去 FE0F 的 emoji, 剩余文本)。无 emoji 时返回 (null, 原串)。
 *  范围与 Web 端 web/index.html 的 _EMOJI_CLS 保持一致：2300-23FF（⏳⏸⏭⏩）与
 *  2190-21FF（↪）以前漏了，导致「⏳ 生成中」这类状态提示在手机上一直是彩色 emoji。 */
private val EMOJI_PREFIX = Regex("^(?:[\\uD83C-\\uDBFF][\\uDC00-\\uDFFF]|[\\u2600-\\u27BF\\u2B00-\\u2BFF\\u2300-\\u23FF\\u2190-\\u21FF\\uFE0F\\u200D\\u20E3])+")
fun splitLeadingEmoji(s: String): Pair<String?, String> {
    val m = EMOJI_PREFIX.find(s) ?: return null to s
    return m.value.replace("\uFE0F", "") to s.removePrefix(m.value)
}
/** 排版符号（箭头/星号等）：这些交给字体渲染更稳，和 Web 端那套「不替换」名单一个口径。 */
private val TYPO_GLYPHS = setOf("→", "←", "↑", "↓", "↔", "↻", "◀", "▶", "▸", "▾", "★", "☆", "·")
/** 任意位置的 emoji（范围与 EMOJI_PREFIX 一致，这里用来找【句中】的图标） */
private val EMOJI_ANY = Regex("[\\uD83C-\\uDBFF][\\uDC00-\\uDFFF]|[\\u2600-\\u27BF\\u2B00-\\u2BFF\\u2300-\\u23FF\\u2190-\\u21FF\\u20E3]")
/** 切成 (emoji | null, 文本) 段：emoji 段画成图标，文本段原样保留。 */
private fun splitEmojiSegments(s: String): List<Pair<String?, String>> {
    val out = mutableListOf<Pair<String?, String>>()
    var last = 0
    for (m in EMOJI_ANY.findAll(s)) {
        val e = m.value.replace("\uFE0F", "")
        if (e in TYPO_GLYPHS || ICON_NAME_BY_EMOJI[e] == null) continue
        if (m.range.first > last) out.add(null to s.substring(last, m.range.first))
        out.add(e to "")
        last = m.range.last + 1
    }
    if (out.isEmpty()) return listOf(null to s)
    if (last < s.length) out.add(null to s.substring(last))
    return out
}
/**
 * 渲染 UI 框架标签：emoji 自动换成黑白线性图标（颜色跟随 color / LocalContentColor）。
 *   · 行首只有一个图标 → 走 Row（和以前完全一样，不动那三百多处已有排版）
 *   · 句中也有图标 → 走 AnnotatedString + InlineTextContent（长文案照常折行）
 *   · 查不到图标的 emoji（聊天内容、排版符号）原样保留
 */
/** Material Symbols 字体（随包，Apache-2.0；与网页端同一份字形，见 icons/icons.json）。
 *  图标名到字形的映射由 tools/gen_icons.py 生成到 IconNames.kt。 */
val MaterialSymbols = FontFamily(Font(R.font.material_symbols_outlined))

/** 画一个图标（字形来自 Material Symbols）：颜色跟随 tint，缺失字形时原样显示名字。
 *  字号用 TextUnit —— 这样跟旁边的文字一起随字号缩放（原来用 Dp 会不跟手）。 */
@Composable
fun MsIcon(
    name: String,
    size: TextUnit = 16.sp,
    tint: Color = LocalContentColor.current,
    modifier: Modifier = Modifier,
    contentDescription: String? = null,
) {
    val m = if (contentDescription == null) modifier
    else modifier.semantics { this.contentDescription = contentDescription }
    Text(
        name, modifier = m, fontFamily = MaterialSymbols, fontSize = size, color = tint,
        maxLines = 1, softWrap = false,
    )
}
@Composable
fun IconText(
    text: String,
    modifier: Modifier = Modifier,
    fontSize: TextUnit = TextUnit.Unspecified,
    fontWeight: FontWeight? = null,
    color: Color = Color.Unspecified,
    iconSize: Dp = 16.dp,
    gap: Dp = 3.dp,
    maxLines: Int = Int.MAX_VALUE,
) {
    val (emoji, rest) = splitLeadingEmoji(text)
    val iconName = emoji?.let { ICON_NAME_BY_EMOJI[it] }
    val tint = if (color == Color.Unspecified) LocalContentColor.current else color
    val segments = remember(text) { splitEmojiSegments(text) }
    val nameSp = with(LocalDensity.current) { iconSize.toSp() }
    if (!segments.any { it.first != null }) {
        if (iconName == null) {
            Text(text, modifier = modifier, fontSize = fontSize, fontWeight = fontWeight, color = color, maxLines = maxLines)
        } else {
            Row(modifier = modifier, verticalAlignment = Alignment.CenterVertically) {
                MsIcon(iconName, nameSp, tint)
                if (rest.isNotBlank()) {
                    Spacer(Modifier.width(gap))
                    Text(rest, fontSize = fontSize, fontWeight = fontWeight, color = color, maxLines = maxLines)
                }
            }
        }
        return
    }
    // Placeholder 的宽高要 TextUnit（随字号缩放），所以把 Dp 换一下
    val iconSp = nameSp
    val providers = remember(segments, iconSp, tint) {
        segments.mapNotNull { it.first }.distinct().associateWith { e ->
            InlineTextContent(Placeholder(iconSp, iconSp, PlaceholderVerticalAlign.Center)) {
                MsIcon(ICON_NAME_BY_EMOJI.getValue(e), iconSp, tint)
            }
        }
    }
    val ann = remember(segments) {
        buildAnnotatedString {
            segments.forEach { (e, t) -> if (e == null) append(t) else appendInlineContent(e, e) }
        }
    }
    Text(
        ann,
        modifier = modifier,
        fontSize = fontSize,
        fontWeight = fontWeight,
        color = color,
        maxLines = maxLines,
        inlineContent = providers,
    )
}
/** 可折叠区块标题行（▸/▾ 指示，点击切换） */
@Composable
fun FoldHead(title: String, folded: Boolean, onToggle: () -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.fillMaxWidth().clickable { onToggle() }.padding(top = 10.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconText(title, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.weight(1f))
        Text(if (folded) "▸" else "▾", fontSize = 12.sp, color = LocalDickPalette.current.textSub)
    }
}
// ---------- 聊天/头像/抽屉 组件（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌自 App.kt 拆出） ----------
fun parseSpeaker(reply: String, roster: Set<String>): Pair<String?, String> {
    val m = Regex("""^[\[【]([^\]】]{1,30})[\]】]\s*[:：]?\s*""", RegexOption.DOT_MATCHES_ALL).find(reply.trim())
    if (m == null) return null to reply
    val name = m.groupValues[1].trim()
    return if (name in roster) name to reply.substring(m.range.last + 1).trim() else null to reply
}
fun speak(tts: TextToSpeech, text: String) {
    try {
        val isJp = text.any { it.code in 0x3040..0x30FF }
        tts.language = if (isJp) Locale.JAPAN else Locale.CHINA
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "dick-tts")
    } catch (_: Exception) {
    }
}

/** 用 inSampleSize 采样解码，把大图限制在 maxDim*2 内，避免大图/照片直接撑爆内存 */
fun decodeSampled(bytes: ByteArray, maxDim: Int): android.graphics.Bitmap? {
    return try {
        val bound = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
        android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bound)
        var sample = 1
        while (bound.outWidth / sample > maxDim * 2 || bound.outHeight / sample > maxDim * 2) sample *= 2
        val o = android.graphics.BitmapFactory.Options().apply { inSampleSize = sample }
        android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
    } catch (_: Exception) { null }
}
fun decodeSampledFile(path: String, maxDim: Int): android.graphics.Bitmap? {
    return try {
        val bound = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
        android.graphics.BitmapFactory.decodeFile(path, bound)
        var sample = 1
        while (bound.outWidth / sample > maxDim * 2 || bound.outHeight / sample > maxDim * 2) sample *= 2
        val o = android.graphics.BitmapFactory.Options().apply { inSampleSize = sample }
        android.graphics.BitmapFactory.decodeFile(path, o)
    } catch (_: Exception) { null }
}

fun loadCustomAvatar(name: String): ImageBitmap? {
    try {
        val base = File(AppEnv.savesDir(), "avatars")
        for (ext in listOf("png", "jpg", "jpeg", "webp")) {
            val f = File(base, name + "." + ext)
            if (f.exists()) {
                val bmp = decodeSampledFile(f.absolutePath, 512)
                if (bmp != null) return bmp.asImageBitmap()
            }
        }
    } catch (_: Exception) {
    }
    return null
}
@Composable
fun Avatar(name: String, cache: MutableMap<String, ImageBitmap?>) {
    var bmp = cache[name]
    if (bmp == null && !cache.containsKey(name)) {
        bmp = loadCustomAvatar(name)
        cache[name] = bmp
    }
    if (bmp != null) {
        Image(bmp, contentDescription = null, modifier = Modifier.size(36.dp).clip(CircleShape))
    } else {
        Box(
            modifier = Modifier.size(36.dp).clip(CircleShape).background(speakerColor(name)),
            contentAlignment = Alignment.Center,
        ) {
            Text((name.ifBlank { "A" }).first().toString(), color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
        }
    }
}
@Composable
fun Bubble(
    m: ChatMsg,
    bubbleBg: Color,
    bubbleText: Color,
    aiColor: Color,
    avatarCache: MutableMap<String, ImageBitmap?>,
    onEdit: (ChatMsg) -> Unit,
    onRegen: (ChatMsg) -> Unit,
    onSwipe: (ChatMsg, Int) -> Unit,
) {
    val isUser = m.isUser
    val displayRole = when (m.role) {
        "你" -> I18n.t("you", "你")
        "系统" -> I18n.t("system", "系统")
        else -> m.role
    }
    // 名字色跟主题走：暗色用 #4ade80/#94a3b8 那一套，浅色用对应的深色版（见 design/tokens.json）
    val pal = LocalDickPalette.current
    val nameColor = speakerNameColor(displayRole, isUser, aiColor, pal)
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
        ) {
            if (!isUser) Avatar(displayRole, avatarCache)
            Spacer(Modifier.width(6.dp))
            Column(horizontalAlignment = if (isUser) Alignment.End else Alignment.Start) {
                // 署名紧贴气泡上沿（≤4dp）：行高压到 14sp，去掉字体行盒在下方留的那点空 ——
                // 否则署名看起来是"悬"在气泡上方，跟气泡不是一组。
                Text(displayRole, color = nameColor, fontWeight = FontWeight.Bold, fontSize = 12.sp, lineHeight = 14.sp)
                Spacer(Modifier.height(2.dp))
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = bubbleBg,
                    // 自己的气泡加一圈描边：只有 surface_2 那种极淡的填充时，暗色下和页面底色
                    // 几乎分不出来（用户原话"颜色费劲"）。描边用令牌里的 border，不新造颜色。
                    border = if (isUser) BorderStroke(1.dp, pal.border) else null,
                ) {
                    Column(Modifier.padding(10.dp)) {
                        if (m.image != null) {
                            Image(m.image!!, contentDescription = null, modifier = Modifier.size(width = 220.dp, height = 150.dp))
                            Spacer(Modifier.height(6.dp))
                        }
                        Text(m.content, color = bubbleText)
                    }
                }
            }
            if (isUser) {
                Spacer(Modifier.width(6.dp))
                Avatar(displayRole, avatarCache)
            }
        }
        if (m.nodeId != null) {
            // 动作条挂在气泡下面，**和气泡同侧对齐**：自己的消息头像在右边，
            // 所以内边距要留在右边（原来一律 start=44dp，等于把"自己的"动作条推到气泡左边，
            // 看起来就是"错位/被裁"）。
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())
                    .padding(start = if (isUser) 0.dp else 44.dp, end = if (isUser) 44.dp else 0.dp),
                horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
            ) {
                TextButton(onClick = { onEdit(m) }, modifier = Modifier.heightIn(min = 44.dp)) { IconText(I18n.t("btn_edit_msg", "✏️"), fontSize = 12.sp) }
                if (!isUser && m.role != "系统") {
                    if (m.swipeTotal > 1) {
                        TextButton(onClick = { onSwipe(m, -1) }, enabled = m.swipeIndex > 0, modifier = Modifier.heightIn(min = 44.dp)) { Text("◀", fontSize = 12.sp) }
                        Text(
                            (m.swipeIndex + 1).toString() + "/" + m.swipeTotal,
                            Modifier.padding(top = 14.dp),
                            fontSize = 11.sp,
                            color = pal.textDim,
                        )
                        TextButton(onClick = { onSwipe(m, 1) }, enabled = m.swipeIndex < m.swipeTotal - 1, modifier = Modifier.heightIn(min = 44.dp)) { Text("▶", fontSize = 12.sp) }
                    }
                    TextButton(onClick = { onRegen(m) }, modifier = Modifier.heightIn(min = 44.dp)) { Text(I18n.t("btn_regenerate", "↻"), fontSize = 12.sp) }
                }
            }
        }
    }
}
@Composable
fun RowScope.QuickChip(label: String, onClick: () -> Unit) {
    TextButton(onClick = onClick, modifier = Modifier.weight(1f)) {
        IconText(label, fontSize = 11.sp)
    }
}
@Composable
fun DrawerItem(label: String, arrow: Boolean = false, arrowAngle: Float = 0f, color: Color = Color.Unspecified, onClick: () -> Unit) {
    TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        IconText(label, modifier = Modifier.weight(1f), color = color)
        if (arrow) Text("▸", modifier = Modifier.rotate(arrowAngle))
    }
}
/** 卡面：把一段 HTML 渲染成 WebView（角色卡面可视化；非强制） */
@Composable
fun HtmlCard(html: String, modifier: Modifier = Modifier) {
    AndroidView(
        factory = { ctx ->
            WebView(ctx).apply {
                settings.javaScriptEnabled = true
                setBackgroundColor(android.graphics.Color.TRANSPARENT)
                loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
            }
        },
        modifier = modifier,
    )
}
