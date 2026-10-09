package com.dick.core

import android.content.res.AssetManager
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/**
 * WorldPacks —— 世界卡库的手机端（`world_packs.py` 的手机端）。
 *
 * 手机上没有"随手往 worlds/ 丢卡"的便利，所以库里的一等公民是**随 APK 附带的卡包**
 * （`assets/world_packs/` 下的 json，与电脑端 `world_packs/` 是同一批文件，由
 * `tools/gen_parity.py` 同步 —— 只留一份真相）。启动时把它们释放到
 * `AppEnv.dir("world_packs")`（纯文件，逻辑层不必认识 AssetManager），
 * `/世界包 装 <名字>` 再拷进 `worlds/`。
 *
 * 装包语义与电脑端一致：**默认不覆盖**同名世界卡（用户可能已经改过），
 * 要覆盖得显式 force，那时先留一份 `.bak-<时间>` 再原子写入。
 */
object WorldPacks {

    const val DIRNAME = "world_packs"

    data class Pack(
        val file: String,
        val path: File,
        val name: String,
        val description: String,
        val era: String,
        val kind: String,
        val region: String,
        val places: Int,
        val rooms: Int,
        val dir: File,
    )

    /** 卡包目录：先用户目录（可以自己丢包<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌进去），再 `extra`（测试用）。 */
    fun packDirs(extra: File? = null): List<File> {
        val out = ArrayList<File>()
        extra?.let { out.add(it) }
        out.add(AppEnv.dir(DIRNAME))
        return out.distinctBy { it.absolutePath }
    }

    private fun readCard(path: File): J.Obj {
        val o = JsonS.parse(path.readText(Charsets.UTF_8)) as? J.Obj
            ?: throw IllegalArgumentException("不是有效的世界卡（不是 JSON 对象）")
        val name = (o.fields["name"] as? J.Str)?.v?.trim() ?: ""
        if (name.isEmpty()) throw IllegalArgumentException("不是有效的世界卡（缺 name）")
        return o
    }

    /** 把 `params.space` 解出来（字符串或对象都认）。 */
    fun spaceOf(card: J.Obj): J.Obj? {
        val params = card.fields["params"] as? J.Obj ?: return null
        return when (val sp = params.fields["space"]) {
            is J.Obj -> sp
            is J.Str -> try {
                JsonS.parse(sp.v) as? J.Obj
            } catch (_: Exception) {
                null
            }
            else -> null
        }
    }

    private fun str(o: J.Obj?, key: String): String = ((o?.fields?.get(key)) as? J.Str)?.v ?: ""

    private fun arrSize(o: J.Obj?, key: String): Int = (o?.fields?.get(key) as? J.Arr)?.items?.size ?: 0

    /** 列出所有可装的卡包（同名的以先出现的目录为准）。 */
    fun listPacks(extra: File? = null): List<Pack> {
        val out = ArrayList<Pack>()
        val seen = HashSet<String>()
        for (d in packDirs(extra)) {
            if (!d.isDirectory) continue
            val files = d.listFiles()?.sortedBy { it.name } ?: continue
            for (f in files) {
                if (!f.isFile || !f.name.endsWith(".json") || f.name.startsWith(".")) continue
                val card = try {
                    readCard(f)
                } catch (e: Exception) {
                    println("[world_packs] 跳过坏卡包 " + f.name + ": " + e.message)
                    continue
                }
                val name = str(card, "name")
                if (name in seen) continue
                seen.add(name)
                val sp = spaceOf(card)
                out.add(Pack(
                    file = f.name,
                    path = f,
                    name = name,
                    description = str(card, "description"),
                    era = str(card.fields["params"] as? J.Obj, "era"),
                    kind = str(card.fields["params"] as? J.Obj, "era_kind"),
                    region = str(card.fields["params"] as? J.Obj, "region"),
                    places = arrSize(sp, "places"),
                    rooms = arrSize(sp, "rooms"),
                    dir = d,
                ))
            }
        }
        return out
    }

    /** 按名字找（先精确，再退一步"包含"）——与电脑端同一套宽松规则。 */
    fun findPack(name: String?, extra: File? = null): Pack? {
        val want = name?.trim() ?: ""
        if (want.isEmpty()) return null
        val packs = listPacks(extra)
        for (p in packs) {
            if (p.name == want || p.file == want || p.file.removeSuffix(".json") == want) return p
        }
        for (p in packs) if (p.name.contains(want)) return p
        return null
    }

    fun safeName(name: String?): String {
        val cleaned = (name ?: "").trim().replace(Regex("[\\\\/:*?\"<>|]"), "_")
        return cleaned.ifEmpty { "world" }
    }

    fun worldsDir(): File = AppEnv.worldsDir()

    /**
     * 把卡包装进世界卡目录。返回 (成功, 给人看的话)。
     * 默认不覆盖；force 时先备份再原子写入。
     */
    fun install(name: String?, targetDir: File? = null, overwrite: Boolean = false): Pair<Boolean, String> {
        val pack = findPack(name) ?: return false to "没找到这个世界卡包：$name"
        val dstDir = targetDir ?: worldsDir()
        if (!dstDir.isDirectory && !dstDir.mkdirs()) {
            return false to "世界卡目录建不出来：${dstDir.absolutePath}"
        }
        val dst = File(dstDir, safeName(pack.name) + ".json")
        if (dst.exists() && !overwrite) {
            return false to ("已经有一张同名的世界卡了（${dst.name}）。要覆盖请用 /世界包 装 <名字> --force")
        }
        return try {
            if (dst.exists()) backup(dst)
            val card = readCard(pack.path)
            val tmp = File(dstDir, dst.name + ".tmp")
            tmp.writeText(JsonS.stringify(card, pretty = true), Charsets.UTF_8)
            if (!tmp.renameTo(dst)) {
                dst.delete()
                if (!tmp.renameTo(dst)) throw IllegalStateException("改名失败")
            }
            true to "已装入：${pack.name} → ${dst.name}"
        } catch (e: Exception) {
            false to "装包失败：${e.message}"
        }
    }

    /** 覆盖前的保命动作：留一份带时间戳的备份，写失败也还有原文件。 */
    fun backup(file: File): File? {
        return try {
            val ts = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"))
            val bak = File(file.parentFile, file.name + ".bak-" + ts)
            file.copyTo(bak, overwrite = true)
            bak
        } catch (_: Exception) {
            null
        }
    }

    /** 人话摘要（给命令面板用）。 */
    fun describe(pack: Pack?): String {
        if (pack == null) return ""
        val bits = ArrayList<String>()
        if (pack.era.isNotEmpty()) bits.add("年代 " + pack.era)
        if (pack.kind.isNotEmpty()) bits.add("设定 " + pack.kind)
        if (pack.region.isNotEmpty()) bits.add("地域 " + pack.region)
        if (pack.places > 0) bits.add("${pack.places} 个地点")
        if (pack.rooms > 0) bits.add("${pack.rooms} 间屋")
        return pack.name + "｜" + (if (bits.isEmpty()) "（无参数）" else bits.joinToString("、"))
    }

    /**
     * 首次启动把 APK 里的卡包释放到 `world_packs/`（已存在的不动 —— 用户改过的以用户的为准）。
     * 必须在后台线程调（读 assets + 写盘）。
     */
    fun seedFromAssets(assets: AssetManager): Int {
        val dir = AppEnv.dir(DIRNAME)
        val names = try {
            assets.list(DIRNAME)?.toList() ?: emptyList()
        } catch (_: Exception) {
            emptyList()
        }
        var n = 0
        for (fn in names) {
            if (!fn.endsWith(".json")) continue
            val dst = File(dir, fn)
            if (dst.exists()) continue
            try {
                assets.open("$DIRNAME/$fn").use { input ->
                    dst.outputStream().use { out -> input.copyTo(out) }
                }
                n++
            } catch (e: Exception) {
                println("[world_packs] 释放卡包失败 " + fn + ": " + e.message)
            }
        }
        return n
    }
}
