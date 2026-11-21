package com.dick.app

import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import kotlinx.coroutines.withTimeoutOrNull

/**
 * 点按 / 长按（**1 秒**）二选一的手势。
 *
 * 为什么不用 `combinedClickable`：它固定用系统的 `ViewConfiguration.longPressTimeout`
 * （AOSP 约 500ms），改不了时长；而列表卡片"稍微按久一点就被判成长按"很恼人 ——
 * 用户明确要求 1 秒。
 *
 * 实现只用挂起函数（`withTimeoutOrNull` + `waitForUpOrCancellation`），不依赖外部 CoroutineScope：
 * 超时前抬手 = 点按；超时 = 长按，之后把抬手事件吃掉，避免再补一次点击。
 *
 * 只有安卓端用：桌面网页走自己的按钮入口，不参与这套手势。
 */
fun Modifier.tapOrLongPress(
    longPressMs: Long = 1000L,
    onTap: () -> Unit,
    onLongPress: () -> Unit,
): Modifier = pointerInput(longPressMs) {
    awaitEachGesture {
        awaitFirstDown(requireUnconsumed = false)
        val releasedInTime = withTimeoutOrNull(longPressMs) {
            waitForUpOrCancellation()          // 1 秒内抬手 → 拿到抬手事件
        }
        if (releasedInTime != null) {
            onTap()
        } else {
            onLongPress()                       // 超时 = 长按
            waitForUpOrCancellation()           // 吃掉长按之后的抬手
        }
    }
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌