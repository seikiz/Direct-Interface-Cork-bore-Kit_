package com.dick.app

// 从 ChatScreen.kt 拆出的输<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌入栏（状态全部走参数，内部不碰外层变量）

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
internal fun ChatComposer(
    input: String,
    onInput: (String) -> Unit,
    busy: Boolean,
    showQuickPanel: Boolean,
    onToggleQuick: () -> Unit,
    onSend: () -> Unit,
    hasImage: Boolean = false,
    onStop: (() -> Unit)? = null,
) {
                    val canSend = !busy && (input.isNotBlank() || hasImage)
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { onToggleQuick() }) {
                            // 快捷面板开/关：图标名跟着状态走（原来是  /  两个 emoji）
                            IconText("", fontSize = 20.sp, icon = if (showQuickPanel) "close" else "add")
                        }
                        OutlinedTextField(
                            value = input,
                            onValueChange = onInput,
                            label = { Text(I18n.t("input_label", "输入消息（/ 开头为命令）")) },
                            modifier = Modifier.weight(1f),
                            maxLines = 4,
                        )
                        Spacer(Modifier.width(6.dp))
                        if (busy && onStop != null) {
                            OutlinedButton(onClick = onStop) { Text(I18n.t("btn_stop", "停止")) }
                        } else {
                            Button(onClick = onSend, enabled = canSend) { Text(I18n.t("btn_send", "发送")) }
                        }
                    }
}
