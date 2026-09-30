package com.dick.narrative.ui

import com.dick.narrative.engine.NarrativeEngine
import com.dick.narrative.platform.appDataDir
import com.dick.narrative.platform.joinPath
import com.dick.narrative.platform.nowText
import com.dick.narrative.platform.readText
import com.dick.narrative.platform.stopAllAudio
import com.dick.narrative.platform.writeText
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonObject

/** 存<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌档槽摘要 */
data class SlotInfo(
    val slot: Int,
    val time: String = "",
    val preview: String = "",
    val line: String = "",
    val affection: Int = 0,
    val exists: Boolean = false,
)

/**
 * 存档 / 读档 / 设置 的落盘。
 * 存档目录：appDataDir()/saves，槽位 0 是自动存档。
 */
object SaveStore {

    const val AUTO = 0
    const val SLOTS = 9          // 0=自动 + 1..8 手动

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    private fun dir() = joinPath(appDataDir(), "saves")
    private fun file(slot: Int) = joinPath(dir(), "slot$slot.json")

    fun info(slot: Int): SlotInfo {
        val t = readText(file(slot))
        if (t.isNullOrBlank()) return SlotInfo(slot)
        return try {
            val o = json.parseToJsonElement(t).jsonObject
            SlotInfo(
                slot = slot,
                time = o.txt("time"),
                preview = o.txt("preview"),
                line = o.txt("line"),
                affection = (o["aff"] as? JsonPrimitive)?.doubleOrNull?.toInt() ?: 0,
                exists = true,
            )
        } catch (e: Exception) {
            SlotInfo(slot)
        }
    }

    fun save(slot: Int, engine: NarrativeEngine): Boolean {
        val preview = engine.text.ifBlank { engine.note }.take(42)
        val obj = JsonObject(
            mapOf(
                "time" to JsonPrimitive(nowText()),
                "preview" to JsonPrimitive(preview),
                "line" to JsonPrimitive(engine.lineTitle.ifBlank { engine.lineId }),
                "aff" to JsonPrimitive(engine.state.affection),
                "engine" to engine.snapshot(),
            )
        )
        return writeText(file(slot), obj.toString())
    }

    fun load(slot: Int, engine: NarrativeEngine): Boolean {
        val t = readText(file(slot)) ?: return false
        return try {
            val o = json.parseToJsonElement(t).jsonObject
            val e = o["engine"] as? JsonObject ?: return false
            stopAllAudio()
            engine.restore(e)
            true
        } catch (ex: Exception) {
            false
        }
    }
}

/** 播放设置 */
data class Settings(
    val textSpeed: Float = 34f,     // 字/秒；<=0 表示瞬间显示
    val volume: Float = 0.8f,
    val fullscreen: Boolean = false,
)

object SettingsStore {

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    private fun file() = joinPath(appDataDir(), "settings.json")

    fun load(): Settings {
        val t = readText(file()) ?: return Settings()
        return try {
            val o = json.parseToJsonElement(t).jsonObject
            Settings(
                textSpeed = (o["textSpeed"] as? JsonPrimitive)?.doubleOrNull?.toFloat() ?: 34f,
                volume = (o["volume"] as? JsonPrimitive)?.doubleOrNull?.toFloat() ?: 0.8f,
                fullscreen = (o["fullscreen"] as? JsonPrimitive)?.booleanOrNull ?: false,
            )
        } catch (e: Exception) {
            Settings()
        }
    }

    fun save(s: Settings) {
        val o = JsonObject(
            mapOf(
                "textSpeed" to JsonPrimitive(s.textSpeed),
                "volume" to JsonPrimitive(s.volume),
                "fullscreen" to JsonPrimitive(s.fullscreen),
            )
        )
        writeText(file(), o.toString())
    }
}

private fun JsonObject.txt(k: String): String = ((this[k]) as? JsonPrimitive)?.contentOrNullStr().orEmpty()

private fun JsonPrimitive.contentOrNullStr(): String? = if (this.isString || content != "null") content else null
