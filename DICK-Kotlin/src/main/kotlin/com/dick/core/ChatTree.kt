package com.dick.core

/**
 * 树状对话历史 —— 与 Python TreeManager 行为对齐：
 * 增删节点 / 子树裁剪 / 当前链追踪 / 数据导入导出 / 叶子修正
 */
class ChatTree {
    val nodes = mutableMapOf<String, MessageNode>()
    var rootId: String? = null
    var currentLeafId: String? = null

    fun addNode(
        role: String,
        content: String,
        parentId: String? = null,
        metadata: J = J.Null,
    ): String {
        val node = MessageNode(role = role, content = content, parentId = parentId, metadata = metadata)
        nodes[node.id] = node
        if (parentId != null && nodes.containsKey(parentId)) {
            nodes[parentId]?.childrenIds?.add(node.id)
        }
        if (rootId == null) rootId = node.id
        currentLeafId = node.id
        return node.id
    }

    fun getNode(nodeId: String?): MessageNode? = nodeId?.let { nodes[it] }

    /** 递归删除节点及其全部后代 */
    fun deleteNode(nodeId: String) {
        val node = nodes[nodeId] ?: return
        for (cid in node.childrenIds.toList()) deleteNode(cid)
        node.parentId?.let { pid ->
            nodes[pid]?.childrenIds?.remove(nodeId)
        }
        nodes.remove(nodeId)
        if (currentLeafId == nodeId) currentLeafId = node.parentId
    }

    /** 删除子树（保留节点本身，清空其后代）——与 Python delete_subtree 对齐 */
    fun deleteSubtree(nodeId: String) {
        val node = nodes[nodeId] ?: return
        for (cid in node.childrenIds.toList()) deleteNode(cid)
        node.childrenIds.clear()
    }

    /** 根 → 当前叶子 的完整链路（含 metadata，供引擎组消息） */
    fun getCurrentChainNodes(): List<MessageNode> {
        val leaf = currentLeafId ?: return emptyList()
        if (!nodes.containsKey(leaf)) return emptyList()
        val chain = mutableListOf<MessageNode>()
        var cur: MessageNode? = nodes[leaf]
        while (cur != null) {
            chain.add(cur)
            cur = cur.parentId?.let { nodes[it] }
        }
        chain.reverse()
        return chain
    }

    fun toData(): TreeData = TreeData(nodes, rootId, currentLeafId)

    fun loadData(data: TreeData) {
        nodes.clear()
        nodes.putAll(data.nodes)
        rootId = data.rootId
        currentLeafId = data.currentLeafId
    }

    /** 叶子失效时回退到根（与 Python fix_leaf 对齐） */
    fun fixLeaf() {
        if (currentLeafId == null || !nodes.containsKey(currentLeafId)) {
            currentLeafId = rootId
        }
    }
}
