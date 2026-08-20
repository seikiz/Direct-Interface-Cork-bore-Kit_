package com.dick.tools

import com.dick.core.AppEnv
import com.dick.core.CardCompat
import com.dick.core.ChatEngine
import com.dick.core.ChatTree
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.MessageNode
import com.dick.core.SaveFile
import com.dick.core.TreeStore
import com.dick.core.WorldBook
import com.dick.core.WorldEntry
import com.dick.core.Workshop
import com.dick.plugins.DicePlugin
import com.dick.plugins.FinancialPlugin
import com.dick.plugins.MemoryPlugin
import com.dick.plugins.SearchPlugin
import com.dick.plugins.WebFetch
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.util.zip.CRC32
import java.util.zip.Deflater

var passed = 0
var failed = 0

fun check(cond: Boolean, msg: String) {
    if (cond) {
        passed++
        println("[PASS] " + msg)
    } else {
        failed++
        println("[FAIL] " + msg)
    }
}

fun main(args: Array<String>) {
    runSelfTest()
}

fun runSelfTest() {
    println("== JSON 基础 ==")
    val n = JsonS.parse("""{"a": 95, "b": 1.5, "c": true, "d": null, "e": [1, 2], "f": {"x": "y"}}""")
    check((n as? J.Obj)?.fields?.get("a") is J.Num, "解析数字/布尔/null/数组/对象")
    val out = JsonS.stringify(n)
    check(out.contains("95") && !out.contains("95.0"), "整数 95 不变成 95.0")
    val tricky = "他说" + 34.toChar() + "你好" + 92.toChar() + "再见" + 10.toChar() + "结束😀"
    val round = JsonS.parse(JsonS.stringify(J.Str(tricky)))
    check((round as? J.Str)?.v == tricky, "引号/反斜杠/换行/emoji 转义往返")

    println("== Python 存档兼容 ==")
    val fixture = """{"name": "咲", "system_prompt": "你现在的身份是：咲", "history_tree": {"nodes": {"c1": {"id": "c1", "role": "user", "content": "怎么？你喜欢我？", "parent_id": null, "children_ids": ["c2"], "timestamp": "2026-08-13T07:49:27.585127", "metadata": {"speaker": null}}, "c2": {"id": "c2", "role": "assistant", "content": "你猜呀。", "parent_id": "c1", "children_ids": [], "timestamp": "2026-08-13T07:49:35.123456", "metadata": {"speaker": "咲"}}}, "root_id": "c1", "current_leaf_id": "c2"}}"""
    val save = (JsonS.parse(fixture) as? J.Obj)?.let { SaveFile.fromJson(it) } ?: SaveFile()
    check(save.name == "咲" && save.historyTree.nodes.size == 2, "解析 Python 存档")
    val encoded = JsonS.stringify(save.toJson(), pretty = true)
    check(encoded.contains("history_tree") && encoded.contains("parent_id") &&
        encoded.contains("children_ids") && encoded.contains("current_leaf_id"), "重编码保留 snake_case 键")

    println("== 对话树 ==")
    val tree = ChatTree()
    val sys = tree.addNode("system", "系统提示")
    val u1 = tree.addNode("user", "你好", sys)
    val a1 = tree.addNode("assistant", "你好呀", u1)
    tree.addNode("user", "在吗", a1)
    check(tree.getCurrentChainNodes().size == 4, "链追踪 4 节点")
    tree.currentLeafId = u1
    tree.addNode("assistant", "另一种回答", u1)
    check(tree.nodes[u1]!!.childrenIds.size == 2, "分支产生 2 个子节点")

    // 回归：模拟 App.doSend 的两轮对话（用户节点必须挂当前叶子）
    val t3 = ChatTree()
    t3.addNode("user", "第一句", parentId = t3.currentLeafId)
    t3.addNode("assistant", "回复一", t3.currentLeafId)
    t3.addNode("user", "第二句", parentId = t3.currentLeafId)
    check(t3.getCurrentChainNodes().size == 3, "两轮对话链完整（3 节点）")
    t3.addNode("assistant", "回复二", t3.currentLeafId)
    check(t3.getCurrentChainNodes().size == 4, "两轮对话完整链（4 节点）")
    check(t3.nodes[t3.currentLeafId]!!.content == "回复二", "第二轮回复挂在正确位置")

    println("== 世界书触发注入 ==")
    val entries = mutableListOf(
        WorldEntry(mutableListOf("龙"), "龙住在龙巢", 100, "any", 100, 3, true, false),
        WorldEntry(mutableListOf("龙巢"), "龙巢在北方", 100, "any", 100, 3, true, false),
        WorldEntry(mutableListOf("北方"), "北方的国王叫阿尔萨", 100, "any", 100, 3, true, false),
        WorldEntry(mutableListOf(), "大陆叫艾泽拉斯", 100, "any", 100, 1, true, true),
        WorldEntry(mutableListOf("秘密"), "被禁用的条目", 100, "any", 100, 1, false, false),
    )
    val inj = WorldBook.inject("一条龙出现了", entries)
    check(inj.contains("阿尔萨") && inj.contains("龙巢在北方"), "递归链（depth 3 触发两层）")
    check(inj.contains("艾泽拉斯"), "常驻条目注入")
    check(!inj.contains("被禁用"), "禁用条目不注入")
    val consts4 = mutableListOf(
        WorldEntry(mutableListOf(), "常驻A", 50, "any", 100, 1, true, true),
        WorldEntry(mutableListOf(), "常驻B", 50, "any", 100, 1, true, true),
        WorldEntry(mutableListOf(), "常驻C", 50, "any", 100, 1, true, true),
        WorldEntry(mutableListOf(), "常驻D", 50, "any", 100, 1, true, true),
    )
    check(WorldBook.inject("无关输入", consts4).split('\n').count { it.isNotBlank() } == 4, "常驻条目不受 maxEntries 上限约束")
    check(WorldBook.matches(WorldEntry(mutableListOf("a", "b"), "", match = "all"), "a b"), "match=all 全命中")
    check(WorldBook.matches(WorldEntry(mutableListOf("a", "b"), ""), "b"), "match=any 任一命中")

    println("== 酒馆角色卡兼容 ==")
    val v2 = JsonS.parse("""{"spec":"chara_card_v2","spec_version":"2.0","name":"T","data":{"name":"T","description":"d","personality":"p","scenario":"s","first_mes":"f","mes_example":"m","system_prompt":"sp","post_history_instructions":"phi","alternate_greetings":["a1"],"tags":[],"creator":"x","character_version":"1.0","extensions":{}}}""")
    val card = CardCompat.toDick(v2)
    check(card != null && card.name == "T" && card.systemPrompt.contains("【性格】") &&
        card.systemPrompt.contains("sp") && card.systemPrompt.contains("a1"), "v2 → DICK 分节拼装")
    val v2Out = CardCompat.dickToV2("T2", "x", card?.cardData)
    check(v2Out.fields["spec"]?.str() == "chara_card_v2" &&
        (v2Out.fields["data"] as? J.Obj)?.fields?.get("personality")?.str() == "p" &&
        (v2Out.fields["data"] as? J.Obj)?.fields?.get("name")?.str() == "T2", "v2 无损回导+改名")
    val bare = CardCompat.dickToV2("L2", "x", (JsonS.parse("""{"name":"L","description":"d1","personality":"p1","first_mes":"f1"}""") as? J.Obj))
    check((bare.fields["data"] as? J.Obj)?.fields?.get("name")?.str() == "L2", "裸字段块回导 data.name 同步")
    val v3 = CardCompat.dickToV2("V3b", "x", (JsonS.parse("""{"spec":"chara_card_v3","spec_version":"3.0","name":"V3","data":{"name":"V3","personality":"v3p","extensions":{}}}""") as? J.Obj))
    check(v3.fields["spec"]?.str() == "chara_card_v3", "v3 整卡保留 spec")
    // 手工构造 1x1 合法 PNG（纯 JVM，不依赖 android.graphics）
    fun makePng(): ByteArray {
        val sig = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
        val ihdr = byteArrayOf(0, 0, 0, 1, 0, 0, 0, 1, 8, 2, 0, 0, 0)
        val def = Deflater()
        def.setInput(byteArrayOf(0, 0xFF.toByte(), 0, 0))
        def.finish()
        val idat = ByteArrayOutputStream()
        val buf = ByteArray(64)
        while (!def.finished()) {
            val n = def.deflate(buf)
            if (n > 0) idat.write(buf, 0, n)
        }
        def.end()
        fun chunk(type: String, data: ByteArray): ByteArray {
            val tb = type.toByteArray(Charsets.ISO_8859_1)
            val o = ByteArrayOutputStream()
            o.write(ByteBuffer.allocate(4).putInt(data.size).array())
            o.write(tb)
            o.write(data)
            val crc = CRC32()
            crc.update(tb)
            crc.update(data)
            o.write(ByteBuffer.allocate(4).putInt(crc.value.toInt()).array())
            return o.toByteArray()
        }
        val o = ByteArrayOutputStream()
        o.write(sig)
        o.write(chunk("IHDR", ihdr))
        o.write(chunk("IDAT", idat.toByteArray()))
        o.write(chunk("IEND", byteArrayOf()))
        return o.toByteArray()
    }
    val pngBase = makePng()
    val embedded = CardCompat.pngEmbedCard(pngBase, v2Out)
    check(embedded != null && embedded.size > pngBase.size, "PNG 嵌卡生成")
    val back = CardCompat.pngExtractCard(embedded!!)
    check(back != null && (back.fields["data"] as? J.Obj)?.fields?.get("name")?.str() == "T2", "PNG 嵌卡往返（chara 块）")
    check(CardCompat.pngExtractCard(pngBase) == null, "无卡 PNG 返回 null")
    check(CardCompat.pngExtractCard(ByteArray(16)) == null, "垃圾字节安全")
    val embeddedV3 = CardCompat.pngEmbedCard(pngBase, v3, v3 = true)
    check(CardCompat.pngExtractCard(embeddedV3!!)?.fields?.get("spec")?.str() == "chara_card_v3", "ccv3 关键字往返")

    println("== 滑条 / 编辑 / 分支 ==")
    val t2 = ChatTree()
    val s2 = t2.addNode("system", "sys")
    val uu = t2.addNode("user", "第一问", s2)
    val aa = t2.addNode("assistant", "回答一", uu)
    t2.addNode("assistant", "回答二", uu)
    check(t2.siblingsOf(aa).size == 2, "同父双候选（滑条）")
    t2.setCurrentLeaf(aa)
    check(t2.getCurrentChainNodes().last().content == "回答一", "滑条切换到候选一")
    t2.editContent(aa, "改写后的回答一")
    check(t2.getNode(aa)?.content == "改写后的回答一", "AI 消息原地编辑")
    val uu2 = t2.copyNode(uu, "编辑过的第一问")
    check(uu2 != null && t2.getNode(uu2)?.parentId == s2, "用户消息编辑开新分支（保留旧分支）")
    check(t2.allLeaves().size >= 3, "叶子分支列表")

    println("== 金融史年表（1617-2026） ==")
    val histFile = File("app/src/main/assets/financial_history.json")
    check(histFile.exists(), "年表资产文件存在")
    if (histFile.exists()) {
        val histObj = JsonS.parse(histFile.readText(Charsets.UTF_8)) as? J.Obj
        val entries = (histObj?.fields?.get("entries") as? J.Arr)?.items ?: emptyList()
        check(entries.size == 49, "年表 49 条，实际 " + entries.size)
        var sectionsOk = true
        for (e in entries) {
            val text = ((e as? J.Obj)?.fields?.get("text")?.str() ?: "")
            if (!text.contains("【原因】") || !text.contains("【当时经济条件】") ||
                !text.contains("【当时科技条件】") || !text.contains("【当时政治条件】")) {
                sectionsOk = false
            }
        }
        check(sectionsOk, "每条含 原因/经济/科技/政治 四节")
        val firstYear = ((entries.firstOrNull() as? J.Obj)?.fields?.get("url")?.str() ?: "").removePrefix("finhist://")
        val lastYear = ((entries.lastOrNull() as? J.Obj)?.fields?.get("url")?.str() ?: "").removePrefix("finhist://").removePrefix("cn")
        check(firstYear.startsWith("1617") && lastYear.startsWith("2021"), "覆盖 1617 至 2021+（首 " + firstYear + " / 尾 " + lastYear + "）")
    }

    println("== 引擎（本地 mock 服务器） ==")
    val engine = ChatEngine(baseUrl = "http://127.0.0.1:8766", apiKey = "test-key", model = "test")
    val chain = listOf(MessageNode(role = "user", content = "你好"))
    val parts = StringBuilder()
    var done = false
    var ok = false
    var usageTokens = 0
    engine.send(
        chain = chain,
        systemPrompt = "测试",
        onStream = { parts.append(it) },
        onResponse = { full, usage ->
            done = true
            ok = full == "你好，世界！"
            usageTokens = usage?.totalTokens ?: 0
        },
        onError = { println("  engine error: " + it) },
    )
    var waited = 0
    while (!done && waited < 100) {
        Thread.sleep(100)
        waited++
    }
    check(done && ok, "流式拼接 = 你好，世界！")
    check(usageTokens == 15, "usage 帧解析（total=15）")
    val cand = engine.complete(chain, "测试")
    check(cand == "候选回答", "非流式 complete() = 候选回答")

    println("== 骰子 ==")
    val dice = DicePlugin()
    val d1 = dice.onCommand("r", "2d6") ?: ""
    check(d1.startsWith("🎲 2d6 = ["), "2d6 掷骰")
    val d2 = dice.onCommand("d20", "") ?: ""
    check(d2.contains("1d20"), "d20 快捷")

    println("== 网页抓取（本地页面） ==")
    val base = "http://127.0.0.1:8766/"
    val html1 = WebFetch.fetchHtml(base + "page1.html", 5000)
    val links = WebFetch.findArticleLinks(html1, base + "page1.html", 10)
    check(links.size == 2 && links[0].first.contains("新能源"), "文章链接解析")
    val nxt = WebFetch.findPagination(html1, base + "page1.html", base + "page1.html")
    check(nxt == listOf(base + "page2.html"), "翻页链接解析")
    val t1 = WebFetch.fetchText(base + "a1.html", 5000, 8000)
    check(t1.contains("风电") && !t1.contains("首页"), "正文提取（去导航噪音）")

    println("== 财报助手（本地源） ==")
    val testData = File(File(System.getProperty("user.dir")), "_kt_test_data")
    testData.deleteRecursively()
    AppEnv.dataRoot = testData.apply { mkdirs() }
    val fp = FinancialPlugin()
    fp.SOURCES = listOf("本地测试源" to (base + "page1.html"))
    val arts = fp.crawlAll(fetchBodies = true, maxPages = 3, maxTotal = 20)
    check(arts.size == 4, "深爬 4 篇（2 列表页 + 正文 + 关联文件递归），实际 " + arts.size)
    check(arts.any { "配套实施细则" in it.title }, "文内政策链接递归")
    check(arts.any { "风电" in it.text }, "正文内容正确")
    val (added, _, total) = fp.buildDb()
    check(added >= 4 && total == added, "政策库入库 " + added + " 条")
    val (added2, _, _) = fp.buildDb()
    check(added2 == 0, "增量去重（二次入库 0 新增）")
    val hits = fp.searchDb("新能源", 5)
    check(hits.isNotEmpty() && "新能源" in hits[0].title, "政策库检索")
    fp.activePreset = "财报模式"
    fp.onMessageSend("新能源板块未来走势如何")
    check(fp.contextInjection().contains("政策库自动引用"), "财报模式自动引用")

    println("== 创意工坊（本地管理） ==")
    Workshop.saveConfig("http://127.0.0.1:9999", "sk-test")
    check(Workshop.serverUrl == "http://127.0.0.1:9999" && Workshop.apiKey == "sk-test", "连接配置保存")
    Workshop.loadConfig()
    check(Workshop.serverUrl == "http://127.0.0.1:9999" && Workshop.apiKey == "sk-test", "配置持久重载")
    val wsSaves = AppEnv.savesDir()
    File(wsSaves, "ws_test_card.json").writeText("""{"name":"ws_test_card","system_prompt":"t"}""")
    File(AppEnv.worldsDir(), "ws_test_world.json").writeText("""{"name":"ws_test_world","description":"t","rules":[],"entries":[]}""")
    check(Workshop.localRoles().any { it == "ws_test_card.json" }, "本地角色列表")
    check(Workshop.localWorlds().any { it == "ws_test_world.json" }, "本地世界列表")
    check(Workshop.preview("角色卡", "ws_test_card.json").contains("ws_test_card"), "本地预览")
    check(Workshop.deleteLocal("角色卡", "ws_test_card.json"), "本地删除角色文件")
    check(Workshop.deleteLocal("世界卡", "ws_test_world.json"), "本地删除世界文件")
    check(!Workshop.deleteLocal("角色卡", "../saves/咲.json"), "路径穿越防护（basename 隔离）")
    Workshop.saveConfig("", "")
    // 自动部署：空配置时 activeServer 返回默认隧道地址（不抛异常）
    val fallback = Workshop.activeServer()
    check(fallback.isNotBlank() && fallback.startsWith("https://"), "空配置自动降级到默认服务器")

    println("== 记忆链 ==")
    val mp = MemoryPlugin()
    mp.onMessageReceived("你好", "你好呀")
    mp.onMessageReceived("在吗", "在的")
    val mr = mp.onCommand("memory", "recall 2") ?: ""
    check(mr.contains("已回溯最近 2 轮"), "记忆回溯")
    check(mp.contextInjection().contains("记忆回溯"), "回溯内容注入")

    println()
    println("自检结果：" + passed + " 通过 / " + failed + " 失败")
    if (failed > 0) kotlin.system.exitProcess(1)
}
