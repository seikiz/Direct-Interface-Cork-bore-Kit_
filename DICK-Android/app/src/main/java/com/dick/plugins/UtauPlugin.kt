package com.dick.plugins

import android.content.Context
import android.speech.tts.TextToSpeech
import java.util.Locale

/**
 * UTAU 语音（Android 版）—— 与桌面版 utau_voice.py 对位，按平台能力阉割。
 *
 * 保留（系统 TTS 能给的）：
 *   /speak <文本>           实时朗读（日文/中文自动识别）
 *   AI 回复 [ja]...[/ja]    自动配音（中字日配，队列追加不打断正文朗读）
 *
 * 阉割（手机性能/系统 TTS 给不了，硬做即伪功能）：
 *   ✂ 音高/语速逐音节控制    → 跟随系统 TTS 设置
 *   ✂ 批量合成 wav 落盘       → 只实时播，不做文件
 *   ✂ 多声库切换              → 跟随系统 TTS 引擎
 *
 * 性能保护：超长文本截断、TTS 实例失败静默降级。
 */
class UtauPlugin(private val context: Context) : Plugin {
    override val name = "UTAU 语音"
    override val version = "1.0"
    override val description = "朗读 /speak（系统 TTS，日文/中文）；AI 回复 [ja] 句自动配音"
    override var enabled = false

    private var tts: TextToSpeech? = null

    override fun onLoad() {
        try {
            tts = TextToSpeech(context) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    // 默认日语（声库存在时）；中文句子 speak() 里再切
                    tts?.language = Locale.JAPAN
                }
            }
        } catch (_: Exception) {
            tts = null
        }
    }

    override fun onCommand(command: String, args: String): String? {
        if (command == "speak" || command == "朗读" || command == "tts") {
            val text = args.trim()
            if (text.isEmpty()) return "用法: /speak <文本>（日文/中文自动识别）"
            speak(text, queue = TextToSpeech.QUEUE_FLUSH)
            return "🗣️ $text"
        }
        return null
    }

    override fun onMessageReceived(userInput: String, aiReply: String) {
        // 中字日配：AI 回复含 [ja]...[/ja] → 自动朗读配音句（队列追加，不打断正文朗读）
        try {
            val m = Regex("""\[ja\]([\s\S]*?)\[/ja\]""").find(aiReply)
            if (m != null && m.groupValues.size > 1 && m.groupValues[1].isNotBlank()) {
                speak(m.groupValues[1].trim(), queue = TextToSpeech.QUEUE_ADD)
            }
        } catch (_: Exception) {
        }
    }

    fun speak(text: String, queue: Int = TextToSpeech.QUEUE_FLUSH) {
        val t = tts ?: return
        // 性能保护：截断超长文本，避免 TTS 卡死
        val safe = if (text.length > 300) text.take(300) + "…" else text
        try {
            t.language = if (isJapanese(safe)) Locale.JAPAN else Locale.CHINA
            t.speak(safe, queue, null, "dick-utau")
        } catch (_: Exception) {
        }
    }

    /** 日语识别：假名（0x3040-0x30FF）+ 常用日文汉字区（0x4E00-0x9FFF 里大概率是日文语境，
     * 结合是否含助词「です/ます/は/の/に」等判断，避免把中文长句误判为日语） */
    private fun isJapanese(text: String): Boolean {
        var kana = 0
        var han = 0
        for (c in text) {
            val code = c.code
            if (code in 0x3040..0x30FF) kana++
            else if (code in 0x4E00..0x9FFF) han++
        }
        if (kana > 0) return true
        if (han == 0) return false
        // 无假名但有汉字：日文助词出现则判定日语（中文句子一般无这些词）
        val jpParticles = listOf("です", "ます", "は", "の", "に", "を", "で", "た", "だ", "よ", "ね", "〜")
        return jpParticles.any { text.contains(it) }
    }
}
