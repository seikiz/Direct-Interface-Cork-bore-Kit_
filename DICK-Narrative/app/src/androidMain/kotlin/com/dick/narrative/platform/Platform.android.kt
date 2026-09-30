package com.dick.narrative.platform

import android.content.Context
import android.graphics.BitmapFactory
import android.media.MediaPlayer
import android.os.Build
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/*
 * 安卓实现：文件走 java.io + assets 兜底，图片走 BitmapFactory，音频走 MediaPlayer。
 * MainActivity 启动时把 applicationContext 塞进 AndroidPlatform，之后平台函数就能用。
 */

object AndroidPlatform {
    var context: Context? = null
}

private fun ctx(): Context? = AndroidPlatform.context

actual fun readBytes(path: String): ByteArray? {
    try {
        val f = File(path)
        if (f.isFile) return f.readBytes()
    } catch (e: Exception) {
    }
    val c = ctx() ?: return null
    return try {
        c.assets.open(path.trimStart('/')).use { it.readBytes() }
    } catch (e: Exception) {
        null
    }
}

actual fun writeText(path: String, text: String): Boolean = try {
    val f = File(path)
    f.parentFile?.mkdirs()
    f.writeText(text)
    true
} catch (e: Exception) {
    false
}

actual fun readText(path: String): String? = readBytes(path)?.toString(Charsets.UTF_8)

actual fun listNames(dir: String): List<String> = try {
    File(dir).list()?.toList() ?: emptyList()
} catch (e: Exception) {
    emptyList()
}

actual fun joinPath(vararg parts: String): String =
    parts.filter { it.isNotBlank() }.joinToString("/")

actual fun decodeImage(bytes: ByteArray): ImageBitmap? = try {
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap()
} catch (e: Exception) {
    null
}

actual fun appDataDir(): String = ctx()?.filesDir?.absolutePath ?: "/data/local/tmp"

/** 手机上没有「程序目录」概念，故事统一放应用私有目录（也可打包进 assets）。 */
actual fun appBaseDir(): String = appDataDir()

actual fun nowText(): String =
    SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.getDefault()).format(Date())

actual val platformName: String = "安卓版 · API " + Build.VERSION.SDK_INT

// ---------------- 音<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌频 ----------------

private val players = HashMap<String, MediaPlayer>()

actual fun playAudio(path: String, loop: Boolean, volume: Float) {
    try {
        stopAudio(path)
        val mp = MediaPlayer()
        val f = File(path)
        if (f.isFile) {
            mp.setDataSource(f.absolutePath)
        } else {
            val c = ctx() ?: return
            val rel = path.trimStart('/')
            c.assets.openFd(rel).use { afd ->
                mp.setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
            }
        }
        val v = volume.coerceIn(0f, 1f)
        mp.isLooping = loop
        mp.setVolume(v, v)
        mp.prepare()
        mp.start()
        players[path] = mp
    } catch (e: Exception) {
    }
}

actual fun stopAudio(path: String) {
    players.remove(path)?.let {
        try {
            it.stop()
        } catch (e: Exception) {
        }
        it.release()
    }
}

actual fun stopAllAudio() {
    players.values.forEach {
        try {
            it.stop()
        } catch (e: Exception) {
        }
        it.release()
    }
    players.clear()
}

/** 安卓已经在全屏窗口里，由系统栏策略控制，这里不额外处理。 */
actual fun setFullscreen(on: Boolean) {
}
