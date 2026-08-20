package com.dick.core

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import java.io.ByteArrayOutputStream
import java.util.Base64
import java.util.zip.CRC32
import java.util.zip.Inflater

/**
 * 酒馆(SillyTavern)角色卡兼容层 —— 与桌面版 card_compat.py 逐条对应：
 *   toDick：v1 / v2(spec=chara_card_v2|v3) / DICK 原生 → {name, system_prompt, card_data}
 *   dickToV2：DICK 卡 → 酒馆 v2 JSON（有 card_data 则尽量无损回导）
 *   PNG：读 tEXt/zTXt/iTXt 块（关键字 chara/ccv3），写 tEXt 嵌卡（IHDR 后插入）
 *   占位头像：Android Canvas 渐变 + 名字首字
 */
object CardCompat {

    val PNG_SIG = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)

    data class DickCard(
        val name: String,
        val systemPrompt: String,
        val cardData: J.Obj?,
        val worldEntries: List<J.Obj> = emptyList(),
    )

    /** 从酒馆 v2/v3 卡 extensions.world 提取世界书条目（与桌面版 extract_world 对应） */
    fun extractWorld(root: J): List<J.Obj> {
        val data = root as? J.Obj ?: return emptyList()
        val d = data.fields["data"] as? J.Obj ?: data
        val ext = d.fields["extensions"] as? J.Obj ?: return emptyList()
        val world = ext.fields["world"] as? J.Obj ?: return emptyList()
        val entries = world.fields["entries"] as? J.Arr ?: return emptyList()
        val out = mutableListOf<J.Obj>()
        for (e in entries.items) {
            val o = e as? J.Obj ?: continue
            val content = clean(o.fields["content"])
            if (content.isEmpty()) continue
            val keys = when (val k = o.fields["keys"] ?: o.fields["keywords"]) {
                is J.Arr -> k.items.mapNotNull { (it as? J.Str)?.v?.trim() }.filter { it.isNotEmpty() }
                is J.Str -> k.v.split(",", "，").map { it.trim() }.filter { it.isNotEmpty() }
                else -> emptyList()
            }
            val entry = J.Obj()
            entry.fields["id"] = J.Str(clean(o.fields["id"]))
            entry.fields["keywords"] = J.Arr().also { a -> keys.forEach { a.items.add(J.Str(it)) } }
            entry.fields["content"] = J.Str(content)
            entry.fields["match"] = J.Str("any")
            entry.fields["weight"] = J.Num((o.fields["priority"] as? J.Num)?.v ?: (o.fields["weight"] as? J.Num)?.v ?: 100.0)
            entry.fields["probability"] = J.Num((o.fields["probability"] as? J.Num)?.v ?: 100.0)
            entry.fields["depth"] = J.Num((o.fields["depth"] as? J.Num)?.v ?: 1.0)
            entry.fields["enabled"] = J.Bool((o.fields["enabled"] as? J.Bool)?.v ?: true)
            entry.fields["constant"] = J.Bool((o.fields["constant"] as? J.Bool)?.v ?: false)
            // 酒馆世界书元字段全量保留（无损往返；DICK 引擎忽略未知键）
            val meta = J.Obj()
            var hasMeta = false
            for (k in listOf("name", "insertion_order", "case_sensitive", "selective",
                             "secondary_keys", "comment", "position")) {
                val v = o.fields[k] ?: continue
                meta.fields[k] = v
                hasMeta = true
            }
            if (hasMeta) entry.fields["_meta"] = meta
            out.add(entry)
        }
        return out
    }

    // ---------- 基础值转字符串 ----------
    private fun numStr(v: J.Num): String =
        if (v.raw.isNotEmpty()) v.raw else {
            if (v.v == v.v.toLong().toDouble() && kotlin.math.abs(v.v) < 1e15) v.v.toLong().toString() else v.v.toString()
        }

    private fun str(v: J?): String = when (v) {
        is J.Str -> v.v
        is J.Num -> numStr(v)
        is J.Bool -> v.v.toString()
        is J.Null -> ""
        else -> ""
    }

    /** 对应 Python _clean：列表 → 逗号连接；其余 → 字符串 strip */
    private fun clean(v: J?): String {
        val s = if (v is J.Arr) v.items.joinToString(", ") { clean(it) } else str(v)
        return s.trim()
    }

    /** 对应 Python _sections：字段拼成 DICK 的 system_prompt（分节标题） */
    private fun sections(data: J.Obj): String {
        val parts = mutableListOf<String>()
        fun add(title: String, v: J?) {
            val c = clean(v)
            if (c.isNotEmpty()) parts.add(title + "：" + c)
        }
        add("【角色简介】", data.fields["description"])
        add("【性格】", data.fields["personality"])
        add("【背景设定】", data.fields["scenario"])
        add("【开场白】", data.fields["first_mes"])
        add("【对话示例】", data.fields["mes_example"])
        add("【备注】", data.fields["creator_notes"])
        val sp = clean(data.fields["system_prompt"])
        if (sp.isNotEmpty()) parts.add(sp)
        val phi = clean(data.fields["post_history_instructions"])
        if (phi.isNotEmpty()) parts.add("【历史后指令】" + phi)
        val ag = data.fields["alternate_greetings"] as? J.Arr
        if (ag != null && ag.items.isNotEmpty()) {
            parts.add("【备用开场白】" + 10.toChar() + ag.items.joinToString(10.toChar().toString()) { "· " + clean(it) })
        }
        return parts.joinToString(10.toChar().toString() + 10.toChar().toString())
    }

    /** 任意酒馆/DICK 卡 → DickCard 或 null */
    fun toDick(root: J): DickCard? {
        val data = root as? J.Obj ?: return null
        val spec = (data.fields["spec"] as? J.Str)?.v
        val isV2 = spec == "chara_card_v2" || spec == "chara_card_v3"
        if (isV2) {
            val d = (data.fields["data"] as? J.Obj) ?: J.Obj()
            val name = clean(d.fields["name"]).ifBlank { clean(data.fields["name"]) }.ifBlank { "导入角色" }
            return DickCard(name, sections(d).ifBlank { name }, data, extractWorld(data))
        }
        val v1Keys = listOf("description", "personality", "first_mes", "mes_example")
        val isV1 = !data.fields.containsKey("spec") && !data.fields.containsKey("data") &&
            v1Keys.any { data.fields.containsKey(it) }
        if (isV1) {
            val name = clean(data.fields["name"]).ifBlank { "导入角色" }
            return DickCard(name, sections(data).ifBlank { name }, data, extractWorld(data))
        }
        val sp = clean(data.fields["system_prompt"])
        if (sp.isNotEmpty()) {
            val name = clean(data.fields["name"]).ifBlank { "导入角色" }
            return DickCard(name, sp, data.fields["card_data"] as? J.Obj, extractWorld(data))
        }
        return null
    }

    /** DICK 世界书条目 → 酒馆 v2 extensions.world 条目（无损反向，与桌面版对应） */
    fun worldToSillytavern(entries: List<J.Obj>, baseId: Int = 1): List<J.Obj> {
        val out = mutableListOf<J.Obj>()
        entries.forEachIndexed { i, e ->
            val meta = e.fields["_meta"] as? J.Obj
            val keys = when (val k = e.fields["keywords"]) {
                is J.Arr -> k.items.mapNotNull { (it as? J.Str)?.v }
                is J.Str -> k.v.split(",", "，").map { it.trim() }.filter { it.isNotEmpty() }
                else -> emptyList()
            }
            val entry = J.Obj()
            entry.fields["keys"] = J.Arr().also { a -> keys.forEach { a.items.add(J.Str(it)) } }
            entry.fields["content"] = J.Str(e.fields["content"]?.str() ?: "")
            entry.fields["enabled"] = J.Bool((e.fields["enabled"] as? J.Bool)?.v ?: true)
            entry.fields["insertion_order"] = J.Num((meta?.fields?.get("insertion_order") as? J.Num)?.v ?: (i * 100).toDouble())
            entry.fields["case_sensitive"] = J.Bool((meta?.fields?.get("case_sensitive") as? J.Bool)?.v ?: false)
            entry.fields["name"] = J.Str(meta?.fields?.get("name")?.str() ?: "")
            entry.fields["priority"] = J.Num((e.fields["weight"] as? J.Num)?.v ?: (e.fields["priority"] as? J.Num)?.v ?: 100.0)
            entry.fields["id"] = J.Num((e.fields["id"] as? J.Num)?.v ?: (baseId + i).toDouble())
            entry.fields["comment"] = J.Str(meta?.fields?.get("comment")?.str() ?: "")
            entry.fields["selective"] = J.Bool((meta?.fields?.get("selective") as? J.Bool)?.v ?: false)
            entry.fields["secondary_keys"] = meta?.fields?.get("secondary_keys") ?: J.Arr()
            entry.fields["constant"] = J.Bool((e.fields["constant"] as? J.Bool)?.v ?: false)
            entry.fields["position"] = J.Str(meta?.fields?.get("position")?.str() ?: "before_char")
            out.add(entry)
        }
        return out
    }

    /** DICK 卡 → 酒馆 v2 JSON。有 card_data 且含 data 块 → 整卡回导保留 spec；否则包标准 v2。
     *  worldEntries：DICK 世界书条目，非空时写回 extensions.world（无损反向）。 */
    fun dickToV2(name: String, systemPrompt: String, cardData: J.Obj?, worldEntries: List<J.Obj> = emptyList()): J.Obj {
        if (cardData != null && cardData.fields.isNotEmpty()) {
            val out = JsonS.parse(JsonS.stringify(cardData)) as? J.Obj ?: return standardV2(name, systemPrompt)
            val d = out.fields["data"] as? J.Obj
            if (d != null) {
                // 整卡形态（v2/v3）：保留原 spec
                if (!out.fields.containsKey("spec")) out.fields["spec"] = J.Str("chara_card_v2")
                if (!out.fields.containsKey("spec_version")) out.fields["spec_version"] = J.Str("2.0")
                out.fields["name"] = J.Str(name)
                d.fields["name"] = J.Str(name)
                if (clean(d.fields["system_prompt"]).isEmpty() && systemPrompt.isNotBlank()) {
                    d.fields["system_prompt"] = J.Str(systemPrompt)
                }
                if (worldEntries.isNotEmpty()) {
                    val ext = (d.fields["extensions"] as? J.Obj) ?: J.Obj().also { d.fields["extensions"] = it }
                    val world = J.Obj()
                    world.fields["entries"] = J.Arr().also { a -> worldToSillytavern(worldEntries).forEach { a.items.add(it) } }
                    ext.fields["world"] = world
                }
            } else {
                // 裸字段块：包成标准 v2 卡（data.name 同步当前名字，与桌面版一致）
                if (clean(out.fields["system_prompt"]).isEmpty() && systemPrompt.isNotBlank()) {
                    out.fields["system_prompt"] = J.Str(systemPrompt)
                }
                out.fields["name"] = J.Str(name)
                if (worldEntries.isNotEmpty()) {
                    val ext = (out.fields["extensions"] as? J.Obj) ?: J.Obj().also { out.fields["extensions"] = it }
                    val world = J.Obj()
                    world.fields["entries"] = J.Arr().also { a -> worldToSillytavern(worldEntries).forEach { a.items.add(it) } }
                    ext.fields["world"] = world
                }
                val wrapped = J.Obj()
                wrapped.fields["spec"] = J.Str("chara_card_v2")
                wrapped.fields["spec_version"] = J.Str("2.0")
                wrapped.fields["name"] = J.Str(name)
                wrapped.fields["data"] = out
                return wrapped
            }
            return out
        }
        if (worldEntries.isNotEmpty()) {
            val o = standardV2(name, systemPrompt)
            val d = o.fields["data"] as? J.Obj
            val ext = (d?.fields?.get("extensions") as? J.Obj) ?: J.Obj().also { d?.fields?.set("extensions", it) }
            val world = J.Obj()
            world.fields["entries"] = J.Arr().also { a -> worldToSillytavern(worldEntries).forEach { a.items.add(it) } }
            ext.fields["world"] = world
            return o
        }
        return standardV2(name, systemPrompt)
    }

    private fun standardV2(name: String, systemPrompt: String): J.Obj {
        val o = J.Obj()
        o.fields["spec"] = J.Str("chara_card_v2")
        o.fields["spec_version"] = J.Str("2.0")
        o.fields["name"] = J.Str(name)
        val d = J.Obj()
        d.fields["name"] = J.Str(name)
        d.fields["description"] = J.Str("")
        d.fields["personality"] = J.Str("")
        d.fields["scenario"] = J.Str("")
        d.fields["first_mes"] = J.Str("")
        d.fields["mes_example"] = J.Str("")
        d.fields["creator_notes"] = J.Str("")
        d.fields["system_prompt"] = J.Str(systemPrompt)
        d.fields["post_history_instructions"] = J.Str("")
        d.fields["alternate_greetings"] = J.Arr()
        d.fields["tags"] = J.Arr()
        d.fields["creator"] = J.Str("DICK")
        d.fields["character_version"] = J.Str("1.0")
        d.fields["extensions"] = J.Obj()
        o.fields["data"] = d
        return o
    }

    // ---------- PNG 块读写 ----------
    private data class Chunk(val type: String, val data: ByteArray)

    private fun readInt32BE(b: ByteArray, off: Int): Int =
        ((b[off].toInt() and 0xFF) shl 24) or
            ((b[off + 1].toInt() and 0xFF) shl 16) or
            ((b[off + 2].toInt() and 0xFF) shl 8) or
            (b[off + 3].toInt() and 0xFF)

    private fun int32BE(v: Int): ByteArray = byteArrayOf(
        ((v ushr 24) and 0xFF).toByte(),
        ((v ushr 16) and 0xFF).toByte(),
        ((v ushr 8) and 0xFF).toByte(),
        (v and 0xFF).toByte(),
    )

    private fun chunks(png: ByteArray): List<Chunk>? {
        if (png.size < 8 || !png.copyOfRange(0, 8).contentEquals(PNG_SIG)) return null
        val out = mutableListOf<Chunk>()
        var pos = 8
        while (pos + 8 <= png.size) {
            val len = readInt32BE(png, pos)
            if (len < 0) return null
            if (pos + 12 + len > png.size) return null
            val type = String(png, pos + 4, 4, Charsets.ISO_8859_1)
            val data = png.copyOfRange(pos + 8, pos + 8 + len)
            out.add(Chunk(type, data))
            pos += 12 + len
            if (type == "IEND") break
        }
        return if (out.isEmpty()) null else out
    }

    private fun inflate(bytes: ByteArray): String? = try {
        val inflater = Inflater()
        inflater.setInput(bytes)
        val out = ByteArrayOutputStream()
        val buf = ByteArray(8192)
        while (!inflater.finished()) {
            val n = inflater.inflate(buf)
            if (n <= 0) break
            out.write(buf, 0, n)
        }
        inflater.end()
        String(out.toByteArray(), Charsets.UTF_8)
    } catch (_: Exception) {
        null
    }

    private fun inflateLatin(bytes: ByteArray): String? = try {
        val inflater = Inflater()
        inflater.setInput(bytes)
        val out = ByteArrayOutputStream()
        val buf = ByteArray(8192)
        while (!inflater.finished()) {
            val n = inflater.inflate(buf)
            if (n <= 0) break
            out.write(buf, 0, n)
        }
        inflater.end()
        String(out.toByteArray(), Charsets.ISO_8859_1)
    } catch (_: Exception) {
        null
    }

    private fun tEXtRead(data: ByteArray): Pair<String?, String?> {
        val i = data.indexOf(0)
        if (i < 0) return null to null
        val kw = String(data, 0, i, Charsets.ISO_8859_1)
        val text = String(data, i + 1, data.size - i - 1, Charsets.ISO_8859_1)
        return kw to text
    }

    private fun zTXtRead(data: ByteArray): Pair<String?, String?> {
        val i = data.indexOf(0)
        if (i < 0) return null to null
        val kw = String(data, 0, i, Charsets.ISO_8859_1)
        if (data.size <= i + 2) return null to null
        return kw to (inflateLatin(data.copyOfRange(i + 2, data.size)) ?: return null to null)
    }

    private fun iTXtRead(data: ByteArray): Pair<String?, String?> {
        val i = data.indexOf(0)
        if (i < 0) return null to null
        val kw = String(data, 0, i, Charsets.ISO_8859_1)
        val rest = data.copyOfRange(i + 1, data.size)
        if (rest.isEmpty()) return null to null
        val compFlag = rest[0].toInt() and 0xFF
        val j = rest.indexOf(0)
        if (j < 0) return null to null
        val sub = rest.copyOfRange(j + 1, rest.size)
        val k = sub.indexOf(0)
        if (k < 0) return null to null
        val textBytes = rest.copyOfRange(j + 1 + k + 1, rest.size)
        return try {
            val text = if (compFlag != 0) inflate(textBytes) else String(textBytes, Charsets.UTF_8)
            kw to text
        } catch (_: Exception) {
            null to null
        }
    }

    /** 从 PNG 嵌卡提取角色卡 JSON（支持 chara/ccv3，tEXt/zTXt/iTXt） */
    fun pngExtractCard(png: ByteArray): J.Obj? {
        val chs = chunks(png) ?: return null
        val texts = mutableMapOf<String, String>()
        for (c in chs) {
            val (kw, text) = when (c.type) {
                "tEXt" -> tEXtRead(c.data)
                "zTXt" -> zTXtRead(c.data)
                "iTXt" -> iTXtRead(c.data)
                else -> null to null
            }
            if (kw != null && text != null) texts[kw] = text
        }
        var raw = texts["ccv3"] ?: texts["chara"] ?: return null
        raw = raw.trim()
        if (raw.startsWith("data:")) raw = raw.substringAfter(",")
        return try {
            val decoded = Base64.getMimeDecoder().decode(raw)
            JsonS.parse(String(decoded, Charsets.UTF_8)) as? J.Obj
        } catch (_: Exception) {
            null
        }
    }

    private fun writeChunk(out: ByteArrayOutputStream, type: String, data: ByteArray) {
        val typeBytes = type.toByteArray(Charsets.ISO_8859_1)
        out.write(int32BE(data.size))
        out.write(typeBytes)
        out.write(data)
        val crc = CRC32()
        crc.update(typeBytes)
        crc.update(data)
        out.write(int32BE(crc.value.toInt()))
    }

    /** 把角色卡 JSON 嵌入 PNG（IHDR 后插入 tEXt 块，跳过旧 chara/ccv3） */
    fun pngEmbedCard(png: ByteArray, card: J.Obj, v3: Boolean = false): ByteArray? {
        val chs = chunks(png) ?: return null
        val keyword = if (v3) "ccv3" else "chara"
        val payload = Base64.getEncoder().encodeToString(JsonS.stringify(card).toByteArray(Charsets.UTF_8))
        val out = ByteArrayOutputStream()
        out.write(PNG_SIG)
        var ihdrWritten = false
        for (c in chs) {
            if (c.type == "IHDR") {
                if (ihdrWritten) continue
                writeChunk(out, "IHDR", c.data)
                writeChunk(out, "tEXt", (keyword + "\u0000" + payload).toByteArray(Charsets.ISO_8859_1))
                ihdrWritten = true
                continue
            }
            if (c.type == "tEXt") {
                val (kw, _) = tEXtRead(c.data)
                if (kw == "chara" || kw == "ccv3") continue
            }
            writeChunk(out, c.type, c.data)
        }
        return out.toByteArray()
    }

    // ---------- 占位头像（Canvas 渐变 + 首字） ----------
    fun placeholderPng(name: String, size: Int = 512): ByteArray {
        val n = name.ifBlank { "?" }
        var h = 0L
        for (ch in n) h = (h * 31 + ch.code.toLong()) and 0xFFFFFFFFL
        val c1 = intArrayOf((24 + (h % 40)).toInt(), (34 + ((h shr 3) % 40)).toInt(), (58 + ((h shr 6) % 40)).toInt())
        val c2 = intArrayOf((70 + ((h shr 5) % 50)).toInt(), (44 + ((h shr 8) % 50)).toInt(), (110 + ((h shr 11) % 60)).toInt())
        val bmp = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)
        val paint = Paint()
        paint.shader = LinearGradient(
            0f, 0f, 0f, size.toFloat(),
            Color.rgb(c1[0], c1[1], c1[2]), Color.rgb(c2[0], c2[1], c2[2]), Shader.TileMode.CLAMP,
        )
        canvas.drawRect(0f, 0f, size.toFloat(), size.toFloat(), paint)
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG)
        textPaint.color = Color.rgb(235, 238, 245)
        textPaint.textSize = size * 0.42f
        textPaint.textAlign = Paint.Align.CENTER
        val ch = n.first().toString()
        val fm = textPaint.fontMetrics
        val baseline = size / 2f - (fm.ascent + fm.descent) / 2f
        canvas.drawText(ch, size / 2f, baseline, textPaint)
        val out = ByteArrayOutputStream()
        bmp.compress(Bitmap.CompressFormat.PNG, 100, out)
        bmp.recycle()
        return out.toByteArray()
    }
}
