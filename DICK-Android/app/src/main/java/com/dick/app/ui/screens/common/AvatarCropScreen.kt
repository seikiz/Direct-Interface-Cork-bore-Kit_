package com.dick.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.AppEnv
import java.io.File

/**
 * 头像交互式裁剪（Canvas 绘制，显示与裁剪同一套数学）。
 *
 * 纯结构搬家（2026-11 UI 解耦第二批）：正文从 Dialogs.kt 的 `AvatarCropDialog` 逐字搬过来，
 * 只换「代码住在哪个文件」。布局数值/文案/交互顺序一个都没动（观感守恒）。
 *
 * 硬边界：
 *   · 状态只从 ChatViewModel 读；不读别的屏的内部字段（跨屏走 vm 的开关/回调）；
 *   · 对外依赖仍走 DialogDeps（下一步按 settings/workshop 的样子收窄成 `<Feature>Actions`）；
 *   · 控件优先用 ui/components/ 的 Dick*（还没换过来的，等这一屏下一次动的时候顺手换）。
 *
 * 兼容门面：[AvatarCropDialog]（在 Dialogs.kt 末尾），转调 [AvatarCropScreen]。
 */
/** 头像交互式裁剪（Canvas 绘制：显示与裁剪同一套数学） */
@Composable
fun AvatarCropScreen(vm: ChatViewModel, deps: DialogDeps) {
    val theme = deps.theme
    // 裁剪台/遮罩/框线都是「恒定角色」（design/tokens.json 的 stage / scrim_soft / stage_line，
    // 三套主题同值）。它们仍然不随主题变，但不再是屏里的野生 hex。
    val pal = theme.palette
    val cropBitmap = vm.cropBitmap
    val avatarTarget = vm.avatarTarget
    var cropScale by vm.cropScale
    var cropDx by vm.cropDx
    var cropDy by vm.cropDy
    var cropStagePx by vm.cropStagePx
    if (cropBitmap.value != null && avatarTarget.value != null) {
        val bmp = cropBitmap.value!!
        DickDialog(
            onDismissRequest = { vm.cropBitmap.value = null; vm.avatarTarget.value = null },
            title = { IconText("裁剪头像", icon = "content_cut") },
            text = {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Box(
                        modifier = Modifier
                            .size(280.dp)
                            .clip(RoundedCornerShape(12.dp))
                            // 裁剪台底板与遮罩走令牌里的恒定角色（stage / scrim_soft / stage_line）<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌：这里要的是"照片外面那圈中性黑"，
                            // 跟主题深浅无关（浅色主题下变白会让裁剪边界糊掉），所以令牌里给的是**恒定值**：
                            // 三套主题同色 —— 「不进令牌」和「不随主题变」是两件事，前者才是硬编码。
                            .background(pal.stage)
                            .onSizeChanged { cropStagePx = it.width.toFloat() }
                            .pointerInput(bmp) {
                                detectTransformGestures { _, pan, zoom, _ ->
                                    cropScale = (cropScale * zoom).coerceIn(0.4f, 6f)
                                    cropDx += pan.x
                                    cropDy += pan.y
                                }
                            }
                    ) {
                        Canvas(modifier = Modifier.fillMaxSize()) {
                            val s = size.width
                            val baseFit = minOf(s / bmp.width, s / bmp.height)
                            val dispW = bmp.width * baseFit * cropScale
                            val dispH = bmp.height * baseFit * cropScale
                            val imgLeft = (s - bmp.width * baseFit) / 2f + cropDx
                            val imgTop = (s - bmp.height * baseFit) / 2f + cropDy
                            drawImage(
                                image = bmp.asImageBitmap(),
                                dstSize = IntSize(dispW.toInt(), dispH.toInt()),
                                dstOffset = IntOffset(imgLeft.toInt(), imgTop.toInt())
                            )
                            val inset = s * 0.23f
                            drawRect(pal.scrimSoft, topLeft = Offset(0f, 0f), size = Size(s, inset))
                            drawRect(pal.scrimSoft, topLeft = Offset(0f, s - inset), size = Size(s, inset))
                            drawRect(pal.scrimSoft, topLeft = Offset(0f, inset), size = Size(inset, s - inset * 2))
                            drawRect(pal.scrimSoft, topLeft = Offset(s - inset, inset), size = Size(inset, s - inset * 2))
                            drawRect(pal.stageLine, topLeft = Offset(inset, inset),
                                size = Size(s - inset * 2, s - inset * 2),
                                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 6f))
                        }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
                        IconText("", fontSize = 12.sp, icon = "search")
                        Slider(
                            value = cropScale,
                            onValueChange = { cropScale = it },
                            valueRange = 0.4f..6f,
                            modifier = Modifier.weight(1f).padding(horizontal = 4.dp)
                        )
                        IconText("", fontSize = 16.sp, icon = "search")
                    }
                    Text("拖动调整位置 · 双指/滑条缩放（0.4x 焦距拉远 ~ 6x 放大）", fontSize = 11.sp, color = theme.muted)
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    try {
                        val b = vm.cropBitmap.value ?: return@TextButton
                        val t = vm.avatarTarget.value ?: return@TextButton
                        val s = cropStagePx
                        val out = android.graphics.Bitmap.createBitmap(256, 256, android.graphics.Bitmap.Config.ARGB_8888)
                        val cvs = android.graphics.Canvas(out)
                        var drew = false
                        if (s > 4f && b.width > 0 && b.height > 0) {
                            val baseFit = minOf(s / b.width, s / b.height)
                            val dispW = b.width * baseFit * cropScale
                            val dispH = b.height * baseFit * cropScale
                            val imgLeft = (s - b.width * baseFit) / 2f + cropDx
                            val imgTop = (s - b.height * baseFit) / 2f + cropDy
                            val inset = s * 0.23f
                            val sqSize = s - inset * 2
                            val srcX = (inset - imgLeft) / dispW * b.width
                            val srcY = (inset - imgTop) / dispH * b.height
                            val srcSize = sqSize / dispW * b.width
                            val sx = srcX.coerceIn(0f, b.width.toFloat())
                            val sy = srcY.coerceIn(0f, b.height.toFloat())
                            val ss = srcSize.coerceAtMost(b.width - sx).coerceAtMost(b.height - sy)
                            if (ss > 4f) {
                                val srcRect = android.graphics.Rect(sx.toInt(), sy.toInt(), (sx + ss).toInt(), (sy + ss).toInt())
                                cvs.drawBitmap(b, srcRect, android.graphics.Rect(0, 0, 256, 256), null)
                                drew = true
                            }
                        }
                        if (!drew) {
                            val side = minOf(b.width, b.height)
                            val fx = (b.width - side) / 2
                            val fy = (b.height - side) / 2
                            cvs.drawBitmap(b, android.graphics.Rect(fx, fy, fx + side, fy + side),
                                android.graphics.Rect(0, 0, 256, 256), null)
                        }
                        val bos = java.io.ByteArrayOutputStream()
                        out.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, bos)
                        val dir = File(AppEnv.savesDir(), "avatars").apply { mkdirs() }
                        File(dir, t + ".png").writeBytes(bos.toByteArray())
                        vm.avatarCache.remove(t)
                    } catch (_: Exception) {
                    }
                    vm.cropBitmap.value = null
                    vm.avatarTarget.value = null
                }) { IconText("确认", icon = "check_circle") }
            },
            dismissButton = { TextButton(onClick = { vm.cropBitmap.value = null; vm.avatarTarget.value = null }) { Text("取消") } },
        )
    }
}
