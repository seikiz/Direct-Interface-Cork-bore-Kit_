package com.dick.app

import com.dick.core.J

/**
 * 结局预设 <-> endings 数组（**纯函数**，不碰 Compose、不碰 ChatViewModel）。
 *
 * 从 Dialogs.kt 的 BranchesDialog 一起搬出来，现在两个屏都用：
 *   · 角色卡编辑（ui/screens/cardEdit/CardEditScreen.kt）—— 机制卡里那一段"结局预设"文本框；
 *   · 回档（ui/screens/backup/BranchesScreen.kt）—— 显示/回写结局。
 *
 * Kotlin 的 private 是文件级的，跨屏共用的工具必须有自己的一份文件，
 * 否则下一个人用的时候只会复制粘贴 —— 那就是下一处"两份实现各说各话"。
 */

/** 结局预设文本 → endings 数组（每行 <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌id|结局名|事件链,逗号|好感≥|隐藏|描述） */
internal fun parseEndings(text: String): J.Arr {
    val arr = J.Arr()
    text.split("\n").forEach { line ->
        val t = line.trim()
        if (t.isEmpty()) return@forEach
        val p = t.split("|")
        if (p.size < 2) return@forEach
        val id = p[0].trim(); if (id.isEmpty()) return@forEach
        val e = J.Obj()
        e.fields["id"] = J.Str(id)
        e.fields["name"] = J.Str(p[1].trim().ifEmpty { id })
        val whenObj = J.Obj()
        p.getOrNull(2)?.trim()?.takeIf { it.isNotEmpty() }?.let { chain ->
            val ids = chain.split(",", "，").map { it.trim() }.filter { it.isNotEmpty() }
            val a = J.Arr(); ids.forEach { a.items.add(J.Str(it)) }
            whenObj.fields["events_chain"] = a
        }
        p.getOrNull(3)?.trim()?.toIntOrNull()?.let { whenObj.fields["aff_ge"] = J.Num(it.toDouble()) }
        val hidden = (p.getOrNull(4)?.trim() ?: "") in setOf("1", "yes", "hidden", "隐藏", "藏", "true")
        if (hidden) e.fields["hidden"] = J.Bool(true)
        if (whenObj.fields.isNotEmpty()) e.fields["when"] = whenObj
        p.drop(5).joinToString("|").trim().takeIf { it.isNotEmpty() }?.let { e.fields["desc"] = J.Str(it) }
        arr.items.add(e)
    }
    return arr
}

/** endings 数组 → 结局预设文本（与 parseEndings 对称） */
internal fun endingsToText(arr: J.Arr?): String {
    return arr?.items?.mapNotNull { it as? J.Obj }?.mapNotNull { e ->
        val id = e.fields["id"]?.str() ?: return@mapNotNull null
        val name = e.fields["name"]?.str() ?: id
        val whenObj = e.fields["when"] as? J.Obj
        val chain = (whenObj?.fields?.get("events_chain") as? J.Arr)?.items?.mapNotNull { it.str() }?.joinToString(",") ?: ""
        val affGe = whenObj?.fields?.get("aff_ge")?.int()?.toString() ?: ""
        val hidden = if ((e.fields["hidden"] as? J.Bool)?.v == true) "1" else ""
        val desc = e.fields["desc"]?.str() ?: ""
        listOf(id, name, chain, affGe, hidden, desc).joinToString("|")
    }?.joinToString("\n") ?: ""
}
