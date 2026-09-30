package com.dick.narrative.platform

import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.toComposeImageBitmap
import org.jetbrains.skia.Image
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import javax.sound.sampled.AudioSystem
import javax.sound.sampled.Clip
import javax.sound.sampled.FloatControl

/* 桌面（JVM）实现：文件走 java.io，图片走 skiko，音频走 javax.sound。 */

actual fun readBytes(path: String): ByteArray? = try {
    val f = File(path)
    if (f.isFile) f.readBytes() else null
} catch (e: Exception) {
    null
}

actual fun writeText(path: String, text: String): Boolean = try {
    val f = File(path)
    f.parentFile?.mkdirs()
    f.writeText(text)
    true
} catch (e: Exception) {
    false
}

actual fun readText(path: String): String? = try {
    val f = File(path)
    if (f.isFile) f.readText() else null
} catch (e: Exception) {
    null
}

actual fun listNames(dir: String): List<String> = try {
    File(dir).list()?.toList() ?: emptyList()
} catch (e: Exception) {
    emptyList()
}

actual fun joinPath(vararg parts: String): String =
    parts.filter { it.isNotBlank() }.joinToString(File.separator)

actual fun decodeImage(bytes: ByteArray): ImageBitmap? = try {
    Image.makeFromEncoded(bytes).toComposeImageBitmap()
} catch (e: Exception) {
    null
}

actual fun appDataDir(): String =
    File(System.getProperty("user.home") ?: ".", ".dick-narrative").absolutePath

actual fun appBaseDir(): String {
    System.getenv("DICK_STORY_DIR")?.takeIf { it.isNotBlank() }?.let { return it }
    System.getProperty("jpackage.app-path")?.let { p ->
        File(p).parentFile?.let { return it.absolutePath }
    }
    return File(".").absolutePath
}

actual fun nowText(): String =
    LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))

actual val platformName: String = "桌面版 · " + System.getProperty("os.name").orEmpty()

// ---------------- 音<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌频 ----------------

private val clips = HashMap<String, Clip>()

actual fun playAudio(path: String, loop: Boolean, volume: Float) {
    try {
        val f = File(path)
        if (!f.isFile) return
        clips.remove(path)?.let { old ->
            try {
                old.stop(); old.close()
            } catch (e: Exception) {
            }
        }
        val clip = AudioSystem.getClip()
        AudioSystem.getAudioInputStream(f).use { stream -> clip.open(stream) }
        applyVolume(clip, volume)
        if (loop) clip.loop(Clip.LOOP_CONTINUOUSLY) else clip.start()
        clips[path] = clip
    } catch (e: Exception) {
        // 桌面 v1 只解 WAV/AU/AIFF；mp3/ogg 需要额外解码库，这里静默跳过
    }
}

actual fun stopAudio(path: String) {
    clips.remove(path)?.let {
        try {
            it.stop(); it.close()
        } catch (e: Exception) {
        }
    }
}

actual fun stopAllAudio() {
    clips.values.forEach {
        try {
            it.stop(); it.close()
        } catch (e: Exception) {
        }
    }
    clips.clear()
}

private fun applyVolume(clip: Clip, volume: Float) {
    try {
        val c = clip.getControl(FloatControl.Type.MASTER_GAIN) as? FloatControl ?: return
        val v = volume.coerceIn(0f, 1f)
        val db = if (v <= 0.0001f) -80.0 else 20.0 * Math.log10(v.toDouble())
        c.value = db.toFloat().coerceIn(c.minimum, c.maximum)
    } catch (e: Exception) {
    }
}

// ---------------- 全屏 ----------------

actual fun setFullscreen(on: Boolean) {
    try {
        val win = java.awt.Window.getWindows()
            .filterIsInstance<java.awt.Frame>()
            .firstOrNull { it.isVisible } ?: return
        val device = win.graphicsConfiguration?.device ?: return
        device.fullScreenWindow = if (on) win else null
    } catch (e: Exception) {
    }
}
