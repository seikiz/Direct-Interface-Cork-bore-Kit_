package com.dick.app

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue

/**
 * SettingsState —— 设置屏的**屏内瞬态**。
 *
 * 硬边界（这一条是"状态收口"的落地口径）：
 *   · 只放「离开这一屏就没有意义」的东西：展开/折叠、输入缓冲、滚动位置；
 *   · 跨屏要用的偏好（主题/强调色/预设/语言/去 AI 味/风格闸/自动接话/开发者模式）
 *     **一律在 ChatViewModel** —— 屏不许自己留副本，否则两份迟早不同步；
 *   · 这里的东西不许被别的屏读。
 *
 * 原来这些是 SettingsDialog 里的 `remember { mutableStateOf(...) }`，
 * 搬到类里之后寿命由调用点决定（`rememberSettingsState()` 放在弹窗打开的分支里，
 * 所以仍然是"关掉就重置"，和搬家前一模一样）。
 */
class SettingsState {
    /** 「 插件」这一段是不是展开<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌的（默认收起 —— 与搬家前一致） */
    var foldPlugins by mutableStateOf(false)

    /** 「高级设置」折叠区（2026-12 文案清理）：替换规则 / 温度 / top_p 收进去，默认收起。
     *  字段一个都没删，只是"进阶项不再挡在首屏上、也不再各带一句说明"。 */
    var foldAdv by mutableStateOf(false)

    // ---- 「向导」的三格瞬态（2026-11）----
    // 为什么放这里：离开 API 弹窗就没意义 → 屏内瞬态，不进 ChatViewModel。
    /** 向导当前步：0 选服务商 / 1 填 Key / 2 测试并保存 */
    var apiStep by mutableStateOf(0)
    /** 正在测试（真连一次 /models）—— 按钮要禁用，防连点 */
    var apiTesting by mutableStateOf(false)
    /** 测试结果/提示那一行（'' = 还没测） */
    var apiTestLine by mutableStateOf("")
}

/** 跟着「设置弹窗打开」这一段的组合走：弹窗关掉，屏内瞬态一起丢。 */
@Composable
fun rememberSettingsState(): SettingsState = remember { SettingsState() }
