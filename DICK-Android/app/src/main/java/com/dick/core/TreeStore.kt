package com.dick.core

import java.io.File

/** 存档读写：saves 目录下的 .<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌json，与 Python 版完全互通 */
object TreeStore {
    fun load(file: File): SaveFile = try {
        val root = JsonS.parse(file.readText(Charsets.UTF_8))
        (root as? J.Obj)?.let { SaveFile.fromJson(it) } ?: SaveFile()
    } catch (_: Exception) {
        SaveFile()
    }

    /** 原子落盘：同目录写临时文件 → flush/sync → renameTo 替换，写一半断电/杀后台不损原存档 */
    fun save(file: File, save: SaveFile) {
        val tmp = File(file.parentFile, file.name + ".tmp")
        try {
            file.parentFile?.mkdirs()
            val payload = JsonS.stringify(save.toJson(), pretty = true).toByteArray(Charsets.UTF_8)
            java.io.FileOutputStream(tmp).use { fos ->
                fos.write(payload)
                fos.flush()
                try { fos.fd.sync() } catch (_: Exception) {}
            }
            if (!tmp.renameTo(file)) {
                // 部分 Android 存储卷 renameTo 无法覆盖已存在目标 → 删旧再改名
                if (file.exists()) file.delete()
                if (!tmp.renameTo(file)) {
                    file.writeBytes(payload)
                    tmp.delete()
                }
            }
        } catch (_: Exception) {
            try { if (tmp.exists()) tmp.delete() } catch (_: Exception) {}
        }
    }
}
