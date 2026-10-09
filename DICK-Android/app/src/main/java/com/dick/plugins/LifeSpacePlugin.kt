package com.dick.plugins

import com.dick.core.ChatBridge
import com.dick.core.WorldPacks

/**
 * 生活 / 空间 / 世界卡库 —— 手机端的三个命令入口。
 *
 * 电脑端是三份插件（`life_plugin.py` / `space_plugin.py` / `worldpack_plugin.py`）；
 * 手机端合成一个：它们的共同点不是功能，而是**都要读"当前跟谁聊、用哪张世界卡"** ——
 * 那件事已经收在 `ChatBridge` 里了，拆成三份只是三份样板。
 *
 * 命令（与电脑端同名同义）：
 *   /生活                     生活层状态（年代、厨具、今天吃了什么）
 *   /在哪                     空间层状态（她此刻在哪、地图、够去哪）
 *   /在哪 <地名>              记下她去了哪（可写 /在哪 学校|骑车）
 *   /在哪 我=<地名>           记下你去了哪
 *   /世界包                   列出可装的世界卡包
 *   /世界包 看 <名字>         看一个包的参数（年代/设定/地图规模）
 *   /世界包 装 <名字> [--force]  装进 worlds/（默认不覆盖）
 */
class LifeSpacePlugin : Plugin {
    override val name = "生活/空间/世界卡库"
    override val version = "1.0"
    override val description = "吃饭（年代/厨具/食材）、不能瞬移（地图/路费）、世界卡包一键安装"
    override var enabled = true

    override fun onCommand(command: String, args: String): String? {
        return when (command) {
            "生活" -> ChatBridge.lifePanel()
            "在哪", "位置" -> whereCmd(args)
            "世界包", "worldpack", "worldpacks" -> worldPackCmd(args)
            else -> null
        }
    }

    private fun whereCmd(args: String): String {
        val a = args.trim()
        if (a.isEmpty()) return ChatBridge.spacePanel()
        // /在哪 我=学校 → 记<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌玩家位置；其余按"她去哪"
        if (a.startsWith("我=") || a.startsWith("我＝")) {
            return ChatBridge.movePlayerTo(a.substring(2).trim())
        }
        return ChatBridge.moveTo(a)
    }

    private fun worldPackCmd(args: String): String {
        val parts = args.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (parts.isEmpty() || parts[0] == "列表" || parts[0] == "list") {
            val packs = WorldPacks.listPacks()
            if (packs.isEmpty()) {
                return "世界卡库里没有卡包。\n（手机端的卡包随 APK 附带，第一次启动会释放到 " +
                        WorldPacks.DIRNAME + "/ 目录；电脑端对应 world_packs/）"
            }
            val sb = StringBuilder("世界卡库（" + packs.size + " 张）：")
            for (p in packs) {
                sb.append(10.toChar()).append("  ").append(WorldPacks.describe(p))
            }
            sb.append(10.toChar()).append("装法：/世界包 装 <名字>（重名加 --force 覆盖，覆盖前会自动备份）")
            return sb.toString()
        }
        val sub = parts[0]
        val force = parts.contains("--force")
        val nameParts = parts.drop(1).filter { it != "--force" }
        val target = nameParts.joinToString(" ")
        if (target.isEmpty()) return "用法：/世界包 装 <名字> ｜ /世界包 看 <名字> ｜ /世界包 列表"
        if (sub == "看" || sub == "show") {
            val p = WorldPacks.findPack(target)
            if (p == null) return "没找到这个世界卡包：$target"
            val sp = try {
                WorldPacks.spaceOf(
                    com.dick.core.JsonS.parse(p.path.readText(Charsets.UTF_8)) as com.dick.core.J.Obj)
            } catch (_: Exception) {
                null
            }
            val sb = StringBuilder(WorldPacks.describe(p))
            if (p.description.isNotEmpty()) sb.append(10.toChar()).append(p.description)
            sb.append(10.toChar()).append("文件：").append(p.file)
            if (sp != null) {
                sb.append(10.toChar()).append("地图自带在卡里（places/rooms/transport/links），装完空间层直接认。")
            }
            sb.append(10.toChar()).append("装法：/世界包 装 ").append(p.name)
            return sb.toString()
        }
        if (sub == "装" || sub == "install") {
            val (ok, msg) = WorldPacks.install(target, overwrite = force)
            if (!ok) return "⚠ " + msg
            // 装完让界面重扫 worlds/（否则要重启才在「世界」里看得到）
            ChatBridge.notifyWorldsChanged()
            return msg + 10.toChar() +
                    "（已放进 worlds/，在「世界」里勾上它就能用；它会带上年代与地图，生活层/空间层跟着换口径）"
        }
        return "用法：/世界包 装 <名字> [--force] ｜ /世界包 看 <名字> ｜ /世界包 列表"
    }
}
