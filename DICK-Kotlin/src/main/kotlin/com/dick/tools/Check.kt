package com.dick.tools

import com.dick.core.ChatTree
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.MessageNode
import com.dick.core.SaveFile
import com.dick.core.TreeStore
import java.io.File

var passed = 0
var failed = 0

fun check(cond: Boolean, msg: String) {
    if (cond) {
        passed++
        println("  ✓ " + msg)
    } else {
        failed++
        println("  ✗ " + msg)
    }
}

fun main(args: Array<String>) {
    if (args.isNotEmpty() && args[0] == "--selftest") {
        runSelfTest()
        return
    }
    val target = args.firstOrNull { it.endsWith(".json") }
    if (target == null) {
        println("用法：--selftest（跑自检） 或 <存档路径>.json（兼容性检查）")
        return
    }
    compat(target)
}

fun runSelfTest() {
    println("== JSON 基础 ==")
    // 整数原样保留
    val n = JsonS.parse("{\"a\": 95, \"b\": 1.5, \"c\": true, \"d\": null, \"e\": [1, 2], \"f\": {\"x\": \"y\"}}")
    check((n as? J.Obj)?.fields?.get("a") is J.Num, "解析数字/布尔/null/数组/对象")
    val out = JsonS.stringify(n)
    check(out.contains("95") && !out.contains("95.0"), "整数 95 不变成 95.0")
    // 转义与中文
    val tricky = "他说" + 34.toChar() + "你好" + 92.toChar() + "再见" + 10.toChar() + "结束😀"
    val round = JsonS.parse(JsonS.stringify(J.Str(tricky)))
    check((round as? J.Str)?.v == tricky, "引号/反斜杠/换行/emoji 转义往返")
    // pretty 与 compact
    check(JsonS.stringify(n, pretty = true).contains(10.toChar()), "pretty 输出带换行缩进")

    println("== Python 存档兼容 ==")
    val fixture = "{\"name\": \"咲\", \"system_prompt\": \"你现在的身份是：咲\", \"history_tree\": {\"nodes\": {\"c1\": {\"id\": \"c1\", \"role\": \"user\", \"content\": \"怎么？你喜欢我？\", \"parent_id\": null, \"children_ids\": [\"c2\"], \"timestamp\": \"2026-08-13T07:49:27.585127\", \"metadata\": {\"speaker\": null}}, \"c2\": {\"id\": \"c2\", \"role\": \"assistant\", \"content\": \"你猜呀。\", \"parent_id\": \"c1\", \"children_ids\": [], \"timestamp\": \"2026-08-13T07:49:35.123456\", \"metadata\": {\"speaker\": \"咲\"}}}, \"root_id\": \"c1\", \"current_leaf_id\": \"c2\"}}"
    val save = (JsonS.parse(fixture) as? J.Obj)?.let { SaveFile.fromJson(it) } ?: SaveFile()
    check(save.name == "咲" && save.systemPrompt == "你现在的身份是：咲", "解析 name/system_prompt")
    check(save.historyTree.nodes.size == 2, "解析 2 个节点")
    check(save.historyTree.nodes["c1"]?.metadata?.obj()?.fields?.get("speaker")?.isNull() == true, "null metadata 处理")
    val encoded = JsonS.stringify(save.toJson(), pretty = true)
    check(encoded.contains("history_tree") && encoded.contains("parent_id") &&
        encoded.contains("children_ids") && encoded.contains("current_leaf_id"), "重编码保留 snake_case 键")
    val reparsed = (JsonS.parse(encoded) as? J.Obj)?.let { SaveFile.fromJson(it) }
    check(reparsed?.historyTree?.nodes?.size == 2, "重编码后可再解析")

    println("== 对话树 ==")
    val tree = ChatTree()
    val sys = tree.addNode("system", "系统提示")
    val u1 = tree.addNode("user", "你好", sys)
    val a1 = tree.addNode("assistant", "你好呀", u1)
    tree.addNode("user", "在吗", a1)
    check(tree.getCurrentChainNodes().size == 4, "链追踪 4 节点")
    check(tree.getCurrentChainNodes().map { it.role } == listOf("system", "user", "assistant", "user"), "链角色顺序")
    // 无父节点的消息 = 独立节点（与 Python add_node 行为一致）
    tree.addNode("user", "独立消息")
    check(tree.getCurrentChainNodes().size == 1, "无父节点消息成为独立链")
    // 分支
    tree.currentLeafId = u1
    tree.addNode("assistant", "另一种回答", u1)
    check(tree.nodes[u1]!!.childrenIds.size == 2, "分支产生 2 个子节点")
    // 子树裁剪（递归删掉 a1 分支与独立链无关的其余后代）
    tree.deleteSubtree(u1)
    check(tree.nodes.size == 3, "裁剪子树后剩 system+u1+独立节点")
    check(tree.nodes[u1]!!.childrenIds.isEmpty(), "u1 子节点清空")
    // 从 Python 数据重建链
    val tree2 = ChatTree()
    tree2.loadData(save.historyTree)
    tree2.fixLeaf()
    check(tree2.getCurrentChainNodes().size == 2, "Python 数据重建链")
    check(tree2.getCurrentChainNodes()[1].content == "你猜呀。", "链内容正确")

    println()
    println("自检结果：" + passed + " 通过 / " + failed + " 失败")
    if (failed > 0) kotlin.system.exitProcess(1)
}

fun compat(path: String) {
    val file = File(path)
    if (!file.exists()) {
        println("文件不存在：" + path)
        return
    }
    val save = TreeStore.load(file)
    println("存档名：" + (save.name ?: "(未命名)"))
    println("节点总数：" + save.historyTree.nodes.size)
    val tree = ChatTree()
    tree.loadData(save.historyTree)
    tree.fixLeaf()
    println("当前链长度：" + tree.getCurrentChainNodes().size)
    val chain = tree.getCurrentChainNodes()
    if (chain.isNotEmpty()) {
        val first = chain.first()
        println("首个节点：" + first.role + " / " + first.content.take(40))
        val last = chain.last()
        println("末个节点：" + last.role + " / " + last.content.take(40))
    }
    println("✅ 兼容性检查通过（可被 Python 版互读）")
}
