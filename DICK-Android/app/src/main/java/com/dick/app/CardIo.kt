package com.dick.app

import android.content.Context
import android.net.Uri
import com.dick.core.AppEnv
import com.dick.core.CardCompat
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.Workshop
import com.dick.core.WorldData
import java.io.File
import java.util.concurrent.ConcurrentHashMap

/**
 * 角色卡的进 / 出 —— 只做"重活"，不碰界面。
 *
 * 为什么单独拆出来：导入 / 导出原本整个写在 `rememberLauncherForActivityResult` 的回调里，
 * 而回调跑在**主线程**上 —— 读多 MB 的 PNG 嵌卡、zlib 解压、逐块扫 PNG、写角色卡 + 世界卡、
 * 再遍历整个世界卡目录解析一遍描述，全都在主线程干。导入一张大卡就是一次肉眼可见的卡顿。
 *
 * 这里的规矩：
 *   ① 所有文件读写与解析都在调用方给的 IO 线程上做；
 *   ② **不碰任何 Compose 状态**（`roleUnlocked` / `worlds` / `sysMsgs` 一律由调用方在主线程更新）；
 *   ③ 返回值/异常就是全部结果，调用方照着它更新界面。
 */

/** 导入结果：界面只用处理这三种情况 */
sealed interface CardImport {
    /** 读出来是空的 → 静默返回（与旧行为一致，不提示） */
    data object Nothing : CardImport

    /** 认不出的格式 → 由界面提示用户 */
    data object BadFormat : CardImport

    /** 成功：角色卡与世界卡都已落盘，界面照着这些数据更新列表 */
    data class Done(
        val name: String,
        val systemPrompt: String,
        /** 是否写入了头像（写入了才需要清头像缓存） */
        val wroteAvatar: Boolean,
        /** 提示语尾巴，例如"，世界书 12 条 → 世界卡「X 的世界书」" */
        val worldNote: String,
        /** 世界卡列表（全量，按目录顺序）：界面按"没有才加"合并 */
        val worldPairs: List<Pair<String, String>>,
        /** 工坊本地列表：角色卡 / 世界卡的**文件名**，由 Workshop 统一枚举 */
        val wsRoles: List<String>,
        val wsWorlds: List<String>,
    ) : CardImport
}

/** 正在导入中的卡名：同一张卡被连点两次时，光看磁盘会算出同一个名字（后一个覆盖前一个） */
private val importingNames = ConcurrentHashMap.newKeySet<String>()

/** 磁盘上已有的角色卡名（文件名去扩展名）：算重名要用磁盘的真实状态，不能只看界面列表 */
private fun roleNamesOnDisk(): List<String> =
    AppEnv.savesDir().listFiles()
        ?.filter { it.isFile && it.name.endsWith(".json") && !it.name.startsWith("_tree_") && !it.name.startsWith(".") }
        ?.map { it.nameWithoutExtension }
        ?: emptyList()

/**
 * 导入角色卡：读 URI → 解析（JSON / PNG 嵌卡）→ 写 `saves/<名字>.json`（含头像与酒馆世界书）。
 * 需要在 IO 线程上调用；失败抛异常，由调用方提示。
 */
fun importCardHeavy(ctx: Context, uri: Uri, existingNames: Set<String>): CardImport {
    val bytes = ctx.contentResolver.openInputStream(uri)?.use { it.readBytes() }
    if (bytes == null || bytes.isEmpty()) return CardImport.Nothing

    val mime = ctx.contentResolver.getType(uri) ?: ""
    val isImg = mime.startsWith("image/") || uri.toString().lowercase().endsWith(".png") ||
        uri.toString().lowercase().endsWith(".webp")
    val parsed = if (isImg) CardCompat.pngExtractCard(bytes)
    else (JsonS.parse(String(bytes, Charsets.UTF_8)) as? J.Obj)
    val card = parsed?.let { CardCompat.toDick(it) } ?: return CardImport.BadFormat

    // 重名：界面列表 + 磁盘 + 正在导入的<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌，三处都算上（连点两次不会撞同一个文件名）
    val taken = HashSet(existingNames)
    taken.addAll(roleNamesOnDisk())
    var name = card.name
    var i = 2
    while (name in taken || !importingNames.add(name)) {
        name = card.name + "_" + i
        i++
    }
    try {
        val o = J.Obj()
        o.fields["name"] = J.Str(name)
        o.fields["system_prompt"] = J.Str(card.systemPrompt)
        card.cardData?.let { o.fields["card_data"] = it }
        // 开场白：从卡内提取到顶层，供 P0 作为固定首条消息显示（不再进人设提示/词闸参考）
        (card.cardData as? J.Obj)?.let { cd ->
            val fm = (cd.fields["data"] as? J.Obj)?.fields?.get("first_mes")?.str()?.takeIf { it.isNotBlank() }
                ?: cd.fields["first_mes"]?.str()?.takeIf { it.isNotBlank() }
            if (fm != null) o.fields["first_mes"] = J.Str(fm)
        }
        File(AppEnv.savesDir(), name + ".json").writeText(JsonS.stringify(o, pretty = true), Charsets.UTF_8)

        var wroteAvatar = false
        if (isImg) {
            val dir = File(AppEnv.savesDir(), "avatars").apply { mkdirs() }
            File(dir, name + ".png").writeBytes(bytes)
            wroteAvatar = true
        }

        // 完全适配：酒馆 v2 内嵌世界书 → DICK 世界卡（与桌面版一致）
        var worldNote = ""
        var worldPairs: List<Pair<String, String>> = emptyList()
        if (card.worldEntries.isNotEmpty()) {
            // 世界书写失败不该让"角色卡已导入"变成一个失败弹窗 —— 角色确实进来了，
            // 老老实实把失败写进提示语尾巴（旧行为是 Log.w 吞掉，界面上看不出来）
            try {
                val wn = name + " 的世界书"
                val wFile = File(AppEnv.worldsDir(), wn + ".json")
                val existing = try {
                    (JsonS.parse(wFile.readText(Charsets.UTF_8)) as? J.Obj)?.fields?.get("entries") as? J.Arr
                } catch (_: Exception) { null }
                val entries = J.Arr()
                if (existing != null) {
                    val existingIds = existing.items.mapNotNull { (it as? J.Obj)?.fields?.get("id")?.str() }.toSet()
                    existing.items.forEach { entries.items.add(it) }
                    card.worldEntries.forEach { e ->
                        val id = e.fields["id"]?.str() ?: ""
                        if (id !in existingIds) entries.items.add(e)
                    }
                } else {
                    card.worldEntries.forEach { entries.items.add(it) }
                }
                val w = J.Obj()
                w.fields["name"] = J.Str(wn)
                w.fields["description"] = J.Str("从角色卡「" + name + "」导入的酒馆世界书")
                w.fields["rules"] = J.Arr()
                w.fields["entries"] = entries
                w.fields["params"] = J.Obj()
                wFile.parentFile?.mkdirs()
                wFile.writeText(JsonS.stringify(w, pretty = true), Charsets.UTF_8)
                worldNote = "，世界书 " + card.worldEntries.size + " 条 → 世界卡「" + wn + "」"
                // 刷新世界列表：这里只负责把目录读成数据，加进界面列表由调用方做主
                worldPairs = AppEnv.worldsDir().listFiles()
                    ?.filter { it.isFile && it.name.endsWith(".json") && !it.name.startsWith("_tree_") && !it.name.startsWith(".") }
                    ?.mapNotNull { f ->
                        try {
                            val wo = JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Obj ?: return@mapNotNull null
                            val wn2 = wo.fields["name"]?.str() ?: f.nameWithoutExtension
                            val wd = WorldData.fromJson(wo)
                            wn2 to renderWorldDesc(wd.description, wd.params)
                        } catch (_: Exception) { null }
                    }
                    ?: emptyList()
            } catch (e: Exception) {
                worldNote = "，但世界书写入失败：" + (e.message ?: "")
            }
        }
        return CardImport.Done(
            name = name,
            systemPrompt = card.systemPrompt,
            wroteAvatar = wroteAvatar,
            worldNote = worldNote,
            worldPairs = worldPairs,
            wsRoles = Workshop.localRoles(),
            wsWorlds = Workshop.localWorlds(),
        )
    } finally {
        importingNames.remove(name)
    }
}

/**
 * 导出角色卡：读 `saves/<名字>.json`（+ 关联世界卡 + 头像）→ 拼回酒馆 v2/v3 → 写进用户选的 URI。
 * 需要在 IO 线程上调用；失败抛异常，由调用方提示。
 */
fun exportCardHeavy(ctx: Context, uri: Uri, name: String, fmt: String) {
    val roleFile = File(AppEnv.savesDir(), name + ".json")
    val obj = if (roleFile.exists()) (JsonS.parse(roleFile.readText(Charsets.UTF_8)) as? J.Obj) ?: J.Obj() else J.Obj()
    val prompt = obj.fields["system_prompt"]?.str() ?: ""
    val cardData = obj.fields["card_data"] as? J.Obj
    // 关联世界卡（`<角色名> 的世界书`）→ 导出时写回酒馆 extensions.world（无损反向）
    val worldEntries = mutableListOf<J.Obj>()
    try {
        val wFile = File(AppEnv.worldsDir(), name + " 的世界书.json")
        if (wFile.exists()) {
            val wo = JsonS.parse(wFile.readText(Charsets.UTF_8)) as? J.Obj
            val arr = wo?.fields?.get("entries") as? J.Arr
            arr?.items?.forEach { (it as? J.Obj)?.let { e -> worldEntries.add(e) } }
        }
    } catch (_: Exception) { }
    val v2 = CardCompat.dickToV2(name, prompt, cardData, worldEntries)
    if (fmt == "json") {
        ctx.contentResolver.openOutputStream(uri)?.use {
            it.write(JsonS.stringify(v2, pretty = true).toByteArray(Charsets.UTF_8))
        }
    } else {
        var png: ByteArray? = null
        val av = File(AppEnv.savesDir(), "avatars")
        for (ext in listOf("png", "jpg", "jpeg", "webp")) {
            val f = File(av, name + "." + ext)
            if (f.exists()) { png = f.readBytes(); break }
        }
        val base = png ?: CardCompat.placeholderPng(name)
        val out = CardCompat.pngEmbedCard(base, v2) ?: base
        ctx.contentResolver.openOutputStream(uri)?.use { it.write(out) }
    }
}

/** 把一个本地文件原样写进用户选的 URI（工坊"导出"用：就是一次 copy） */
fun copyFileToUri(ctx: Context, uri: Uri, src: File) {
    ctx.contentResolver.openOutputStream(uri)?.use { it.write(src.readBytes()) }
}
