package com.dick.plugins

/** 界面插件：主题与强调色（在 设置 → 插件区 操作） */
class UiPlugin : Plugin {
    override val name = "界面"
    override val version = "1.0"
    override val description = "主题（深色/浅色/OLED）与强调色"
    override var enabled = true
}
