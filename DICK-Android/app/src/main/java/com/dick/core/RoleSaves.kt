package com.dick.core

import java.io.File
import java.util.UUID

/** 角色卡·多存档：一个存档点（含对<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌话树 + 机制状态 + 进度时间戳） */
class SaveSlot(
    val id: String = "s-" + UUID.randomUUID().toString().substring(0, 10),
    var label: String = "未命名存档",
    var createdAt: String = "",
    var updatedAt: String = "",
    var tree: TreeData = TreeData(),
    var mechState: J.Obj? = null,
) {
    /** 正式聊天条数（不含系统节点） */
    fun progress(): Int = tree.nodes.values.count { it.role != "system" }

    fun toJson(): J.Obj {
        val o = J.Obj()
        o.fields["id"] = J.strOr(id)
        o.fields["label"] = J.strOr(label)
        o.fields["created_ts"] = J.strOr(createdAt)
        o.fields["updated_ts"] = J.strOr(updatedAt)
        o.fields["history_tree"] = tree.toJson()
        val ms = mechState
        if (ms != null) o.fields["mechanics_state"] = ms
        return o
    }

    companion object {
        fun fromJson(o: J.Obj): SaveSlot = SaveSlot(
            id = (o.fields["id"] as? J.Str)?.v ?: ("s-" + UUID.randomUUID().toString().substring(0, 10)),
            label = (o.fields["label"] as? J.Str)?.v ?: "未命名存档",
            createdAt = (o.fields["created_ts"] as? J.Str)?.v ?: "",
            updatedAt = (o.fields["updated_ts"] as? J.Str)?.v ?: "",
            tree = (o.fields["history_tree"] as? J.Obj)?.let { TreeData.fromJson(it) } ?: TreeData(),
            mechState = o.fields["mechanics_state"] as? J.Obj,
        )
    }
}

/** 角色卡·多存档 的磁盘读写：saves/.role_saves/_saves_<角色>.json 存数组 */
object RoleSaves {
    private fun safe(name: String): String =
        name.replace('\\', '_').replace('/', '_').replace(':', '_').replace('*', '_')
            .replace('?', '_').replace('<', '_').replace('>', '_').replace('|', '_')

    fun fileFor(role: String): File =
        File(File(AppEnv.savesDir(), ".role_saves").apply { mkdirs() }, "_saves_" + safe(role) + ".json")

    fun load(role: String): MutableList<SaveSlot> {
        try {
            val f = fileFor(role)
            if (!f.exists()) return mutableListOf()
            val arr = JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Arr ?: return mutableListOf()
            val out = mutableListOf<SaveSlot>()
            arr.items.forEach { (it as? J.Obj)?.let { s -> out.add(SaveSlot.fromJson(it)) } }
            return out
        } catch (_: Exception) {
            return mutableListOf()
        }
    }

    fun save(role: String, slots: List<SaveSlot>) {
        try {
            val f = fileFor(role)
            f.parentFile?.mkdirs()
            val arr = J.Arr(slots.map { it.toJson() }.toMutableList())
            f.writeText(JsonS.stringify(arr), Charsets.UTF_8)
        } catch (_: Exception) {
        }
    }

    fun summary(s: SaveSlot): J.Obj {
        val o = J.Obj()
        o.fields["id"] = J.strOr(s.id)
        o.fields["label"] = J.strOr(s.label)
        o.fields["created_ts"] = J.strOr(s.createdAt)
        o.fields["updated_ts"] = J.strOr(s.updatedAt)
        o.fields["progress"] = J.Num(s.progress().toDouble(), s.progress().toString())
        return o
    }
}
