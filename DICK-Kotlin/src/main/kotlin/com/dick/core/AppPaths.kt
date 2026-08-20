package com.dick.core

import java.io.File

/**
 * 便携路径：数据全部跟随程序目录（与 Python app_paths 同设计）。
 * 覆盖方式：JVM 参数 -Ddick.home=路径 指向任意数据根目录（可与 Python 版共用）。
 */
object AppPaths {
    val baseDir: File by lazy {
        File(System.getProperty("dick.home") ?: System.getProperty("user.dir"))
    }

    fun dataDir(name: String): File = File(baseDir, name).apply { mkdirs() }

    fun configFile(): File = File(baseDir, "config.json")
    fun savesDir(): File = dataDir("saves")
    fun worldsDir(): File = dataDir("worlds")
    fun personasDir(): File = dataDir("personas")
    fun presetsDir(): File = dataDir("prompt_presets")
    fun pluginsDir(): File = dataDir("plugins")
    fun exportsDir(): File = dataDir("exports")
}
