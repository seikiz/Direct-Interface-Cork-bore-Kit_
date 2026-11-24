package com.dick.core

/**
 * 树状对话历史 —— 与 Python TreeManager 行为对齐：
 * 增删节点 / 子树裁剪 / 当前链追踪 / 数据导入导出 / 叶子修正
 */
class ChatTree {
    val nodes = mutableMapOf<String, MessageNode>()
    var rootId: String? = null
    var currentLeafId: String? = null

    /** 增量内存索引：叶子集合 / 节点深度 / 按角色分桶（与 Python TreeIndex 对齐） */
    val leafIndex = linkedSetOf<String>()
    val depthIndex = hashMapOf<String, Int>()
    val roleIndex = hashMapOf<String, MutableSet<String>>()

    fun addNode(
        role: String,
        content: String,
        parentId: String? = null,
        metadata: J = J.Null,
    ): String {
        val node = MessageNode(role = role, content = content, parentId = parentId, metadata = metadata)
        nodes[node.id] = node
        val parent = if (parentId != null) nodes[parentId] else null
        if (parent != null) {
            parent.childrenIds.add(node.id)
            leafIndex.remove(parent.id)
            depthIndex[node.id] = (depthIndex[parent.id] ?: 0) + 1
        } else {
            depthIndex[node.id] = 0
        }
        leafIndex.add(node.id)
        roleIndex.getOrPut(role) { linkedSetOf() }.add(node.id)
        if (rootId == null) rootId = node.id
        currentLeafId = node.id
        return node.id
    }

    fun getNode(nodeId: String?): MessageNode? = nodeId?.let { nodes[it] }

    /** 迭代栈删除节点及其全部后代（防深树栈溢出）并同步更新索引 */
    fun deleteNode(nodeId: String) {
        val rootDel = nodes[nodeId] ?: return
        val parent = rootDel.parentId?.let { nodes[it] }
        parent?.childrenIds?.remove(nodeId)
        val stack = ArrayDeque<String>()
        val seen = HashSet<String>()
        stack.addLast(nodeId)
        while (stack.isNotEmpty()) {
            val curId = stack.removeLast()
            if (!seen.add(curId)) continue
            val n = nodes[curId] ?: continue
            for (cid in n.childrenIds) stack.addLast(cid)
        }
        val leafDeleted = currentLeafId in seen
        for (rid in seen) {
            val removed = nodes.remove(rid)
            leafIndex.remove(rid)
            depthIndex.remove(rid)
            if (removed != null) roleIndex[removed.role]?.remove(rid)
        }
        if (parent != null && parent.childrenIds.isEmpty()) leafIndex.add(parent.id)
        if (leafDeleted) currentLeafId = rootDel.parentId
        if (rootId in seen) rootId = null
    }

    /** 删除子树（保留节点本身，清空其后代）——与 Python delete_subtree 对齐 */
    fun deleteSubtree(nodeId: String) {
        val node = nodes[nodeId] ?: return
        for (cid in node.childrenIds.toList()) deleteNode(cid)
        node.childrenIds.clear()
        leafIndex.add(nodeId)
    }

    /** 根 → 当前叶子 的完整链路（含环保护与 metadata，供引擎组消息） */
    fun getCurrentChainNodes(): List<MessageNode> {
        val leaf = currentLeafId ?: return emptyList()
        return chainUpTo(leaf)
    }

    /** 兄弟节点（同父），含自身 */
    fun siblingsOf(nodeId: String): List<MessageNode> {
        val node = nodes[nodeId] ?: return emptyList()
        val pid = node.parentId ?: return emptyList()
        val parent = nodes[pid] ?: return emptyList()
        return parent.childrenIds.mapNotNull { nodes[it] }
    }

    /** 根 → 指定节点（含）的链路（带环保护，防止坏存档死循环） */
    fun chainUpTo(nodeId: String): List<MessageNode> {
        if (!nodes.containsKey(nodeId)) return emptyList()
        val chain = mutableListOf<MessageNode>()
        val seen = HashSet<String>()
        var cur: MessageNode? = nodes[nodeId]
        while (cur != null && seen.add(cur.id)) {
            chain.add(cur)
            cur = cur.parentId?.let { nodes[it] }
        }
        chain.reverse()
        return chain
    }

    /** 切换当前叶子（切换滑条/分支） */
    fun setCurrentLeaf(nodeId: String) {
        if (nodes.containsKey(nodeId)) currentLeafId = nodeId
    }

    /** 原地修改节点文本 */
    fun editContent(nodeId: String, content: String) {
        nodes[nodeId]?.let { it.content = content }
    }

    /** 在指定节点同父位置新建副本（用户消息编辑重发），返回新节点 id */
    fun copyNode(nodeId: String, newContent: String): String? {
        val node = nodes[nodeId] ?: return null
        return addNode(node.role, newContent, node.parentId, node.metadata)
    }

    /** 所有叶子节点（直接走叶子索引 O(L)） */
    fun allLeaves(): List<MessageNode> = leafIndex.mapNotNull { nodes[it] }

    /** 节点深度（O(1) 读索引） */
    fun depthOf(nodeId: String): Int = depthIndex[nodeId] ?: 0

    /** 按关键词与可选角色检索历史节点 */
    fun search(query: String, role: String? = null, limit: Int = 20): List<MessageNode> {
        val q = query.trim().lowercase()
        val pool = if (role != null) roleIndex[role]?.mapNotNull { nodes[it] } ?: emptyList()
        else nodes.values.filter { it.role != "system" }
        val matched = if (q.isEmpty()) pool else pool.filter { it.content.lowercase().contains(q) }
        return matched.sortedByDescending { it.timestamp }.take(limit.coerceAtLeast(1))
    }

    /** 从现有 nodes 全量重建内存索引（加载存档后调用） */
    fun rebuildIndex() {
        leafIndex.clear()
        depthIndex.clear()
        roleIndex.clear()
        if (nodes.isEmpty()) return
        val roots = mutableListOf<String>()
        rootId?.takeIf { nodes.containsKey(it) }?.let { roots.add(it) }
        for ((nid, n) in nodes) {
            if ((n.parentId == null || !nodes.containsKey(n.parentId)) && nid !in roots) roots.add(nid)
        }
        val visited = HashSet<String>()
        val queue = ArrayDeque<Pair<String, Int>>()
        roots.forEach { queue.addLast(it to 0) }
        while (queue.isNotEmpty()) {
            val (nid, d) = queue.removeFirst()
            if (!visited.add(nid)) continue
            val n = nodes[nid] ?: continue
            depthIndex[nid] = d
            if (n.childrenIds.isEmpty()) leafIndex.add(nid)
            roleIndex.getOrPut(n.role) { linkedSetOf() }.add(nid)
            for (cid in n.childrenIds) {
                if (cid !in visited && nodes.containsKey(cid)) queue.addLast(cid to d + 1)
            }
        }
        for ((nid, n) in nodes) {
            if (nid in visited) continue
            depthIndex[nid] = 0
            if (n.childrenIds.isEmpty()) leafIndex.add(nid)
            roleIndex.getOrPut(n.role) { linkedSetOf() }.add(nid)
        }
    }

    fun toData(): TreeData = TreeData(nodes, rootId, currentLeafId)

    fun loadData(data: TreeData) {
        data.repairLinks()      // 老存档可能只有 parent_id：先把关系补全，否则分支图只剩一个节点
        nodes.clear()
        nodes.putAll(data.nodes)
        rootId = data.rootId
        currentLeafId = data.currentLeafId
        rebuildIndex()
    }

    /** 叶子失效时回退到根（与 Python fix_leaf 对齐） */
    fun fixLeaf() {
        if (currentLeafId == null || !nodes.containsKey(currentLeafId)) {
            currentLeafId = rootId
        }
    }
}
