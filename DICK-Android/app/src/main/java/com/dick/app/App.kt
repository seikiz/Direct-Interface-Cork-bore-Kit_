package com.dick.app

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.Composable
import androidx.lifecycle.viewmodel.compose.viewModel

/**
 * App —— 应用入口（**只有入口**）。
 *
 * 2026-11 UI 解耦之后这里只剩三件事：
 *   ① 取 ChatViewModel（唯一状态源）；
 *   ② 解析当前主题（主题序号在 vm 里，系统深浅在这里读一次，口径与 DickTheme 一致）；
 *   ③ 把屏交出去 —— 聊天主屏在 ui/screens/chat/ChatScreen.kt，
 *      其余 overlay 屏在 ui/screens/<feature>/，由 nav/Routes.kt 的 OverlayHost 统一挂载。
 *
 * 为什么 `DickTheme` **必须**在这层（2026-12 改）：搬家前它只包住抽屉，弹窗画在主题外层，
 * 于是弹窗里 `MaterialTheme.colorScheme` 是 M3 **默认浅色**（AlertDialog 取 surfaceContainerHigh
 * = 淡紫），`LocalContentColor` 是**纯黑** —— 深色主题下就是「弹窗白得像硬编码 + 卡片标题发暗」
 * 两张截图。现在整个 App 都在 DickTheme 里：令牌与 MaterialTheme 覆盖所有弹窗/抽屉/对话框。
 * 弹窗壳另外再显式给色（见 ui/components/DialogShell.kt），两层保险，任一层被绕过都不会露白。
 *
 * 加一屏请**不要**改这个文件：去 ui/screens/<feature>/ 建屏，再在 nav/Routes.kt 注册一行。
 */
@Composable
fun App() {
    val vm: ChatViewModel = viewModel()
    // 主题解析：「跟随系统」这一项在这里按系统深浅落<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌到暗/浅（与 DickTheme 同一个口径，
    // 所以 ChatScreen 拿到的就是实际生效的那套色，不必等 MaterialTheme 生效）
    val theme = resolveTheme(vm.themeIdx.value, isSystemInDarkTheme())
    // 强调色也分暗/浅两版：浅色主题下 #60a5fa 当文字色只有 2.5:1（见 design/tokens.json）
    val accent = accentFor(vm.accentIdx.value, theme.mode == DickThemeMode.Light)
    // 整个 App（含所有 overlay 弹窗）都在主题里：弹窗不再落回 M3 默认淡紫/黑字。
    DickTheme(mode = theme.mode, accentIdx = vm.accentIdx.value) {
        ChatScreen(vm, theme, accent)
    }
}
