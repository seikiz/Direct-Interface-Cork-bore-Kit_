package com.dick.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 卡面查看（把角色卡面 HTML 渲染进 WebView）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `CardFaceDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[CardFaceDialog]（在 Dialogs.kt 末尾），转调 [CardFaceScreen]。
 */
/** 卡面查看（<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌角色卡面可视化） */
@Composable
fun CardFaceScreen(vm: ChatViewModel, muted: Color) {
    if (vm.showCardFace.value) {
        val role = vm.selectedRoles.value.firstOrNull()
        val html = role?.let { vm.advancedByRole[it]?.fields?.get("card_face")?.str() } ?: ""
        AlertDialog(
            onDismissRequest = { vm.showCardFace.value = false },
            title = { IconText("卡面", icon = "style") },
            text = {
                if (html.isNotBlank()) {
                    HtmlCard(html, Modifier.fillMaxWidth().height(420.dp))
                } else {
                    Column(Modifier.padding(8.dp)) {
                        Text("该角色未设置卡面。", fontSize = 13.sp, color = muted)
                        Text("在「角色 → 编辑 → 开发者模式 → 卡面」导入 HTML 或自行编辑。", fontSize = 12.sp, color = muted)
                    }
                }
            },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { vm.showCardFace.value = false }) { Text(I18n.t("btn_cancel", "取消")) } },
        )
    }
}
