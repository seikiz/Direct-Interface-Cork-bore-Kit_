package com.dick.app

// 从 ChatScreen 抽出的 overlay <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌/ 对话框簇（导航壳 + 引导 + 清空历史确认）
import androidx.compose.runtime.Composable

@Composable
internal fun ChatOverlays(
    st: ChatState,
    theme: ThemeSpec,
    deps: DialogDeps,
    showGuide: Boolean,
    guideStep: Int,
    showClearHistory: Boolean,
    onStep: (Int) -> Unit,
    onCloseGuide: () -> Unit,
    onDismissClear: () -> Unit,
    onConfirmClear: (Boolean) -> Unit,
) {
// 首次启动引导框

// ---------- 所有 overlay 屏（导航壳） ----------
// App() 从这里之后**不认识任何一个具体屏**：谁在屏幕上、什么顺序，全在 nav/Routes.kt。
// 搬家前这里是 14 行平铺的 `XxxDialog(vm, deps)` —— 那种写法谁都能顺手插一行，
// 结果就是"屏与屏互相点名"。加一屏请去 Routes 里加。

ChatGuideDialog(
    showGuide = showGuide, guideStep = guideStep, theme = theme,
    onStep = onStep, onClose = onCloseGuide,
)

ChatClearHistoryDialog(
    show = showClearHistory, theme = theme, cardLabel = st.currentCardLabel(),
    onDismiss = onDismissClear,
    onConfirm = onConfirmClear,
)

OverlayHost(
    vm = st.vm,
    deps = deps,
    muted = theme.muted,
    danger = theme.danger,
    onDeleteRole = { n -> st.deleteRole(n) },
    onDeleteWorld = { n -> st.deleteWorld(n) },
)

// ---------- 彻底清空历史（红色 · 二次确认） ----------
}
