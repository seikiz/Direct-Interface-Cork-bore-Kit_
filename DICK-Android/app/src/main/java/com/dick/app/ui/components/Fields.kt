package com.dick.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 输入框 + label（DICK 的唯一文本输入出口）。
 *
 * 为什么把它单独抽出来：设置屏有 15 个输入框、工坊有 2 个，原来每处都手写一遍
 * `OutlinedTextField(value, onValueChange, label = { Text(...) }, singleLine = ...)`。
 * label 里的 emoji 该不该换图标、字号该多大这类事，散在十几处就一定会漂。
 *
 * 两种形态，按"提示是标签还是说明"选：
 *   · [DickField]        —— 提示就是这一格的**名字**，走 Material 的浮动 label（工坊、对话类表单）；
 *   · [DickLabeledField] —— label 画在**框上方**，说明画在**框下方灰色小字**。
 *     为什么要有第二种：把"温度（留空=默认）"整句塞进框里，输入的内容会被那句说明挤得没地方，
 *     读起来像占位符在跟你抢位置（用户截图里的原话是"影响观感"）。说明归说明，值归值。
 *
 * 契约：只吃参数（值 + 回调 + 文案 + 说明），不读 vm、不发请求、不改行为。
 */
@Composable
fun DickField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    singleLine: Boolean = false,
    minLines: Int = 1,
    enabled: Boolean = true,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { IconText(label, iconSize = 14.dp) },
        modifier = modifier,
        singleLine = singleLine,
        minLines = minLines,
        enabled = enabled,
    )
}

/**
 * 框上方小号 label + 输入框 +（可选）框下方灰色说明。
 *
 * 设置屏统一用这个：同一个屏里"框内浮动 label"和"框外 label"混着用，会比文案不一致还难看。
 * `hint` 为空就不画那一行 —— 不留空行，免得每格高度不一致。
 */
@Composable
fun DickLabeledField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    hint: String? = null,
    singleLine: Boolean = false,
    minLines: Int = 1,
    enabled: Boolean = true,
) {
    Column(modifier) {
        Text(label, fontSize = 12.sp, color = DickTone.Muted.color())
        Spacer(Modifier.height(2.dp))
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier.fillMaxWidth(),
            singleLine = singleLine,
            minLines = minLines,
            enabled = enabled,
        )
        if (hint != null) {
            Spacer(Modifier.height(2.dp))
            Text(hint, fontSize = 11.sp, color = DickTone.Dim.color())
        }
    }
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌