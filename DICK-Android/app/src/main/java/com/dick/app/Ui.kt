package com.dick.app

import android.graphics.BitmapFactory
import android.speech.tts.TextToSpeech
import android.webkit.WebView
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
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 把字符串开头的 emoji 前缀提取出来，返回 (去 FE0F 的 emoji, 剩余文本)。无 emoji 时返回 (null, 原串)。 */
private val EMOJI_PREFIX = Regex("^(?:[\\uD83C-\\uDBFF][\\uDC00-\\uDFFF]|[\\u2600-\\u27BF\\u2B00-\\u2BFF\\uFE0F\\u200D\\u20E3])+")
fun splitLeadingEmoji(s: String): Pair<String?, String> {
    val m = EMOJI_PREFIX.find(s) ?: return null to s
    return m.value.replace("\uFE0F", "") to s.removePrefix(m.value)
}
/** emoji → 黑白线性图标 drawable（与 Web 端同一套设计，stroke currentColor → 由 tint 控制颜色） */
private val EMOJI_RES: Map<String, Int> = mapOf(
    "📂" to R.drawable.ic_folder,
    "🛰" to R.drawable.ic_radio,
    "➕" to R.drawable.ic_plus,
    "❌" to R.drawable.ic_close,
    "⚙" to R.drawable.ic_settings,
    "✅" to R.drawable.ic_check,
    "🧰" to R.drawable.ic_toolbox,
    "📤" to R.drawable.ic_upload,
    "🗑" to R.drawable.ic_trash,
    "🔑" to R.drawable.ic_key,
    "⚠" to R.drawable.ic_warn,
    "🌍" to R.drawable.ic_globe,
    "🌐" to R.drawable.ic_globe,
    "💾" to R.drawable.ic_save,
    "🧮" to R.drawable.ic_calc,
    "🔤" to R.drawable.ic_font,
    "🔌" to R.drawable.ic_plug,
    "🔍" to R.drawable.ic_search,
    "⬇" to R.drawable.ic_download,
    "📥" to R.drawable.ic_inbox,
    "❤" to R.drawable.ic_heart,
    "🤖" to R.drawable.ic_robot,
    "✨" to R.drawable.ic_sparkle,
    "🔥" to R.drawable.ic_flame,
    "🎭" to R.drawable.ic_users,
    "🧑" to R.drawable.ic_person,
    "👤" to R.drawable.ic_person,
    "📷" to R.drawable.ic_camera,
    "🔗" to R.drawable.ic_link,
    "📄" to R.drawable.ic_doc,
    "🧹" to R.drawable.ic_clear,
    "🎨" to R.drawable.ic_droplet,
    "✏" to R.drawable.ic_edit,
    "📚" to R.drawable.ic_book,
    "🌿" to R.drawable.ic_branch,
    "📊" to R.drawable.ic_chart,
    "📈" to R.drawable.ic_trend,
    "🎲" to R.drawable.ic_dice,
    "🧠" to R.drawable.ic_chip,
    "🎮" to R.drawable.ic_gamepad,
    "✂" to R.drawable.ic_scissors,
    "🔄" to R.drawable.ic_refresh,
    "🖼" to R.drawable.ic_image,
    "🚀" to R.drawable.ic_rocket,
    "🔧" to R.drawable.ic_wrench,
    "👋" to R.drawable.ic_wave,
    "💬" to R.drawable.ic_chat,
    "🎯" to R.drawable.ic_target,
    "🎛" to R.drawable.ic_sliders,
    "🎬" to R.drawable.ic_clapper,
    "⚔" to R.drawable.ic_swords,
    "⚡" to R.drawable.ic_bolt,
    "🧍" to R.drawable.ic_person_stand,
    "💘" to R.drawable.ic_heart_arrow,
)
/**
 * 渲染 UI 框架标签：开头的 emoji 自动换成黑白线性图标（颜色跟随 color / LocalContentColor），
 * 其余文本照常显示。找不到对应图标的 emoji（如聊天内容）原样保留。
 */
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
    val res = emoji?.let { EMOJI_RES[it] } ?: 0
    if (res == 0) {
        Text(text, modifier = modifier, fontSize = fontSize, fontWeight = fontWeight, color = color, maxLines = maxLines)
    } else {
        val tint = if (color == Color.Unspecified) LocalContentColor.current else color
        Row(modifier = modifier, verticalAlignment = Alignment.CenterVertically) {
            Icon(
                painterResource(res), null,
                modifier = Modifier.size(iconSize),
                tint = tint,
            )
            if (rest.isNotBlank()) {
                Spacer(Modifier.width(gap))
                Text(rest, fontSize = fontSize, fontWeight = fontWeight, color = color, maxLines = maxLines)
            }
        }
    }
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
        Text(if (folded) "▸" else "▾", fontSize = 12.sp, color = Color(0xFF94A3B8))
    }
}
// ---------- 聊天/头像/抽屉 组件（自 App.kt 拆出） ----------
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
    val nameColor = if (isUser) Color(0xFF4ADE80) else aiColor
    val displayRole = when (m.role) {
        "你" -> I18n.t("you", "你")
        "系统" -> I18n.t("system", "系统")
        else -> m.role
    }
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
        ) {
            if (!isUser) Avatar(displayRole, avatarCache)
            Spacer(Modifier.width(6.dp))
            Column(horizontalAlignment = if (isUser) Alignment.End else Alignment.Start) {
                Text(displayRole, color = nameColor, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = bubbleBg,
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
            Row(
                Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(start = 44.dp),
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
                            color = Color(0xFF9CA3AF),
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
