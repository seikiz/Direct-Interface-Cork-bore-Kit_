package com.dick.app

// 从 ChatScreen.kt 拆出<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌的快捷面板（纯 UI，状态全部走参数）

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.dick.core.AppConfig
import com.dick.core.J

                @Composable
internal fun ChatQuickPanel(
    visible: Boolean,
    theme: ThemeSpec, accent: Color,
    finFolded: Boolean, onToggleFin: () -> Unit,
    financialEnabled: Boolean,
    cardQuickReplies: List<Pair<String, String>>,
    quickReplies: List<Pair<String, String>>,
    onImage: () -> Unit,
    onManualGal: () -> Unit,
    insertCmd: (String) -> Unit,
    onPick: (String) -> Unit,
) {
    if (!visible) return
                    Surface(color = theme.bubble, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                        Column(Modifier.padding(6.dp)) {
                            Row {
                                QuickChip(I18n.t("qc_image", "图片"), icon = "photo_camera") { onImage() }
                                QuickChip("搜索", icon = "search") { insertCmd("/搜索 ") }
                                QuickChip("深搜", icon = "search") { insertCmd("/深搜 ") }
                                QuickChip("骰子", icon = "casino") { insertCmd("/r 2d6") }
                            }
                            Row {
                                QuickChip("记忆", icon = "memory") { insertCmd("/memory recall 3") }
                                QuickChip("选项", icon = "sports_esports") { onManualGal() }
                            }
                            // 财报：折叠区块，仅启用财报模式才显示（隐藏 + 收起，避免铺满面板）
                            if (financialEnabled) {
                                FoldHead("财报", finFolded, onToggleFin, icon = "bar_chart")
                                if (!finFolded) {
                                    Row {
                                        QuickChip("个股", icon = "bar_chart") { insertCmd("/股票 ") }
                                        QuickChip("全市场", icon = "search") { insertCmd("/全市场 ") }
                                        QuickChip("联动", icon = "link") { insertCmd("/联动 ") }
                                        QuickChip("爬政策", icon = "trending_up") { insertCmd("/财报 爬取") }
                                    }
                                    Row {
                                        QuickChip("入库", icon = "menu_book") { insertCmd("/财报 入库") }
                                        QuickChip("检索", icon = "menu_book") { insertCmd("/财报 检索 ") }
                                        QuickChip("爬网页", icon = "language") { insertCmd("/爬取 ") }
                                    }
                                }
                            }
                            Row {
                                // 卡片自带快捷回复（高级设置）优先，再跟全局
                                cardQuickReplies.forEach { (label, t) ->
                                    QuickChip(label) { onPick(t) }
                                }
                                quickReplies.forEach { (label, t) ->
                                    QuickChip(label) { onPick(t) }
                                }
                            }
                        }
                    }
                }
