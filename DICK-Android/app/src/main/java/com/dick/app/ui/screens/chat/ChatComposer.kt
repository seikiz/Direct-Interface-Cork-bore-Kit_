package com.dick.app

// 从 ChatScreen.kt 拆出的输<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌入栏（状态全部走参数，内部不碰外层变量）

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
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
) {
                    Row(Modifier.fillMaxWidth()) {
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
                        Button(onClick = onSend, enabled = !busy) { Text(I18n.t("btn_send", "发送")) }
                    }
}
