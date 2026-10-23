package com.dick.app

// 从 ChatScreen.kt 拆出的两个<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌对话框（全是参数 + 回调，不碰外层状态）

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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

@Composable
internal fun ChatGuideDialog(
    showGuide: Boolean, guideStep: Int, theme: ThemeSpec,
    onStep: (Int) -> Unit, onClose: () -> Unit,
) {
        if (showGuide) {
            // 幕布走令牌（theme.palette.scrim = 80% 近黑石板）：原来这里是字面量 0xCC0A0C10。
            // 令牌值就是那个字面量（换算回去逐位相同），所以观感不变；
            // 但从此改幕布只需改 design/tokens.json，屏里再也拼不出野生 hex。
            Box(Modifier.fillMaxSize().background(theme.palette.scrim).clickable { }, contentAlignment = Alignment.Center) {
                Surface(
                    modifier = Modifier.fillMaxWidth().padding(22.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = theme.bubble,
                    shadowElevation = 12.dp,
                ) {
                    // 三步引导：每条 = (图标名, 标题, 说明)。图标名走 IconText 的 icon 参数，
                    // 标题只留纯文本（文案里不再有 emoji 字符）。
                    val guide = listOf(
                        Triple("waving_hand", "欢迎使用 DICK", "装好即聊的角色扮演聊天室：手机 / 电脑进度互通，支持角色卡、世界书、回档、内置游戏。"),
                        Triple("settings", "配置模型", "设置 → 填 API Key、选模型商（DeepSeek 官方 / 免费链 / Ollama 本地）。免 Key 的免费链直接就能聊。"),
                        Triple("theater_comedy", "选择角色", "角色列表勾选即可开聊（多选 = 群聊，@角色名 指定发言）；可新建或导入酒馆卡 v1/v2/v3/PNG。"),
                        Triple("chat", "开聊", "输入消息发送；↻ 重生成、◀▶ 滑条、编辑。面板有骰子 / 记忆 / GAL 选项 / 快捷回复。"),
                        Triple("account_tree", "进阶玩法", "回档：主线平铺、分支收纳；GAL 选项点选即演；世界书平行世界；存档自动守护。"),
                    )
                    Column(Modifier.padding(20.dp)) {
                        IconText(guide[guideStep].second, fontSize = 18.sp, fontWeight = FontWeight.Bold, iconSize = 20.dp,
                            icon = guide[guideStep].first)
                        Spacer(Modifier.height(10.dp))
                        Text(guide[guideStep].third, fontSize = 13.sp, lineHeight = 22.sp)
                        Spacer(Modifier.height(16.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            TextButton(onClick = { onClose() }) { Text("跳过", fontSize = 13.sp) }
                            Spacer(Modifier.weight(1f))
                            if (guideStep > 0) {
                                TextButton(onClick = { onStep(guideStep - 1) }) { Text("上一步", fontSize = 13.sp) }
                            }
                            Button(onClick = {
                                if (guideStep >= guide.size - 1) { onClose() }
                                else onStep(guideStep + 1)
                            }) { IconText(if (guideStep >= guide.size - 1) "开始使用" else "下一步", fontSize = 13.sp, iconSize = 14.dp) }
                        }
                    }
                }
            }
        }
}

@Composable
internal fun ChatClearHistoryDialog(
    show: Boolean, theme: ThemeSpec, cardLabel: String,
    onDismiss: () -> Unit, onConfirm: (Boolean) -> Unit,
) {
        if (show) {
            var alsoClearMemory by remember { mutableStateOf(false) }
            DickDialog(
                onDismissRequest = { onDismiss() },
                title = { IconText("彻底清空历史", color = theme.danger, icon = "warning") },
                text = {
                    Column {
                        Text("将删除当前角色「" + cardLabel + "」的全部聊天记录。")
                        Spacer(Modifier.height(6.dp))
                        Text("此操作不可恢复。确定要清空吗？", fontSize = 12.sp, color = theme.muted)
                        Text("（机制卡的状态/好感度也会一起重置。）", fontSize = 11.sp, color = theme.muted)
                        Spacer(Modifier.height(8.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = alsoClearMemory, onCheckedChange = { alsoClearMemory = it })
                            Text("同时清空记忆链（memory）", fontSize = 12.sp, modifier = Modifier.padding(top = 14.dp))
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = {
                        onConfirm(alsoClearMemory)
                        onDismiss()
                    }) { IconText("彻底清空", color = theme.danger, icon = "delete") }
                },
                dismissButton = { TextButton(onClick = { onDismiss() }) { Text("取消") } },
            )
        }
}
