package com.dick.core

import java.io.File

/** 数据根目录：Android 下由 UI 注入 context.filesDir；测试时可改指向临时目录 */
object AppEnv {
    @Volatile
    var dataRoot: File = File(System.getProperty("user.dir"))

    fun dir(name: String): File = File(dataRoot, name).apply { mkdirs() }

    fun savesDir(): File = dir("saves")
    fun worldsDir(): File = dir("worlds")
    fun memoryDir(): File = dir("memory")
    fun mechStateDir(): File = dir("mech_state")  // 第三个文件夹：机制状态实时 JSON（不依赖树快照）
    fun dbFile(): File = File(dataRoot, "policy_db.json")
    fun configFile(): File = File(dataRoot, "config.json")
}
