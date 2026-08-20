package com.dick.core

import java.io.File

/** 存档读写：saves 目录下的 .json，与 Python 版完全互通 */
object TreeStore {
    fun load(file: File): SaveFile = try {
        val root = JsonS.parse(file.readText(Charsets.UTF_8))
        (root as? J.Obj)?.let { SaveFile.fromJson(it) } ?: SaveFile()
    } catch (_: Exception) {
        SaveFile()
    }

    fun save(file: File, save: SaveFile) {
        try {
            file.parentFile?.mkdirs()
            file.writeText(JsonS.stringify(save.toJson(), pretty = true), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }
}
