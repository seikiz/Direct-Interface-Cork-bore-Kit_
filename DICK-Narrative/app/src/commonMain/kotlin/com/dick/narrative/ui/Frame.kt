package com.dick.narrative.ui

import androidx.compose.runtime.Immutable
import com.dick.narrative.engine.ChoiceView
import com.dick.narrative.engine.NarrativeEngine
import com.dick.narrative.engine.SpriteView

/**
 * 帧：引擎第 N 步之后「该画什么」的不可变快照。
 * Compose 只在帧对象变化时重组，所以引擎内部怎么改都不影响渲染层。
 */
@Immutable
data class Frame(
    val lineId: String = "",
    val lineTitle: String = "",
    val bg: String = "",
    val sprites: List<SpriteView> = emptyList(),
    val images: List<String> = emptyList(),
    val speaker: String = "",
    val text: String = "",
    val note: String = "",
    val choices: List<ChoiceView> = emptyList(),
    val ended: Boolean = false,
    val endTitle: String = "",
    val bgm: String = "",
    val voice: String = "",
    val voiceTick: Int = 0,
    val sfx: String = "",
    val sfxTick: Int = 0,
    val effect: String = "",
    val effectTick: Int = 0,
    val waitMs: Int = 0,
    val waitTick: Int = 0,
    val affection: Int = 50,
)

fun NarrativeEngine.frame(): Frame = Frame(
    lineId = lineId,
    lineTitle = lineTitle,
    bg = bg,
    sprites = sprites,
    images = images,
    speaker = speaker,
    text = text,
    note = note,
    choices = choices,
    ended = ended,
    endTitle = endTitle,
    bgm = bgm,
    voice = voice,
    voiceTick = voiceTick,
    sfx = sfx,
    sfxTick = sfxTick,
    effect = effect,
    effectTick = effectTick,
    waitMs = waitMs,
    waitTick = waitTick,
    affection = state.affection,
)
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌