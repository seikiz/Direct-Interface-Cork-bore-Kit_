package com.dick.narrative.engine

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/*
 * 叙事规格（Spec）—— 引擎与渲染器之间的唯一契约。
 * 一份 spec = 一个故事：角色 + 线(场景) + 点(节拍) + 分支。
 * 载体是 JSON（"codex.json" / "story.json"），与具体渲染器无关：
 * 网页、桌面、手机、DICK 主聊天窗都只是把同一份 spec 画出来。
 */

/** 角色：独立实体（说话时显示的名字 + 默认立绘/语音） */
data class NarrRole(
    val name: String,
    val sprite: String = "",
    val voice: String = "",
)

/** choice 的一个选项 */
data class ChoiceOption(
    val text: String,
    val goto: String = "",
    val condition: JsonElement? = null,   // 条件不满足 → 该选项不显示
)

/**
 * 点（节拍）：线里的一步。kind 决定它做什么，其余字段按需使用。
 * kind: say / note / show / hide / bg / bgm / sfx / effect / wait / setflag / roll
 *       / choice / jump / end / action
 */
data class Step(
    val kind: String = "say",
    val text: String = "",
    val note: String = "",
    val role: String = "",           // 说话的角色名（对应 NarrRole.name）
    val sprite: String = "",
    val sprites: List<String> = emptyList(),   // 多立绘（制作器里一行可以挂多张）
    val voice: String = "",
    val bg: String = "",
    val bgm: String = "",
    val sfx: String = "",
    val effect: String = "",
    val waitMs: Int = 0,
    val images: List<String> = emptyList(),
    val clearImages: Boolean = false,
    val choices: List<ChoiceOption> = emptyList(),
    val goto: String = "",
    val endTitle: String = "",
    val action: String = "",
    val flagKey: String = "",
    val flagValue: Boolean = true,
    val condition: JsonElement? = null,  // 该点是否执行/显示
)

/** 线（场景）：一串点 + 出口（next / 分支在点里） */
data class Line(
    val id: String,
    val title: String = "",
    val images: List<String> = emptyList(),
    val steps: List<Step> = emptyList(),
    val next: String = "",
    val key: Boolean? = null,
    val bg: String = "",             // 线级背景：进入这条线就切
    val bgm: String = "",            // 线级音乐：进入这条线就换
)

/** 一个故事 */
data class NarrativeSpec(
    val name: String = "未命名故事",
    val intro: String = "",
    val roles: List<NarrRole> = emptyList(),
    val lines: List<Line> = emptyList(),
) {
    fun line(id: String): Line? = lines.firstOrNull { it.id == id }
    fun role(name: String): NarrRole? = roles.firstOrNull { it.name == name }
    val startId: String get() = lines.firstOrNull()?.id ?: ""
}

object SpecParser {

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }

    fun parse(text: String): NarrativeSpec = fromJson(json.parseToJsonElement(text))

    /** 把条件字符串（如 {"aff":">=85"}）解析成 JsonElement；失败返回 null（= 无条件） */
    fun parseCondition(text: String): JsonElement? =
        if (text.isBlank()) null
        else try {
            json.parseToJsonElement(text)
        } catch (e: Exception) {
            null
        }

    fun fromJson(root: JsonElement): NarrativeSpec {
        val o = root as? JsonObject ?: return NarrativeSpec()
        val roles = o.arr("roles").map { r ->
            NarrRole(
                name = r.str("name").orEmpty(),
                sprite = r.str("sprite").orEmpty(),
                voice = r.str("voice").orEmpty(),
            )
        }.filter { it.name.isNotBlank() }

        val lines = o.arr("scenes").ifEmpty { o.arr("lines") }.mapIndexed { i, sc ->
            Line(
                id = sc.str("id")?.takeIf { it.isNotBlank() } ?: "s${i + 1}",
                title = sc.str("title").orEmpty(),
                images = sc.strList("images"),
                next = sc.str("next").orEmpty().ifBlank { sc.str("jump").orEmpty() },
                key = sc.boolOrNull("key"),
                bg = sc.str("bg").orEmpty(),
                bgm = sc.str("bgm").orEmpty(),
                steps = sc.arr("lines").ifEmpty { sc.arr("steps") }.map { parseStep(it) },
            )
        }
        return NarrativeSpec(
            name = o.str("name")?.takeIf { it.isNotBlank() } ?: "未命名故事",
            intro = o.str("intro").orEmpty(),
            roles = roles,
            lines = lines,
        )
    }

    private fun parseStep(e: JsonElement): Step {
        val o = e as? JsonObject ?: return Step()
        val choices = o.arr("choice").map { c ->
            ChoiceOption(
                text = c.str("text").orEmpty(),
                goto = c.str("goto").orEmpty(),
                condition = (c as? JsonObject)?.get("if"),
            )
        }
        val kind = o.str("kind")?.takeIf { it.isNotBlank() } ?: guessKind(o)
        val flag = o["flag"] as? JsonObject
        return Step(
            kind = kind,
            text = o.str("text").orEmpty(),
            note = o.str("note").orEmpty(),
            role = o.str("speaker").orEmpty(),
            sprite = o.str("sprite").orEmpty(),
            sprites = parseSprites(o),
            voice = o.str("voice").orEmpty(),
            bg = o.str("bg").orEmpty(),
            bgm = o.str("bgm").orEmpty(),
            sfx = o.str("sfx").orEmpty(),
            effect = o.str("effect").orEmpty(),
            waitMs = o.int("ms") ?: 0,
            images = o.strList("images"),
            clearImages = o.boolOrNull("clearImages") == true || o.boolOrNull("hideImages") == true,
            choices = choices,
            goto = o.str("goto").orEmpty().ifBlank { o.str("jump").orEmpty() },
            endTitle = o.str("end").orEmpty(),
            action = o.str("action").orEmpty(),
            flagKey = flag?.str("k").orEmpty(),
            flagValue = flag?.boolOrNull("v") ?: true,
            condition = o["if"],
        )
    }

    /** 立绘列表：["a.png"] 和 [{"file":"a.png"}] 两种写法都吃 */
    private fun parseSprites(o: JsonObject): List<String> =
        (o["sprites"] as? JsonArray)
            ?.mapNotNull { e ->
                when (e) {
                    is JsonPrimitive -> e.contentOrNullSafe()
                    is JsonObject -> (e["file"] as? JsonPrimitive)?.contentOrNullSafe()
                    else -> null
                }
            }
            ?.filter { it.isNotBlank() }
            ?: emptyList()

    /** 老格式（没写 kind）按字段推断 */
    private fun guessKind(o: JsonObject): String = when {        o.containsKey("choice") -> "choice"
        o.containsKey("jump") -> "jump"
        o.containsKey("end") -> "end"
        o.containsKey("action") -> "action"
        o.containsKey("text") -> "say"
        o.containsKey("note") -> "note"
        o.containsKey("bg") -> "bg"
        o.containsKey("bgm") -> "bgm"
        o.containsKey("sfx") -> "sfx"
        o.containsKey("effect") -> "effect"
        o.containsKey("wait") -> "wait"
        o.containsKey("setflag") -> "setflag"
        else -> "action"
    }
}

// ---------- JsonElement 读取小工<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌具（动态 JSON，宽容缺字段） ----------
fun JsonElement.str(key: String): String? =
    ((this as? JsonObject)?.get(key) as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNullSafe()

fun JsonElement.int(key: String): Int? =
    ((this as? JsonObject)?.get(key) as? JsonPrimitive)?.doubleOrNull?.toInt()

fun JsonElement.boolOrNull(key: String): Boolean? =
    ((this as? JsonObject)?.get(key) as? JsonPrimitive)?.booleanOrNull

fun JsonElement.arr(key: String): List<JsonElement> =
    ((this as? JsonObject)?.get(key) as? JsonArray)?.toList() ?: emptyList()

fun JsonElement.strList(key: String): List<String> =
    arr(key).mapNotNull { (it as? JsonPrimitive)?.contentOrNullSafe() }.filter { it.isNotBlank() }

private fun JsonPrimitive.contentOrNullSafe(): String? =
    if (this is JsonNull) null else content
