# ============================================================
#   swipe_plugin.py - 多候选回复（Swipe）插件 v1.0
#
#   酒馆式 Swipe：对同一条用户消息生成多个候选 AI 回复，
#   可随时循环切换，树状历史天然保存所有分支。
#
#   命令：
#     /swipe          无候选则生成，已有候选则切换到下一个
#     /swipe back     切换到上一个候选
#     /swipe 2        跳到第 2 个候选
#
#   核心依赖：core.generate_candidate / core.refresh_chat（主界面注入）
# ============================================================

import threading
import time

from plugin_base import PluginBase


class SwipePlugin(PluginBase):
    name = "多候选回复"
    version = "1.0"
    description = "酒馆式 Swipe：一条消息生成多个候选回复，/swipe 循环切换"
    author = "seiki"
    enabled = True

    # 插件坞按钮：点击 = 生成/换一个候选
    ui_buttons = [
        {"type": "insert", "label": "🎲 换一换", "text": "/swipe"},
    ]

    # 声明式设置
    settings_schema = [
        {"key": "candidate_count", "label": "候选回复数量", "type": "int",
         "default": 3, "min": 1, "max": 5},
    ]

    def __init__(self, core):
        super().__init__(core)
        self._pending = 0          # 剩余待生成的候选数
        self._branch_user = None   # 当前分支点（用户消息节点 id）

    def on_load(self):
        print("[多候选回复] 已加载：发送 /swipe 生成并切换候选回复")

    def on_message_send(self, user_input):
        # 新的用户消息 = 新的分支点，旧候选状态作废
        self._pending = 0
        self._branch_user = None
        return user_input

    # ---------- 树工具 ----------
    def _last_user_node(self):
        core = self.core
        nid = core.tree.current_leaf_id
        while nid and nid in core.tree.nodes:
            node = core.tree.nodes[nid]
            if node.role == 'user':
                return node
            nid = node.parent_id
        return None

    def _candidates(self, user_node):
        core = self.core
        return [cid for cid in user_node.children_ids
                if cid in core.tree.nodes and core.tree.nodes[cid].role == 'assistant']

    # ---------- 命令 ----------
    def on_command(self, command, args):
        if command not in ("swipe", "s"):
            return None
        arg = args.strip().lower()
        core = self.core
        if not core.client:
            return "⚠️ 请先启动聊天", False

        user_node = self._last_user_node()
        if not user_node:
            return "⚠️ 尚未找到可生成候选的用户消息", False
        cands = self._candidates(user_node)
        current = core.tree.current_leaf_id

        # /swipe back —— 上一个候选
        if arg in ("back", "prev", "上", "上一个"):
            if not cands:
                return "⚠️ 还没有候选回复，先输入 /swipe 生成", False
            if current not in cands:
                idx = -1
            else:
                idx = cands.index(current)
            nxt = cands[(idx - 1) % len(cands)]
            core.tree.current_leaf_id = nxt
            return self._show((idx - 1) % len(cands) + 1, len(cands)), False

        # /swipe 2 —— 跳到指定候选
        if arg.isdigit():
            n = int(arg)
            if 1 <= n <= len(cands):
                core.tree.current_leaf_id = cands[n - 1]
                return self._show(n, len(cands)), False
            return f"⚠️ 候选编号范围 1~{len(cands)}", False

        # /swipe —— 候选不足则生成，否则切换下一个
        target = int(self.get_setting("candidate_count", 3))
        if len(cands) >= target:
            if current in cands:
                idx = cands.index(current)
            else:
                idx = -1
            nxt = cands[(idx + 1) % len(cands)]
            core.tree.current_leaf_id = nxt
            return self._show((idx + 1) % len(cands) + 1, len(cands)), False

        to_gen = target - len(cands)
        self._branch_user = user_node.id
        self._pending = to_gen
        self._gen_next()
        return f"🎲 正在生成 {to_gen} 个候选回复，完成后自动显示...", False

    def _show(self, idx, total, prefix="✅"):
        self.core.refresh_chat()
        return f"{prefix} 候选 {idx}/{total}（/swipe 换下一个，/swipe back 回上一个）"

    # ---------- 顺序生成候选 ----------
    def _gen_next(self):
        core = self.core
        if self._pending <= 0:
            # 全部生成完：当前叶子已是最后生成的新候选，刷新显示即可
            user_node = core.tree.nodes.get(self._branch_user)
            if user_node:
                cands = self._candidates(user_node)
                if cands:
                    core.tree.current_leaf_id = cands[-1]
                    core.refresh_chat()
                    print(f"[多候选回复] ✅ 已生成 {len(cands)} 个候选回复")
            self._pending = 0
            return
        self._pending -= 1
        core.generate_candidate(self._branch_user,
                                on_response=self._on_candidate_done,
                                on_error=self._on_candidate_error)

    def _on_candidate_done(self, ai_reply, usage):
        # 回调发生时 is_processing 尚未复位（finally 后置），延迟到空闲再生成下一个
        threading.Thread(target=self._gen_next_deferred, daemon=True).start()

    def _gen_next_deferred(self):
        core = self.core
        deadline = time.time() + 60
        while core.is_processing and time.time() < deadline:
            time.sleep(0.02)
        self._gen_next()

    def _on_candidate_error(self, err):
        print(f"[多候选回复] 候选生成失败: {err}")
        self._pending = 0
