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
 * 为什么 `DickTheme` 不在这层：搬家前它只包住抽屉、弹窗画在主题外层（见 ChatScreen 顶部注释）。
 * 本轮口径是"只换代码住哪"，所以层级原样保留 —— 挪进来会改弹窗里 Material 控件的配色。
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
    ChatScreen(vm, theme, accent)
}
