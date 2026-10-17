package com.dick.core

import java.io.File

/** 数据根目录：Android 下由 UI 注入 c<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ontext.filesDir；测试时可改指向临时目录 */
object AppEnv {
    @Volatile
    var dataRoot: File = File(System.getProperty("user.dir"))

    fun dir(name: String): File = File(dataRoot, name).apply { mkdirs() }

    fun savesDir(): File = dir("saves")
    fun worldsDir(): File = dir("worlds")
    /** 世界卡包库（与 WorldPacks.DIRNAME 同一个目录；工坊下载/上传卡包都落这里） */
    fun worldPacksDir(): File = dir(WorldPacks.DIRNAME)
    fun memoryDir(): File = dir("memory")
    fun mechStateDir(): File = dir("mech_state")  // 第三个文件夹：机制状态实时 JSON（不依赖树快照）
    fun dbFile(): File = File(dataRoot, "policy_db.json")
    fun configFile(): File = File(dataRoot, "config.json")
}
