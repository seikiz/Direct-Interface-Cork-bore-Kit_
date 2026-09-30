package com.dick.narrative

import androidx.compose.runtime.remember
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import com.dick.narrative.engine.DemoStory
import com.dick.narrative.engine.NarrativeSpec
import com.dick.narrative.engine.SpecParser
import com.dick.narrative.platform.joinPath
import com.dick.narrative.platform.readText
import com.dick.narrative.ui.NarrativePlayer
import com.dick.narrative.ui.NarrTheme
import java.io.File

/**
 * 桌面入口 —— 打包成 EXE 后的主程序。
 *
 * 找故事的顺序（先找到先用）：
 *   1. 环境变量 DICK_STORY_DIR 指向的目录
 *   2. exe 同级目录（jpackage 打包后就是这个）
 *   3. 当前工作目录
 * 每个位置都依次试：目录本身是故事包 → 目录下的 story/ 或 data/ → story/<包名>/
 * （GAL制作器「导出到播放器」生成的就是 story/<包名>/codex.json 这个结构。）
 * 一个都找不到就播内置示例《钟楼之下》，保证程序永远打得开。
 */
fun main() = application {
    val spec = remember { loadSpec() }
    val windowState = rememberWindowState(size = DpSize(1280.dp, 720.dp))

    Window(
        onCloseRequest = ::exitApplication,
        title = spec.name,
        state = windowState,
    ) {
        NarrTheme {
            NarrativePlayer(root = StoryRoot, spec = spec, onQuit = { exitApplication() })
        }
    }
}

private val STORY_NAMES = listOf("codex.json", "story.json")

/** 故事目录 + 文件名；找不到返回 null */
private val Found: Pair<String, String>? by lazy { findStory() }
private val StoryRoot: String by lazy { Found?.first ?: File(".").absolutePath }

private fun findStory(): Pair<String, String>? {
    val bases = ArrayList<String>()
    System.getenv("DICK_STORY_DIR")?.takeIf { it.isNotBlank() }?.let { bases.add(it) }
    System.getProperty("jpackage.app-path")?.let { p ->
        File(p).parentFile?.let { bases.add(it.absolutePath) }
    }
    bases.add(File(".").absolutePath)

    for (base in bases) {
        probe(base)?.let { return it }
        for (sub in listOf("story", "data")) {
            val d = File(base, sub)
            probe(d.absolutePath)?.let { return it }
            // story/<包名><seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌/codex.json
            val pkgs = d.listFiles()?.filter { it.isDirectory }?.sortedBy { it.name } ?: emptyList()
            for (pkg in pkgs) {
                probe(pkg.absolutePath)?.let { return it }
            }
        }
    }
    return null
}

private fun probe(dir: String): Pair<String, String>? {
    for (n in STORY_NAMES) {
        if (File(dir, n).isFile) return dir to n
    }
    return null
}

private fun loadSpec(): NarrativeSpec {
    val found = Found ?: return DemoStory.spec
    val text = readText(joinPath(found.first, found.second))
    if (text.isNullOrBlank()) return DemoStory.spec
    return try {
        SpecParser.parse(text)
    } catch (e: Exception) {
        NarrativeSpec(name = "故事文件解析失败", intro = e.message.orEmpty())
    }
}
