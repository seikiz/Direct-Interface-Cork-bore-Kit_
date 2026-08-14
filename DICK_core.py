# ============================================================
#   DICK_core.py - 核心引擎（树状分支版 + 动态注入）
#   独立模块，供 UI 导入使用
# ============================================================

import uuid
import re
import threading
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Callable, Any
from openai import OpenAI


class MessageNode:
    """对话节点，构成树状历史"""
    __slots__ = ('id', 'role', 'content', 'parent_id', 'children_ids', 'timestamp', 'metadata')
    def __init__(self, role: str, content: str, parent_id: Optional[str] = None, metadata: Optional[Dict] = None):
        self.id = str(uuid.uuid4())
        self.role = role
        self.content = content
        self.parent_id = parent_id
        self.children_ids = []
        self.timestamp = datetime.now().isoformat()
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "timestamp": self.timestamp,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data):
        node = cls(data['role'], data['content'], data.get('parent_id'), data.get('metadata', {}))
        node.id = data['id']
        node.children_ids = data.get('children_ids', [])
        node.timestamp = data.get('timestamp', datetime.now().isoformat())
        return node


# ============================================================
#   TreeManager - 纯树状历史管理（无 API 依赖）
# ============================================================
class TreeManager:
    """管理树状对话历史的所有操作（节点增删改查、链追踪、叶子修正）"""
    def __init__(self):
        self.nodes: Dict[str, MessageNode] = {}
        self.root_id: Optional[str] = None
        self.current_leaf_id: Optional[str] = None

    # ---------- 节点操作 ----------
    def add_node(self, role: str, content: str, parent_id: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
        node = MessageNode(role, content, parent_id, metadata)
        self.nodes[node.id] = node
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children_ids.append(node.id)
        if self.root_id is None:
            self.root_id = node.id
        self.current_leaf_id = node.id
        return node.id

    def delete_node(self, node_id: str):
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        for cid in node.children_ids[:]:
            self.delete_node(cid)
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node_id in parent.children_ids:
                parent.children_ids.remove(node_id)
        del self.nodes[node_id]
        if self.current_leaf_id == node_id:
            self.current_leaf_id = node.parent_id

    def delete_subtree(self, node_id: str):
        if node_id not in self.nodes:
            return
        node = self.nodes[node_id]
        for cid in node.children_ids[:]:
            self.delete_node(cid)
        node.children_ids = []

    def get_node(self, node_id: str) -> Optional[MessageNode]:
        return self.nodes.get(node_id)

    # ---------- 链追踪 ----------
    def get_current_chain(self) -> List[Dict]:
        if not self.current_leaf_id or self.current_leaf_id not in self.nodes:
            return []
        chain = []
        node = self.nodes.get(self.current_leaf_id)
        ancestors = []
        while node:
            ancestors.append(node)
            if node.parent_id and node.parent_id in self.nodes:
                node = self.nodes[node.parent_id]
            else:
                break
        ancestors.reverse()
        for n in ancestors:
            chain.append({"role": n.role, "content": n.content})
        return chain

    def get_all_nodes_data(self) -> Dict:
        return {
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "root_id": self.root_id,
            "current_leaf_id": self.current_leaf_id
        }

    def load_nodes_data(self, data: Dict):
        self.nodes = {}
        for nid, ndata in data.get('nodes', {}).items():
            self.nodes[nid] = MessageNode.from_dict(ndata)
        self.root_id = data.get('root_id')
        self.current_leaf_id = data.get('current_leaf_id')
        self.fix_leaf()
        chain_len = len(self.get_current_chain())
        print(f"[TreeManager] 加载后链长度: {chain_len}")

    # ---------- 叶子修正 ----------
    def fix_leaf(self):
        """确保 current_leaf_id 指向最深的叶子节点"""
        if not self.nodes or self.root_id is None:
            return
        node = self.nodes.get(self.root_id)
        if not node:
            return
        visited = set()
        while node.children_ids and node.id not in visited:
            visited.add(node.id)
            last_id = node.children_ids[-1]
            if last_id in self.nodes:
                node = self.nodes[last_id]
            else:
                break
        self.current_leaf_id = node.id
        print(f"[TreeManager] 叶子节点修正: {node.id} ({node.role})")

    def ensure_valid_leaf(self):
        if self.current_leaf_id is None or self.current_leaf_id not in self.nodes:
            self.fix_leaf()

    def count_nodes(self) -> int:
        return len(self.nodes)

    def clear(self):
        self.nodes = {}
        self.root_id = None
        self.current_leaf_id = None


# ============================================================
#   ContextInjector - 动态上下文注入器
#   根据用户输入检索索引文件，按需注入世界知识
# ============================================================

class ContextInjector:
    """动态上下文注入器 - 从索引文件中按关键词检索"""
    def __init__(self, index_dir: str):
        self.index_dir = index_dir
        self.indices = {}  # {index_filename: index_data}
        self._load_all_indices()

    def _load_all_indices(self):
        """加载所有 .index.json 文件"""
        if not os.path.exists(self.index_dir):
            return
        for fname in os.listdir(self.index_dir):
            if fname.endswith('.index.json'):
                try:
                    with open(os.path.join(self.index_dir, fname), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.indices[fname] = data
                except Exception as e:
                    print(f"[ContextInjector] 加载索引失败: {fname} - {e}")

    def get_context(self, user_input: str, max_entries: int = 3, priority_threshold: int = 200) -> str:
        """
        根据用户输入检索相关条目，返回拼接后的上下文
        :param user_input: 用户消息
        :param max_entries: 最多返回几条
        :param priority_threshold: 只返回 priority <= 此值的条目（越小越优先）
        """
        if not user_input or not self.indices:
            return ""

        # 提取关键词（简单分词）
        words = set()
        for w in re.split(r'[，,、。.！!？?；;：:\s\n]+', user_input):
            w = w.strip()
            if len(w) >= 2:
                words.add(w.lower())

        if not words:
            return ""

        # 匹配所有索引
        matched = []
        for idx_name, idx_data in self.indices.items():
            for entry in idx_data.get('entries', []):
                entry_priority = entry.get('priority', 100)
                if entry_priority > priority_threshold:
                    continue
                entry_keys = [k.lower() for k in entry.get('keywords', [])]
                # 检查是否有关键词匹配
                for word in words:
                    for key in entry_keys:
                        if word in key or key in word:
                            matched.append(entry)
                            break
                    else:
                        continue
                    break

        # 去重（按 content 去重）
        seen = set()
        unique = []
        for entry in matched:
            content = entry.get('content', '')
            if content not in seen:
                seen.add(content)
                unique.append(entry)

        # 按优先级排序
        unique.sort(key=lambda x: x.get('priority', 100))

        # 取前 max_entries 条
        selected = unique[:max_entries]
        if not selected:
            return ""

        # 拼接成上下文
        parts = []
        for entry in selected:
            comment = entry.get('comment', '')
            content = entry.get('content', '')
            if comment:
                parts.append(f"【{comment}】\n{content}")
            else:
                parts.append(content)

        return "\n\n".join(parts)


# ============================================================
#   ChatCore - 对话核心（整合 TreeManager + API + 动态注入）
# ============================================================
class ChatCore:
    def __init__(self):
        self.client = None
        self.model = "deepseek-v4-pro"
        self.base_url = "https://api.deepseek.com"
        self.api_key = None

        self.tree = TreeManager()

        self.active_roles: List[Dict] = []
        self.world_data: Optional[Dict] = None
        self.system_prompt_base = ""

        self.is_processing = False
        self.total_tokens = 0

        # ===== 新增：动态注入器 =====
        self.injector: Optional[ContextInjector] = None
        self.index_dir: Optional[str] = None

    # ---------- 基础设置 ----------
    def set_api_key(self, key: str):
        self.api_key = key
        self.client = OpenAI(api_key=key, base_url=self.base_url)

    def set_base_url(self, url: str):
        self.base_url = url
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def set_model(self, model: str):
        self.model = model

    def set_system_base(self, prompt: str):
        self.system_prompt_base = prompt

    # ---------- 新增：索引目录设置 ----------
    def set_index_dir(self, index_dir: str):
        """设置索引目录，初始化注入器"""
        self.index_dir = index_dir
        if os.path.exists(index_dir):
            self.injector = ContextInjector(index_dir)
        else:
            self.injector = None

    # ---------- 世界卡管理 ----------
    def set_world_data(self, world_dict: Dict):
        self.world_data = world_dict
        self._rebuild_system_node()

    def _inject_world_context(self, user_input: str) -> str:
        if not self.world_data:
            return ""
        entries = self.world_data.get('entries', [])
        if not entries:
            return ""
        matched = []
        for entry in entries:
            keywords = entry.get('keywords', [])
            content = entry.get('content', '')
            if not keywords or not content:
                continue
            for kw in keywords:
                if kw.lower() in user_input.lower():
                    matched.append(f"- {content}")
                    break
        if matched:
            return "【当前场景相关信息】\n" + "\n".join(matched) + "\n"
        return ""

    # ---------- 角色管理 ----------
    def set_active_roles(self, roles_data: List[Dict]):
        self.active_roles = roles_data
        if roles_data and 'history_tree' in roles_data[0]:
            # 直接加载已有的树（保留历史）
            self.load_nodes_data(roles_data[0]['history_tree'])
            print(f"[ChatCore] 加载历史树，节点数: {len(self.tree.nodes)}")
        else:
            # 回退到重建系统节点（兼容旧格式）
            self._rebuild_system_node()

    def _rebuild_system_node(self):
        old_system_ids = [nid for nid, node in self.tree.nodes.items() if node.role == 'system']
        first_children = []
        for sid in old_system_ids:
            node = self.tree.nodes.get(sid)
            if node:
                first_children.extend(node.children_ids)
                del self.tree.nodes[sid]
                if self.tree.root_id == sid:
                    self.tree.root_id = None

        combined = self.system_prompt_base + "\n"
        if len(self.active_roles) == 1:
            role = self.active_roles[0]
            combined += f"你现在的身份是：{role.get('name', '未知角色')}。\n"
            combined += role.get('system_prompt', '') + "\n"
        elif len(self.active_roles) > 1:
            combined += "你是一个多角色模拟器。\n"
            combined += "每条用户消息前会有 '@角色名' 标记，请根据该标记切换对应的角色语气和人格。\n"
            for idx, role in enumerate(self.active_roles):
                name = role.get('name', f'角色{idx+1}')
                full_prompt = role.get('system_prompt', '')
                combined += f"===== {name} 的角色设定 =====\n{full_prompt}\n"
            combined += "\n用户消息格式：@角色名 内容\n"

        if self.world_data:
            combined += f"\n当前世界观：{self.world_data.get('name', '未知世界')}\n"
            combined += f"背景：{self.world_data.get('description', '')}\n"
            rules = self.world_data.get('rules', [])
            if rules:
                combined += "基础规则：\n" + "\n".join([f"- {r}" for r in rules]) + "\n"

        sys_node = MessageNode('system', combined.strip(), parent_id=None)
        self.tree.nodes[sys_node.id] = sys_node
        self.tree.root_id = sys_node.id

        for cid in first_children:
            if cid in self.tree.nodes:
                self.tree.nodes[cid].parent_id = sys_node.id
                sys_node.children_ids.append(cid)

        self.tree.fix_leaf()

    # ---------- 对话操作 ----------
    def add_user_message(self, content: str) -> str:
        if self.tree.current_leaf_id is None:
            self._rebuild_system_node()
        return self.tree.add_node('user', content, parent_id=self.tree.current_leaf_id, metadata={"speaker": None})

    def add_assistant_message(self, content: str, parent_id: str, metadata: Optional[Dict] = None) -> str:
        return self.tree.add_node('assistant', content, parent_id=parent_id, metadata=metadata)

    def get_current_chain(self) -> List[Dict]:
        return self.tree.get_current_chain()

    def get_all_nodes_data(self) -> Dict:
        return self.tree.get_all_nodes_data()

    def load_nodes_data(self, data: Dict):
        self.tree.load_nodes_data(data)

    def clear_history(self):
        self.tree.clear()
        self.total_tokens = 0

    @property
    def nodes(self):
        return self.tree.nodes

    @property
    def current_leaf_id(self):
        return self.tree.current_leaf_id

    @current_leaf_id.setter
    def current_leaf_id(self, value):
        self.tree.current_leaf_id = value

    @property
    def root_id(self):
        return self.tree.root_id

    @root_id.setter
    def root_id(self, value):
        self.tree.root_id = value

    # ---------- 重试与编辑 ----------
    def regenerate_last(self, on_response=None, on_error=None):
        if not self.tree.current_leaf_id:
            return
        current = self.tree.nodes.get(self.tree.current_leaf_id)
        if not current:
            return
        if current.role == 'assistant':
            parent_id = current.parent_id
            if parent_id and parent_id in self.tree.nodes:
                parent = self.tree.nodes[parent_id]
                if self.tree.current_leaf_id in parent.children_ids:
                    parent.children_ids.remove(self.tree.current_leaf_id)
            del self.tree.nodes[self.tree.current_leaf_id]
            self.tree.current_leaf_id = parent_id
            if parent_id and self.tree.nodes[parent_id].role == 'user':
                user_msg = self.tree.nodes[parent_id].content
                speaker = None
                self._fetch_response(user_msg, speaker, on_response, on_error, parent_id)
                return
        elif current.role == 'user':
            self._fetch_response(current.content, current.metadata.get('speaker'), on_response, on_error, current.id)
            return
        if on_error:
            on_error("当前无法重试，请检查对话状态")

    def edit_and_branch(self, node_id: str, new_content: str, on_response=None, on_error=None):
        node = self.tree.nodes.get(node_id)
        if not node or node.role != 'user':
            if on_error:
                on_error("只能编辑用户消息")
            return
        node.content = new_content
        self.tree.delete_subtree(node_id)
        self.tree.current_leaf_id = node_id
        self._fetch_response(new_content, node.metadata.get('speaker'), on_response, on_error, node_id)

    # ---------- API 交互 ----------
    def send_message(self, user_input: str, on_response=None, on_error=None):
        if not self.client:
            if on_error: on_error("请先设置 API Key")
            return
        if not user_input.strip():
            return
        self.add_user_message(user_input)
        threading.Thread(
            target=self._fetch_response,
            args=(user_input, None, on_response, on_error, self.tree.current_leaf_id),
            daemon=True
        ).start()

    def _fetch_response(self, user_input: str, speaker: Optional[str], on_response, on_error, parent_node_id: str):
        if self.is_processing:
            if on_error: on_error("正在处理中，请稍候")
            return
        self.is_processing = True
        try:
            chain = self.tree.get_current_chain()
            system_msgs = [m for m in chain if m['role'] == 'system']
            last_user_msg = chain[-1] if chain and chain[-1]['role'] == 'user' else None

            messages = []
            if system_msgs:
                messages.append(system_msgs[0])

            # ===== 新增：动态注入 =====
            if self.injector:
                context = self.injector.get_context(user_input)
                if context:
                    messages.append({"role": "system", "content": f"【相关背景知识】\n{context}"})

            for msg in chain:
                if msg['role'] == 'system':
                    continue
                if msg['role'] == 'user' and msg == last_user_msg:
                    continue
                messages.append(msg)

            world_context = self._inject_world_context(user_input)
            if world_context:
                messages.append({"role": "system", "content": world_context})

            if last_user_msg:
                final_content = last_user_msg['content']
                if speaker:
                    final_content = f"[{speaker}]说：{final_content}"
                messages.append({"role": "user", "content": final_content})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                timeout=30
            )
            ai_reply = response.choices[0].message.content
            usage = response.usage

            # ====== 安全提取 usage ======
            usage_dict = {}
            if usage:
                usage_dict = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage, "completion_tokens", 0),
                    "total_tokens": getattr(usage, "total_tokens", 0),
                    "completion_tokens_details": {}
                }
                if hasattr(usage, "completion_tokens_details") and usage.completion_tokens_details:
                    details = usage.completion_tokens_details
                    if hasattr(details, "__dict__"):
                        usage_dict["completion_tokens_details"] = {k: v for k, v in details.__dict__.items() if not k.startswith("_")}
                    elif isinstance(details, dict):
                        usage_dict["completion_tokens_details"] = details

            node_id = self.tree.add_node(
                'assistant',
                ai_reply,
                parent_id=parent_node_id,
                metadata={"usage": usage_dict}
            )
            if usage:
                self.total_tokens += usage.total_tokens
            if on_response:
                on_response(ai_reply, usage)
        except Exception as e:
            if on_error:
                on_error(str(e))
        finally:
            self.is_processing = False

    def get_total_tokens(self) -> int:
        return self.total_tokens

    # ---------- 首次启动引导 ----------
    def check_first_launch(self, config_file: str):
        """
        检查是否为首次启动，返回 True 表示需要显示引导
        """
        if not os.path.exists(config_file):
            return True
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                if cfg.get("welcome_shown", False):
                    return False
        except:
            pass
        return True

    def mark_welcome_shown(self, config_file: str):
        """标记欢迎引导已显示"""
        try:
            cfg = {}
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            cfg["welcome_shown"] = True
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[引导] 写入标记失败: {e}")