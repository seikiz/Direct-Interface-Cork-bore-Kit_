package com.dick.app

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
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
        Text(title, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.weight(1f))
        Text(if (folded) "▸" else "▾", fontSize = 12.sp, color = Color(0xFF94A3B8))
    }
}
