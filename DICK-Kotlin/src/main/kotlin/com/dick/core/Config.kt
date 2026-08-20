package com.dick.core

class ConfigStore {
    var data: AppConfig = AppConfig()

    fun load() {
        val f = AppPaths.configFile()
        if (!f.exists()) return
        try {
            val root = JsonS.parse(f.readText(Charsets.UTF_8))
            (root as? J.Obj)?.let { data = AppConfig.fromJson(it) }
        } catch (_: Exception) {
            // 配置损坏时保持默认值
        }
    }

    fun save() {
        try {
            AppPaths.configFile().writeText(
                JsonS.stringify(data.toJson(), pretty = true),
                Charsets.UTF_8,
            )
        } catch (_: Exception) {
        }
    }
}
