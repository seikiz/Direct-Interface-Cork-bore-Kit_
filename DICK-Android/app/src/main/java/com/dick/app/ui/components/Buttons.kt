package com.dick.app

import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 按钮（DICK 设计系统的唯一按钮出口）。
 *
 * 契约（与 web/UI_ARCHITECTURE.md「组件契约」同一条规矩）：
 *   · **只吃参数**：不读 ChatViewModel、不读 App() 闭包、不知道自己在哪一屏；
 *   · **事件往外抛**：点击只通过 onClick 回调，组件自己不调后端、不改状态；
 *   · **观感由变体决定**，三档，语义固定（别再按"看着顺眼"挑）：
 *
 * | variant | 长相 | 什么时候用 | 例子 |
 * | --- | --- | --- | --- |
 * | Primary | 实心 | **当前值 / 主操作**（点一下换下一个值也算，因为那是"当前选择就在这儿"） | 主题：浅色 / 预设：默认 / 保存 |
 * | Secondary | 描边 | **次级入口**（进另一个面板、开系统相册） | 时间流速 / 壁纸 / 玩家角色卡 |
 * | Plain | 纯文字 | **行内轻动作**（对话框的取消、± 计数、列表项里的动作） | 取消 / − / 去官网注册 |
 *
 * 想改"所有按钮"的样子：改这一个文件。想改"某一屏的按钮层级"：改变体，不许复制粘贴。
 */

/** 按钮三档（语<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌义见文件头表格）。 */
enum class DickButtonVariant { Primary, Secondary, Plain }

/**
 * 三档按钮的**唯一实现**。
 * `fontSize` 不传 = Material3 默认字级；`color` 只影响文字/图标（描边与实心底色仍由 Material3 给）。
 */
@Composable
fun DickActionButton(
    label: String,
    onClick: () -> Unit,
    variant: DickButtonVariant = DickButtonVariant.Plain,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    fontSize: TextUnit = TextUnit.Unspecified,
    color: Color = Color.Unspecified,
) {
    when (variant) {
        DickButtonVariant.Primary -> Button(onClick = onClick, modifier = modifier, enabled = enabled) {
            IconText(label, fontSize = fontSize, color = color)
        }
        DickButtonVariant.Secondary -> OutlinedButton(onClick = onClick, modifier = modifier, enabled = enabled) {
            IconText(label, fontSize = fontSize, color = color)
        }
        DickButtonVariant.Plain -> TextButton(onClick = onClick, modifier = modifier, enabled = enabled) {
            IconText(label, fontSize = fontSize, color = color)
        }
    }
}

/** 实心按钮（Primary）。 */
@Composable
fun DickButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    fontSize: TextUnit = TextUnit.Unspecified,
) {
    DickActionButton(label, onClick, DickButtonVariant.Primary, modifier, enabled, fontSize)
}

/** 文字按钮（Plain）：对话框的确定/取消、列表行里的轻动作。 */
@Composable
fun DickTextButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    fontSize: TextUnit = TextUnit.Unspecified,
    color: Color = Color.Unspecified,
) {
    DickActionButton(label, onClick, DickButtonVariant.Plain, modifier, enabled, fontSize, color)
}

/** 描边按钮（Secondary）：设置页里"打开另一个面板/相册"那类入口。 */
@Composable
fun DickOutlinedButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    fontSize: TextUnit = TextUnit.Unspecified,
) {
    DickActionButton(label, onClick, DickButtonVariant.Secondary, modifier, enabled, fontSize)
}

/**
 * 图标按钮：内容是**单个图标/字形**的 TextButton（不是 IconButton —— 图标按钮在这里
 * 指的是「只有图标没有文字」，触控高度仍走 TextButton 的默认值，别换成更小的盒子）。
 */
@Composable
fun DickIconButton(
    icon: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    fontSize: TextUnit = 12.sp,
    iconSize: Dp = 16.dp,
    tint: Color = Color.Unspecified,
) {
    TextButton(onClick = onClick, modifier = modifier, enabled = enabled) {
        IconText(icon, fontSize = fontSize, color = tint, iconSize = iconSize)
    }
}
