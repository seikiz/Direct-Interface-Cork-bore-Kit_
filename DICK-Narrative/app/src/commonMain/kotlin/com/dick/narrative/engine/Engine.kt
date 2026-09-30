package com.dick.narrative.engine

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** 立绘（渲染器画这个） */
data class SpriteView(val file: String, val pos: String = "center")

/** 当前可见选项（index 为可见列表下标，交给 choose(i)） */
data class ChoiceView(val text: String, val index: Int)

/** 回想条目 */
data class BacklogEntry(val speaker: String, val text: String)

/**
 * 叙事引擎 —— 纯 Kotlin，无任何 UI/平台依赖。
 *
 * 职责：读一份 [NarrativeSpec]，按「线 → 点 → 分支」推进，维护 [NarrState]，
 * 并把「当前该画什么」暴露成一组只读属性（帧）。渲染器只读这些属性 + 调
 * [advance] / [choose]，两端（桌面/手机）共用同一套逻辑。
 */
class NarrativeEngine(val spec: NarrativeSpec) {

    val state = NarrState()

    /** 回想（已说过的台词，最新在最后） */
    val backlog: MutableList<BacklogEntry> = mutableListOf()

    var lineId: String = ""
        private set
    var lineTitle: String = ""
        private set
    var ended: Boolean = false
        private set
    var endTitle: String = ""
        private set

    // ---- 当前帧（渲<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌染器只读） ----
    var bg: String = ""
        private set
    var sprites: List<SpriteView> = emptyList()
        private set
    var images: List<String> = emptyList()
        private set
    var speaker: String = ""
        private set
    var text: String = ""
        private set
    var note: String = ""
        private set
    var choices: List<ChoiceView> = emptyList()
        private set

    // ---- 音频 / 特效：tick 变化 = 有新事件要播/要演 ----
    var bgm: String = ""
        private set
    var voice: String = ""
        private set
    var voiceTick: Int = 0
        private set
    var sfx: String = ""
        private set
    var sfxTick: Int = 0
        private set
    var effect: String = ""
        private set
    var effectTick: Int = 0
        private set
    var waitMs: Int = 0
        private set
    var waitTick: Int = 0
        private set

    private var line: Line? = null
    private var index = 0
    private var visibleOptions: List<ChoiceOption> = emptyList()

    fun start(lineId: String? = null) {
        ended = false
        endTitle = ""
        state.affection = 50
        state.status.clear()
        state.flags.clear()
        backlog.clear()
        enter(lineId?.takeIf { it.isNotBlank() } ?: spec.startId)
        run()
    }

    /** 点击推进（当前有选项时不应调用） */
    fun advance() {
        if (ended || choices.isNotEmpty()) return
        run()
    }

    /** 选择第 i 个可见选项 */
    fun choose(i: Int) {
        val opt = visibleOptions.getOrNull(i) ?: return
        choices = emptyList()
        visibleOptions = emptyList()
        index++                       // 离开这个分支点
        if (opt.goto.isNotBlank() && spec.line(opt.goto) != null) enter(opt.goto)
        run()
    }

    // ---------- 存档 ----------

    /**
     * 快照：lineId + 待执行点下标 + 状态 + 当前画面。
     * 因为 run() 在返回前已经把 index 推到「下一个待执行点」，
     * 所以快照本身就是可续跑的：恢复后 advance() 正好接上。
     */
    fun snapshot(): JsonObject = JsonObject(
        mapOf(
            "line" to JsonPrimitive(lineId),
            "index" to JsonPrimitive(index),
            "state" to state.toJson(),
            "bg" to JsonPrimitive(bg),
            "bgm" to JsonPrimitive(bgm),
            "speaker" to JsonPrimitive(speaker),
            "text" to JsonPrimitive(text),
            "note" to JsonPrimitive(note),
            "ended" to JsonPrimitive(ended),
            "endTitle" to JsonPrimitive(endTitle),
            "atChoice" to JsonPrimitive(choices.isNotEmpty()),
            "sprites" to JsonArray(sprites.map {
                JsonObject(mapOf("file" to JsonPrimitive(it.file), "pos" to JsonPrimitive(it.pos)))
            }),
            "images" to JsonArray(images.map { JsonPrimitive(it) }),
        )
    )

    /** 恢复快照。分支帧会按恢复后的状态重算一次选项。 */
    fun restore(o: JsonObject) {
        line = spec.line(o.str("line").orEmpty())
        lineId = line?.id.orEmpty()
        lineTitle = line?.title.orEmpty()
        index = o.int("index") ?: 0

        state.affection = o["state"]?.int("affection") ?: 50
        state.status.clear()
        ((o["state"] as? JsonObject)?.get("status") as? JsonObject)?.forEach { (k, v) ->
            (v as? JsonPrimitive)?.content?.let { state.status[k] = it }
        }
        state.flags.clear()
        ((o["state"] as? JsonObject)?.get("flags") as? JsonObject)?.forEach { (k, v) ->
            state.flags[k] = (v as? JsonPrimitive)?.content == "true"
        }

        bg = o.str("bg").orEmpty()
        bgm = o.str("bgm").orEmpty()
        speaker = o.str("speaker").orEmpty()
        text = o.str("text").orEmpty()
        note = o.str("note").orEmpty()
        endTitle = o.str("endTitle").orEmpty()
        sprites = o.arr("sprites").mapNotNull { s ->
            val f = s.str("file") ?: return@mapNotNull null
            SpriteView(f, s.str("pos") ?: "center")
        }
        images = o.strList("images")

        choices = emptyList()
        visibleOptions = emptyList()

        ended = o.boolOrNull("ended") == true
        if (!ended && o.boolOrNull("atChoice") == true) {
            text = ""
            note = ""
            run()                     // 重算这个分支点当前可见的选项
        }
    }

    // ---------- 内部 ----------

    private fun enter(id: String) {
        line = spec.line(id)
        lineId = line?.id.orEmpty()
        lineTitle = line?.title.orEmpty()
        index = 0
        line?.let { ln ->
            if (ln.images.isNotEmpty()) images = ln.images
            // 线级背景 / 音乐：制作器把这两个字段挂在「线」上，进入这条线就生效
            if (ln.bg.isNotBlank()) bg = ln.bg
            if (ln.bgm.isNotBlank()) bgm = ln.bgm
        }
    }

    private fun finish(title: String) {
        ended = true
        endTitle = title.ifBlank { "完结" }
        text = ""
        note = ""
        choices = emptyList()
        visibleOptions = emptyList()
    }

    /** 推进到下一个「阻塞点」（台词/旁白/选项/结局）为止 */
    private fun run() {
        while (true) {
            if (ended) return
            val ln = line ?: run { finish("完结"); return }

            if (index >= ln.steps.size) {
                val nx = ln.next
                if (nx.isNotBlank() && spec.line(nx) != null) {
                    enter(nx)
                    continue
                }
                finish("完结")
                return
            }

            val step = ln.steps[index]
            if (!Cond.eval(state, step.condition)) {
                index++
                continue
            }

            applyVisuals(step)

            when (step.kind) {
                "say" -> {
                    text = step.text
                    speaker = step.role
                    note = ""
                    if (text.isNotBlank()) backlog.add(BacklogEntry(speaker, text))
                    index++
                    return
                }

                "note" -> {
                    note = step.note
                    text = ""
                    speaker = ""
                    index++
                    return
                }

                "choice" -> {
                    visibleOptions = step.choices.filter { Cond.eval(state, it.condition) }
                    choices = visibleOptions.mapIndexed { i, o -> ChoiceView(o.text, i) }
                    text = ""
                    note = ""
                    if (choices.isEmpty()) {
                        index++          // 没有可见选项 → 这个分支点直接跳过
                        continue
                    }
                    return               // index 停在分支点上，choose() 负责离开
                }

                "end" -> {
                    index++
                    finish(step.endTitle)
                    return
                }

                "jump" -> {
                    if (step.goto.isNotBlank() && spec.line(step.goto) != null) {
                        enter(step.goto)
                        continue
                    }
                    index++
                }

                "setflag" -> {
                    if (step.flagKey.isNotBlank()) state.flags[step.flagKey] = step.flagValue
                    index++
                }

                "wait" -> {
                    if (step.waitMs > 0) {
                        waitMs = step.waitMs
                        waitTick++
                    }
                    index++
                }

                else -> index++   // action / show / hide / bg / bgm / sfx / effect 已在 applyVisuals 生效
            }
        }
    }

    /** 任何点都可能携带的表现副作用（背景/音乐/立绘/图片/语音/音效/特效） */
    private fun applyVisuals(step: Step) {
        val role = spec.role(step.role)

        if (step.bg.isNotBlank()) bg = step.bg
        if (step.bgm.isNotBlank()) bgm = step.bgm

        // 立绘：单张 sprite / 列表 sprites / 角色默认立绘，按优先级兜底
        val list = step.sprites.ifEmpty { listOf(step.sprite) }.filter { it.isNotBlank() }
        val shown = list.ifEmpty {
            listOf(role?.sprite.orEmpty()).filter { it.isNotBlank() }
        }
        if (shown.isNotEmpty()) sprites = shown.map { SpriteView(it, "center") }

        if (step.kind == "hide") sprites = emptyList()

        if (step.images.isNotEmpty()) images = step.images
        else if (step.clearImages) images = emptyList()

        val v = step.voice.ifBlank { role?.voice.orEmpty() }
        if (v.isNotBlank()) {
            voice = v
            voiceTick++
        }
        if (step.sfx.isNotBlank()) {
            sfx = step.sfx
            sfxTick++
        }
        if (step.effect.isNotBlank()) {
            effect = step.effect
            effectTick++
        }
    }
}
