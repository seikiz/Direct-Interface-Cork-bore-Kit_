# ============================================================
#   memory_chain_plugin.py - 记忆链扩容插件（JSON 串口扩容）v1.0
#
#   原理：当存档 JSON 超过阈值（"爆满"）时，自动把完整数据归档到
#   memory/ 目录形成记忆链（角色.part1.json、part2.json ...），
#   当前 JSON 只保留最近的对话节点继续工作；旧数据永不丢失，
#   可随时通过命令调取，并自动生成压缩记忆注入新对话。
#
#   命令：
#     /memory              查看记忆链状态
#     /memory recall [N]   回溯最近 N 条历史消息（下次发送时附带）
#     /memory summary      查看当前压缩记忆摘要
#     /memory clear        清除待回溯内容
# ============================================================

import json
import os
import re
import shutil
import threading
from datetime import datetime

from plugin_base import PluginBase
import app_paths


class MemoryChainPlugin(PluginBase):
    name = "记忆链扩容"
    version = "1.0"
    description = "存档过大自动归档成链，生成压缩记忆，历史不丢失"
    author = "seiki"
    enabled = True

    # 声明式 UI 模组：插件坞快捷记忆按钮
    ui_buttons = [
        {"type": "insert", "label": "🧠 记忆", "text": "/memory"},
        {"type": "insert", "label": "⏪ 回溯", "text": "/memory recall "},
    ]

    # ---------- 可调参数 ----------
    MAX_BYTES = 1_500_000      # 存档超过该字节数触发归档（1.5MB）
    KEEP_NODES = 150           # 归档后当前 JSON 保留的最近节点数
    SUMMARY_CHARS = 400        # 压缩记忆摘要目标字数
    RECALL_TAIL = 30           # /memory recall 默认回溯条数
    CONTEXT_CAP = 16000        # 生成摘要时送入 LLM 的最大字符数

    def __init__(self, core):
        super().__init__(core)
        base = app_paths.get_base_dir()  # exe 模式跟随 exe 目录，源码模式为工程根
        self.save_dir = os.path.join(base, "saves")
        self.memory_dir = os.path.join(base, "memory")
        os.makedirs(self.memory_dir, exist_ok=True)
        self.chain_file = os.path.join(self.memory_dir, "chain.json")
        self.pending_recall = []   # 待回溯的历史消息 [(role, content), ...]

    def on_load(self):
        print("[记忆链扩容] 已加载：存档超过 %.1fMB 自动归档并生成压缩记忆" % (self.MAX_BYTES / 1_000_000))

    # ============================================================
    # 基础工具
    # ============================================================
    def _active_save(self):
        """找到最近修改的角色存档（主程序每次回复后保存活动角色）"""
        files = [f for f in os.listdir(self.save_dir) if f.endswith(".json")]
        if not files:
            return None
        files.sort(key=lambda f: os.path.getmtime(os.path.join(self.save_dir, f)), reverse=True)
        return os.path.join(self.save_dir, files[0])

    def _stem(self, path):
        return os.path.splitext(os.path.basename(path))[0]

    def _load_chain(self):
        try:
            with open(self.chain_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_chain(self, chain):
        tmp = self.chain_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(chain, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.chain_file)

    def _safe_stem(self, stem):
        return re.sub(r'[\\/:*?"<>|]', "_", stem)

    # ============================================================
    # 核心：自动归档扩容
    # ============================================================
    def on_message_received(self, user_input, ai_reply):
        """每次 AI 回复后检查存档是否爆满，必要时归档"""
        try:
            self._maybe_rotate()
        except Exception as e:
            print(f"[记忆链扩容] 归档检查失败: {e}")

    def _maybe_rotate(self):
        path = self._active_save()
        if not path or not os.path.exists(path):
            return
        if os.path.getsize(path) < self.MAX_BYTES:
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        nodes = data.get("history_tree", {}).get("nodes", {})
        if len(nodes) <= self.KEEP_NODES + 20:
            return  # 节点太少，归档没有意义

        stem = self._stem(path)
        safe = self._safe_stem(stem)

        # 1. 归档：当前完整 JSON → memory/<角色>.part<N>.json
        chain = self._load_chain()
        parts = chain.setdefault(safe, [])
        seq = len(parts) + 1
        archive_path = os.path.join(self.memory_dir, f"{safe}.part{seq}.json")
        shutil.move(path, archive_path)
        parts.append({
            "part": seq,
            "path": os.path.basename(archive_path),
            "nodes": len(nodes),
            "size": os.path.getsize(archive_path),
            "time": datetime.now().isoformat(),
        })
        self._save_chain(chain)

        # 2. 精简内存树：只保留最近 KEEP_NODES 个节点 + 系统节点
        kept = self._trim_tree(keep=self.KEEP_NODES)

        # 3. 立即写回一个新的"当前" JSON（保留除历史树外的所有字段）
        new_data = {k: v for k, v in data.items() if k != "history_tree"}
        new_data["history_tree"] = self.core.get_all_nodes_data()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)

        print(f"[记忆链扩容] 📦 「{stem}」已归档第 {seq} 部分（{len(nodes)} 节点，"
              f"当前保留 {kept} 节点），历史未丢失")

        # 4. 后台生成压缩记忆摘要（不阻塞界面）
        threading.Thread(target=self._build_summary, args=(stem, safe, archive_path),
                         daemon=True).start()

    def _trim_tree(self, keep):
        """精简内存树：从当前叶子向上保留最近 keep 个节点 + 所有 system 节点"""
        tree = self.core.tree
        keep_ids = set()
        node = tree.nodes.get(tree.current_leaf_id)
        count = 0
        while node and count < keep:
            keep_ids.add(node.id)
            node = tree.nodes.get(node.parent_id) if node.parent_id else None
            count += 1
        for nid, n in tree.nodes.items():
            if n.role == "system":
                keep_ids.add(nid)
        for nid in list(tree.nodes):
            if nid not in keep_ids:
                del tree.nodes[nid]
        for n in tree.nodes.values():
            n.children_ids = [c for c in n.children_ids if c in tree.nodes]
        tree.fix_leaf()
        return len(tree.nodes)

    # ============================================================
    # 压缩记忆摘要（后台线程）
    # ============================================================
    def _archive_chain_messages(self, archive_path):
        """按对话顺序提取归档文件中的 user/assistant 消息"""
        with open(archive_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tree = data.get("history_tree", {})
        nodes = tree.get("nodes", {})
        leaf_id = tree.get("current_leaf_id")
        if not leaf_id or leaf_id not in nodes:
            return []
        chain = []
        nid = leaf_id
        while nid and nid in nodes:
            chain.append(nodes[nid])
            nid = nodes[nid].get("parent_id")
        chain.reverse()
        return [(n.get("role"), n.get("content", "")) for n in chain
                if n.get("role") in ("user", "assistant")]

    def _ask_llm(self, text):
        """调用主程序 LLM 生成压缩摘要"""
        client = getattr(self.core, "client", None)
        if not client:
            return None
        try:
            resp = client.chat.completions.create(
                model=getattr(self.core, "model", "deepseek-chat"),
                messages=[
                    {"role": "system",
                     "content": f"你是记忆压缩助手。把下面的对话历史压缩成 {self.SUMMARY_CHARS} 字以内的要点摘要，"
                                "保留：人物关系、剧情进展、重要设定、未完成事件。直接输出摘要正文，不要任何前缀。"},
                    {"role": "user", "content": text},
                ],
                stream=False,
                timeout=60,
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"[记忆链扩容] 摘要生成失败: {e}")
            return None

    def _fallback_summary(self, messages):
        """无 LLM 时的截取式摘要：开头几条 + 结尾几条"""
        if not messages:
            return ""
        head = messages[:6]
        tail = messages[-6:]
        lines = [f"{r}：{c[:80]}" for r, c in head]
        if len(messages) > 12:
            lines.append(f"……（中间省略 {len(messages) - 12} 条）……")
        lines += [f"{r}：{c[:80]}" for r, c in tail]
        return "\n".join(lines)

    def _build_summary(self, stem, safe, archive_path):
        try:
            messages = self._archive_chain_messages(archive_path)
            if not messages:
                return
            text = "\n".join(f"{r}: {c[:400]}" for r, c in messages)[:self.CONTEXT_CAP]
            summary = self._ask_llm(text) or self._fallback_summary(messages)
            if not summary:
                return
            summary_path = os.path.join(self.memory_dir, f"{safe}.summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump({
                    "stem": stem,
                    "summary": summary,
                    "generated_at": datetime.now().isoformat(),
                    "source": os.path.basename(archive_path),
                }, f, ensure_ascii=False, indent=2)
            print(f"[记忆链扩容] 🧠 压缩记忆已生成（{len(summary)} 字）")
        except Exception as e:
            print(f"[记忆链扩容] 摘要后台任务失败: {e}")

    def _latest_summary(self, safe):
        try:
            with open(os.path.join(self.memory_dir, f"{safe}.summary.json"),
                      "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # ============================================================
    # 消息注入：自动携带历史记忆
    # ============================================================
    def on_message_send(self, user_input):
        if not user_input:
            return user_input

        # 回溯请求优先（一次性）
        if self.pending_recall:
            recall_text = "\n".join(f"{r}：{c[:300]}" for r, c in self.pending_recall)
            self.pending_recall = []
            return f"[回溯记忆：更早的对话]\n{recall_text}\n---\n{user_input}"

        # 常规：注入压缩记忆
        if "[历史记忆]" in user_input:
            return user_input
        path = self._active_save()
        if not path:
            return user_input
        summary = self._latest_summary(self._safe_stem(self._stem(path)))
        if summary and summary.get("summary"):
            return f"[历史记忆]\n{summary['summary']}\n---\n{user_input}"
        return user_input

    # ============================================================
    # 命令
    # ============================================================
    def on_command(self, command, args):
        if command != "memory":
            return None

        parts = args.strip().split(maxsplit=1)
        action = parts[0].lower() if parts and parts[0] else "status"
        arg = parts[1] if len(parts) > 1 else ""

        if action == "status" or action == "":
            return self._cmd_status(), False

        if action == "recall":
            return self._cmd_recall(arg), False

        if action == "summary":
            return self._cmd_summary(), False

        if action == "clear":
            self.pending_recall = []
            return "✅ 已清除待回溯内容", False

        return ("用法：\n"
                "/memory              查看记忆链状态\n"
                "/memory recall [N]   回溯最近 N 条历史消息\n"
                "/memory summary      查看压缩记忆摘要\n"
                "/memory clear        清除待回溯内容"), False

    def _cmd_status(self):
        path = self._active_save()
        if not path:
            return "📭 尚未发现存档文件"
        stem = self._stem(path)
        safe = self._safe_stem(stem)
        size_kb = os.path.getsize(path) / 1024 if os.path.exists(path) else 0
        chain = self._load_chain().get(safe, [])
        total_nodes = sum(p.get("nodes", 0) for p in chain)
        lines = [
            f"📁 当前存档：{os.path.basename(path)}（{size_kb:.0f} KB）",
            f"🔗 记忆链：{len(chain)} 个归档，共 {total_nodes} 个历史节点",
        ]
        for p in chain[-5:]:
            lines.append(f"  · part{p['part']}: {p['nodes']} 节点, {p['size']/1024:.0f}KB, {p['time'][:16]}")
        summary = self._latest_summary(safe)
        if summary:
            lines.append(f"🧠 压缩记忆：{len(summary.get('summary', ''))} 字（{summary.get('generated_at', '')[:16]}）")
        else:
            lines.append("🧠 压缩记忆：尚未生成")
        lines.append(f"⚙️ 归档阈值：{self.MAX_BYTES/1000000:.2f}MB，保留 {self.KEEP_NODES} 个最近节点")
        return "\n".join(lines)

    def _cmd_recall(self, arg):
        path = self._active_save()
        if not path:
            return "📭 尚未发现存档文件"
        safe = self._safe_stem(self._stem(path))
        chain = self._load_chain().get(safe, [])
        if not chain:
            return "🔗 记忆链为空，还没有归档的历史"
        try:
            n = max(1, min(int(arg), 100)) if arg.strip() else self.RECALL_TAIL
        except ValueError:
            n = self.RECALL_TAIL

        messages = []
        # 从最新的归档往前找，直到凑够 n 条
        for part in reversed(chain):
            ap = os.path.join(self.memory_dir, part["path"])
            msgs = self._archive_chain_messages(ap)
            messages = msgs + messages
            if len(messages) >= n:
                break
        self.pending_recall = messages[-n:]
        return f"⏪ 已准备回溯最近 {len(self.pending_recall)} 条历史消息，下次发送消息时自动附带"

    def _cmd_summary(self):
        path = self._active_save()
        if not path:
            return "📭 尚未发现存档文件"
        summary = self._latest_summary(self._safe_stem(self._stem(path)))
        if not summary:
            return "🧠 尚未生成压缩记忆（对话量达到阈值后自动生成）"
        return f"🧠 压缩记忆（{summary.get('generated_at', '')[:16]} 生成）：\n{summary['summary']}"
