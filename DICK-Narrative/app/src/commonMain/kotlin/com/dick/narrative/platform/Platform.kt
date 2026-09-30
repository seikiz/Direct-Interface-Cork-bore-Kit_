package com.dick.narrative.platform

import androidx.compose.ui.graphics.ImageBitmap

/*
 * 平台层：所有「桌面/手机不一样」的事都收在这里。
 * 引擎与 UI 只调用这些函数，因此同一份故事在 EXE 和 APK 上表现一致。
 */

/** 读文件字节；不存在或失败返回 null */
expect fun readBytes(path: String): ByteArray?

/** 写文本（UTF-8）；自动建父目录。成功返回 true */
expect fun writeText(path: String, text: String): Boolean

/** 读文本；不存在或失败返回 null */
expect fun readText(path: String): String?

/** 列目录内的文件名（不含路径）；失败返回空表 */
expect fun listNames(dir: String): List<String>

/** 路径拼接（自动选分隔符） */
expect fun joinPath(vararg parts: String): String

/** 解码图片；失败返回 null */
expect fun decodeImage(bytes: ByteArray): ImageBitmap?

/** 可写目录：存档、设置放这里 */
expect fun appDataDir(): String

/** 故事根目录（用户把故事包放这儿） */
expect fun appBaseDir(): String

/** 当前时间文本（存档用） */
expect fun nowText(): String

/** 平台名，界面右下角显示用 */
expect val platformName: String

// ---- 音频（v1：桌面支持 WAV，手机走 Medi<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌aPlayer 支持 mp3/ogg/wav） ----

/** 播放一个音频文件；loop=true 时循环 */
expect fun playAudio(path: String, loop: Boolean, volume: Float)

/** 停止某个音频 */
expect fun stopAudio(path: String)

/** 全部停止（退出/读档时用） */
expect fun stopAllAudio()

/** 全屏切换（移动端为空实现） */
expect fun setFullscreen(on: Boolean)
