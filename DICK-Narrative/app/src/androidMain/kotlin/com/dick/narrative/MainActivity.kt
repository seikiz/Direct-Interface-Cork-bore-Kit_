package com.dick.narrative

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.dick.narrative.engine.DemoStory
import com.dick.narrative.engine.NarrativeSpec
import com.dick.narrative.engine.SpecParser
import com.dick.narrative.platform.AndroidPlatform
import com.dick.narrative.platform.appDataDir
import com.dick.narrative.platform.joinPath
import com.dick.narrative.platform.readText
import com.dick.narrative.ui.NarrTheme
import com.dick.narrative.ui.NarrativePlayer

/**
 * 安卓入口 —— 同一个引擎、同一个界面。
 * 故事来源：应用私有目录下的 story.json / codex.json，或打包进 assets 的同名文件；
 * 都没有就用内置示例。
 */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AndroidPlatform.context = applicationContext
        val spec = loadSpec()
        setContent {
            NarrTheme {
                NarrativePlayer(
                    root = appDataDir(),
                    spec = spec,
                    onQuit = { finish() },
                )
            }
        }
    }
}

private fun loadSpec(): NarrativeSpec {
    val root = appDataDir()
    listOf("story.json", "codex.json").forEach { name ->
        val t = readText(joinPath(root, name)) ?: readText(name)
        if (!t.isNullOrBlank()) {
            return try {
                SpecParser.parse(t)
            } catch (e: Exception) {
                NarrativeSpec(name = "故事文件解析失败", intro = e.message.orEmpty())
            }
        }
    }
    return DemoStory.spec
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌