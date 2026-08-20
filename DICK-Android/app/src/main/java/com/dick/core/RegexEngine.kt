package com.dick.core

import java.io.File

/**
 * 正则管道（ST 风格清洗/格式化）。
 * 规则格式（与桌面版一致）：{id, name, pattern, replace, scope(ai/user/both), enabled}
 * 替换串用 Python 风格 \1 捕获组（内部转成 Kotlin $1）。
 * 应用时机：消息写入树节点之前 → 树里存转换后文本，回溯/分支天然一致。
 */
object RegexEngine {

    fun loadGlobal(): List<J.Obj> {
        val f = File(AppEnv.dataRoot, "regex_rules.json")
        if (!f.exists()) return emptyList()
        return try {
            ((JsonS.parse(f.readText(Charsets.UTF_8)) as? J.Arr)?.items ?: emptyList())
                .mapNotNull { it as? J.Obj }
        } catch (_: Exception) {
            emptyList()
        }
    }

    /** 应用规则（角色卡规则 + 全局规则，角色卡优先） */
    fun apply(text: String, scope: String, roleRules: List<J.Obj>, globalRules: List<J.Obj>): String {
        if (text.isBlank()) return text
        var t = text
        for (rule in roleRules + globalRules) {
            if (rule.fields["enabled"]?.bool() == false) continue
            val p = rule.fields["pattern"]?.str()?.takeIf { it.isNotBlank() } ?: continue
            val r = rule.fields["replace"]?.str() ?: ""
            val s = rule.fields["scope"]?.str() ?: "both"
            if (s != scope && s != "both") continue
            try {
                // Python 风格 \1 → Kotlin $1
                var repl = r
                for (i in 1..9) repl = repl.replace("\\$i", "$$i")
                t = Regex(p).replace(t, repl)
            } catch (_: Exception) {
            }
        }
        return t
    }
}
