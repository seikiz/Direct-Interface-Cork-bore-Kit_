package com.dick.core

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineName
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/**
 * Lanes —— 模块分道执行（手机端）
 *
 * 与电脑端 `jobs.py` 同一套想法：**一个模块一条运行线**，同线保序、跨线并行。
 *
 * 为什么手机端也要它（实测 2026-10）：
 *   App.kt 里到处是 `scope.launch(Dispatchers.IO) { …; launch(Main) { 更新界面 } }`，
 *   每次各 launch 各自的协程，于是没有并发控制、没有顺序保证、出问题也看不到"现在在跑什么"。
 *   更要紧的是**保序类的活儿**：`landAssistantReply` 在**主线程**上做
 *   `mech.persistState()` 与 `saveTree()`（整棵树序列化 + 写盘），还顺手 new 了个裸 Thread。
 *
 * 用法：
 *   Lanes.on(Lanes.io, "存档落盘") { TreeStore.save(path, snapshot) }
 *   Lanes.on(Lanes.net, "推工坊同步") { Workshop.pushSave(cardId, json) }
 *   Lanes.status()      // 每线在跑什么 / 完成数 / 失败数
 *
 * 并发约定（与 jobs.py 一致）：
 *   io / vision / plugin = 1（保序或独占设备）　net = 4（请求彼此独立）
 *   只留四条**真在用**的线：记忆链的落盘在 plugin 线上，内存归档不需要单独一条；
 *   TTS 只能在主线程发起，所以没有 voice 线（宁可没有，也不留没人用的空线）。
 *
 * 现在 `App.kt` 里已经没有裸 `Thread { }` 了 —— 探测 Ollama、拉服务器树、拉共享连接配置、
 * 图片理解，全都挂在线上：谁在跑、跑了几次、失败几次，`Lanes.status()` 一读就知道。
 */
object Lanes {

    private const val NET_PARALLELISM = 4
    private val job = SupervisorJob()

    @OptIn(ExperimentalCoroutinesApi::class)
    private fun lane(name: String, parallelism: Int): CoroutineScope =
        CoroutineScope(Dispatchers.IO.limitedParallelism(parallelism) + job + CoroutineName("lane-$name"))

    /** 落盘 / 导出：串行（同<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌一个文件不能被两个协程同时写） */
    val io: CoroutineScope by lazy { lane("io", 1) }

    /** 图片理解：串行（免费视觉链自己有速率限制，别自己给自己叠并发） */
    val vision: CoroutineScope by lazy { lane("vision", 1) }

    /** 插件钩子：串行（同一插件要先看到前一条回复）—— 记忆链的落盘也在这条线上 */
    val plugin: CoroutineScope by lazy { lane("plugin", 1) }

    /** 网络（工坊 / 搜索 / 下载）：可并行 */
    val net: CoroutineScope by lazy { lane("net", NET_PARALLELISM) }

    private val running = ConcurrentHashMap<String, String>()
    private val doneCount = ConcurrentHashMap<String, AtomicInteger>()
    private val failCount = ConcurrentHashMap<String, AtomicInteger>()

    private val all: List<Pair<String, CoroutineScope>>
        get() = listOf("io" to io, "vision" to vision, "plugin" to plugin, "net" to net)

    /** 投一个任务到指定线：带任务名（状态可见），失败不会拖垮这条线 */
    fun on(scope: CoroutineScope, name: String, block: suspend () -> Unit) {
        val lane = all.firstOrNull { it.second === scope }?.first ?: "other"
        val key = "$lane:$name"
        scope.launch {
            running[key] = name
            try {
                block()
                doneCount.getOrPut(lane) { AtomicInteger() }.incrementAndGet()
            } catch (t: Throwable) {
                failCount.getOrPut(lane) { AtomicInteger() }.incrementAndGet()
                println("[Lanes:$lane] $name 失败：${t.message}")
            } finally {
                running.remove(key)
            }
        }
    }

    /** 状态快照：每线在跑什么 + 完成/失败计数（给设置页或日志用） */
    fun status(): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for ((lane, _) in all) {
            val cur = running.entries.filter { it.key.startsWith("$lane:") }.map { it.value }
            out[lane] = "跑：" + (if (cur.isEmpty()) "-" else cur.joinToString("、")) +
                "　完成 " + (doneCount[lane]?.get() ?: 0) +
                "　失败 " + (failCount[lane]?.get() ?: 0)
        }
        return out
    }

    /** 运行中的任务名（调试用） */
    fun busyNames(): List<String> = running.values.toList()
}

/** 让"用哪条线"在调用点读起来更直白：`Lanes.io.runLane("存档落盘") { … }` */
fun CoroutineScope.runLane(name: String, block: suspend () -> Unit) = Lanes.on(this, name, block)
