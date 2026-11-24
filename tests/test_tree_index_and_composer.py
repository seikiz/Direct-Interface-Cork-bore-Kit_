# -*- coding: utf-8 -*-
"""树索引与存储优化 + 交互栏逻辑优化专项测试。

覆盖：
  1. TreeIndex 增量维护：leaves / depth / by_role / by_speaker / choices / epoch_ts
  2. 倒排检索 search()：中文 2-gram / 英文词 / 角色与说话人过滤 / update_node 实时刷新 / delete_node 清理
  3. 迭代删除深树（1500 层不触发 RecursionError）+ 当前链缓存与版本号一致性
  4. 序列化 index 摘要持久化 + 缺失/损坏 index 摘要读档自动重建（100% 向后兼容）
  5. _save_tree 消除双重序列化 + 自动落盘版本去重；api_branches / api_tree 迭代与索引加速
  6. 桌面交互栏：IME 防误发、_sending 防连发、showQuoteBar XSS 转义、#quoteBar 位于 #inputbar 之前、自动撑高、粘贴图片、clearImage 重置 fileInput
  7. 安卓端：ChatTree 索引与环保护、TreeStore 原子写、ChatComposer 空输入禁用与停止按钮
"""
import io
import json
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import app_paths
from core_tree import TreeManager
from tree_index import TreeIndex, INDEX_VERSION
import html_app

ok = 0
bad = 0


def check(cond, msg):
    global ok, bad
    if cond:
        ok += 1
        print("  OK " + msg)
    else:
        bad += 1
        print("  FAIL " + msg)


def main():
    tmp = tempfile.mkdtemp(prefix="dick_tidx_")
    try:
        print("== ① TreeIndex 增量维护与 O(1) 查询 ==")
        t = TreeManager()
        r = t.add_node("system", "系统设定")
        u1 = t.add_node("user", "今天去京都赏樱花吗", parent_id=r, metadata={"is_choice": True})
        a1 = t.add_node("assistant", "好呀，清水寺的樱花开了", parent_id=u1, metadata={"speaker": "咲"})
        a2 = t.add_node("assistant", "我更想去海边看日落 sunset", parent_id=u1, metadata={"speaker": "美雪"})

        check(t.index.leaves == {a1, a2}, "叶子索引精确维护两个分支叶子: %r" % t.index.leaves)
        check(t.index.depth_of(r) == 0 and t.index.depth_of(u1) == 1 and t.index.depth_of(a1) == 2 and t.index.depth_of(a2) == 2,
              "深度索引准确")
        check(t.index.has_conversation() is True, "has_conversation O(1) 命中")
        check(t.index.by_speaker.get("咲") == {a1} and t.index.by_speaker.get("美雪") == {a2}, "说话人分桶索引准确")
        check(t.index.choices == {u1}, "GAL 选项节点索引准确")

        print("== ② 倒排检索 search() + update_node + delete_node ==")
        hits_zh = t.search_nodes("樱花")
        check({n.id for n in hits_zh} == {u1, a1}, "中文 2-gram 倒排检索命中 u1/a1")
        hits_sp = t.search_nodes("樱花", speaker="咲")
        check([n.id for n in hits_sp] == [a1], "按 speaker 过滤检索精确命中咲")
        hits_en = t.search_nodes("sunset")
        check([n.id for n in hits_en] == [a2], "英文词倒排检索命中 a2")

        # 原地更新节点：旧词移除，新词入索引
        check(t.update_node(a2, content="改去山顶看星空 stargaze"), "update_node 成功")
        check(t.search_nodes("sunset") == [], "update_node 后旧词从倒排索引清除")
        check([n.id for n in t.search_nodes("星空")] == [a2], "update_node 后新词立即检索到")

        # 删除叶子 a2 → a1 仍为叶子；再删 a1 → u1 恢复成叶子
        t.delete_node(a2)
        check(t.index.leaves == {a1} and "美雪" not in t.index.by_speaker, "删除节点后叶子与说话人索引同步清理")
        check(t.search_nodes("星空") == [], "删除节点后倒排词项同步清理")
        t.delete_node(a1)
        check(t.index.leaves == {u1}, "全部子节点删除后父节点自动恢复为叶子")

        print("== ③ 深树 1500 层迭代删除 + 链缓存一致性 ==")
        deep = TreeManager()
        cur = deep.add_node("system", "root")
        for i in range(1500):
            cur = deep.add_node("user" if i % 2 == 0 else "assistant", f"第{i}轮对话", parent_id=cur)
        c1 = deep.get_current_chain()
        c2 = deep.get_current_chain()
        check(len(c1) == 1501 and len(c2) == 1501, "1500 层深树链追踪与缓存命中")
        check(deep.index.depth_of(cur) == 1500, "深树叶子深度索引 = 1500")
        first_child = deep.nodes[deep.root_id].children_ids[0]
        deep.delete_node(first_child)
        check(len(deep.nodes) == 1 and deep.index.leaves == {deep.root_id}, "1500 层深树迭代删除不爆栈且索引归位")

        print("== ④ 序列化 index 摘要持久化 + 旧存档/坏摘要兼容 ==")
        t2 = TreeManager()
        r2 = t2.add_node("system", "sys")
        u2 = t2.add_node("user", "你好世界", parent_id=r2, metadata={"is_choice": True})
        a2b = t2.add_node("assistant", "回响", parent_id=u2, metadata={"speaker": "咲"})
        dump = t2.get_all_nodes_data()
        idx_sum = dump.get("index")
        check(isinstance(idx_sum, dict) and idx_sum.get("v") == INDEX_VERSION and idx_sum.get("node_count") == 3,
              "序列化附带 index 摘要")
        check(idx_sum.get("leaves") == [a2b] and idx_sum.get("choices") == [u2], "index 摘要含 leaves 与 choices")

        # 去掉 index（老存档）或篡改 node_count → 加载后按 nodes 自动重建
        dump_old = {k: v for k, v in dump.items() if k != "index"}
        t3 = TreeManager()
        t3.load_nodes_data(dump_old)
        check(t3.index.leaves == {a2b} and t3.index.depth_of(a2b) == 2 and t3.index.choices == {u2},
              "老存档无 index 时自动重建完整索引")
        check([n.id for n in t3.search_nodes("你好")] == [u2], "重建后倒排检索立即可用")

        print("== ⑤ 壳层 _save_tree 去重 + api_branches / api_tree 迭代加速 ==")
        _real = app_paths.get_base_dir()
        app_paths.get_base_dir = lambda: tmp
        app_paths.get_plugin_dirs = lambda: [os.path.join(_real, "plugins")]
        html_app.BASE_DIR = tmp
        app = html_app.HtmlApp()
        app.api_create_role("索引角色", json.dumps({"personality": "温和"}))
        app.api_select_roles(json.dumps(["索引角色"]))
        nu = app.core.add_user_message("测试问题")
        na1 = app.core.add_assistant_message("分支回复一", parent_id=nu)
        na2 = app.core.add_assistant_message("分支回复二", parent_id=nu)
        app.core.tree.current_leaf_id = na1

        with mock.patch.object(app.core, "get_all_nodes_data", wraps=app.core.get_all_nodes_data) as spy_ser:
            app._save_tree(wait=True)
            check(spy_ser.call_count == 1, "_save_tree 单次调用只序列化一次（不再重复调用）")
            # wait=False 且树未变 → 跳过冗余自动落盘
            app._save_tree(wait=False)
            check(spy_ser.call_count == 1, "树未变更时自动落盘去重跳过")

        branches = app.api_branches()
        check(len(branches) == 1 and branches[0]["node_id"] == na2, "api_branches 走叶子索引返回另一分支")
        tree_rows = app.api_tree()
        by_id = {x["id"]: x for x in tree_rows}
        check(by_id[na2]["branch_size"] == 1 and by_id[na1]["on_path"] is True, "迭代版 api_tree 拓扑与分支大小准确")

        print("== ⑥ 桌面交互栏逻辑与安全检查 ==")
        idx_html = io.open(os.path.join(ROOT, "web", "index.html"), encoding="utf-8").read()
        js_1b = io.open(os.path.join(ROOT, "web", "js", "chat-inline-1b.js"), encoding="utf-8").read()
        js_2 = io.open(os.path.join(ROOT, "web", "js", "chat-inline-2.js"), encoding="utf-8").read()
        check(0 < idx_html.find('id="composerStatus"') < idx_html.find('id="quoteBar"') < idx_html.find('id="inputbar"'),
              "#quoteBar 位于 #composerStatus 与 #inputbar 之间")
        check("var _sending = false;" in js_1b and "autoResizeInput(" in js_1b, "桌面 send() 含防重锁与自动撑高")
        check("escapeHtml(who)" in js_1b and "escapeHtml(q.excerpt" in js_1b, "showQuoteBar 对说话人与摘要做 XSS 转义")
        check("fi.value = ''" in js_1b and "attachImageFile(" in js_1b, "clearImage 重置 fileInput 且封装贴图逻辑")
        check("compositionstart" in js_2 and "e.isComposing" in js_2 and "paste" in js_2 and "Escape" in js_2 and "ArrowUp" in js_2,
              "输入框含 IME 防误发、剪贴板贴图、Esc 与 ArrowUp 快捷键")

        print("== ⑦ 安卓端树索引 / 原子落盘 / 交互栏结构检查 ==")
        ct_kt = io.open(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "core", "ChatTree.kt"), encoding="utf-8").read()
        ts_kt = io.open(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "core", "TreeStore.kt"), encoding="utf-8").read()
        cc_kt = io.open(os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app", "ui", "screens", "chat", "ChatComposer.kt"), encoding="utf-8").read()
        check("leafIndex" in ct_kt and "depthIndex" in ct_kt and "roleIndex" in ct_kt and "seen.add(cur.id)" in ct_kt,
              "安卓 ChatTree 含三类增量索引与环保护")
        check(".tmp" in ts_kt and "renameTo(file)" in ts_kt, "安卓 TreeStore 使用临时文件原子写")
        check("canSend = !busy && (input.isNotBlank() || hasImage)" in cc_kt and "onStop" in cc_kt,
              "安卓 ChatComposer 含空输入禁用与停止按钮")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("结果：%d 通过, %d 失败" % (ok, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
