# ============================================================
#   galgame_choices_plugin.py - Galgame 选项（选择肢）插件 v1.0
#
#   视觉小说式选择肢：AI 回复后自动生成 N 个剧情选项按钮，
#   点一下即以该行动发言（也可以照常自由输入）。
#
#   命令：
#     /cyoa           手动生成一组选项（自动模式关闭时也可用）
#     /cyoa show      查看当前已生成的选项
#
#   设置（⚙️ 设置 → 插件 → Galgame 选项）：
#     count  每轮选项数量（2-4，默认 3）
#     auto   每轮 AI 回复后自动生成（默认开）
#
#   联动：html_app 把选项状态透传给前端（api_state/api_poll 的
#   "choices" 字段），前端渲染按钮；api_pick_choice 以选项内容
#   作为玩家输入发送；api_cyoa 手动触发。
# ============================================================

import json
import re
import threading
import time

from plugin_base import PluginBase


class GalgameChoicesPlugin(PluginBase):
    name = "Galgame 选项"
    version = "1.1"
    description = "视觉小说式选择肢：AI 回复后自动生成剧情选项（支持机制卡好感/状态效果），点击即以该行动发言（/cyoa 手动）"
    author = "seiki"
    enabled = False

    ui_buttons = [
        {"type": "insert", "label": "🎮 选项", "text": "/cyoa"},
    ]

    settings_schema = [
        {"key": "count", "label": "每轮选项数量", "type": "int",
         "default": 3, "min": 2, "max": 4},
        {"key": "auto", "label": "AI 回复后自动生成选项", "type": "bool",
         "default": True},
    ]

    def __init__(self, core):
        super().__init__(core)
        self.choices = []            # 当前可点的选项列表
        self.choices_loading = False # 是否正在生成
        self.choices_error = ""      # 最近一次生成失败的原因
        self._gen_user_node = None   # 已为哪个用户节点生成过选项（避免滑条/群聊重复生成）
        self._lock = threading.Lock()

    def on_load(self):
        print("[Galgame 选项] 已加载：AI 回复后自动生成剧情选项，/cyoa 手动触发（默认关闭）")

    # ---------- 状态 ----------
    def clear_choices(self):
        with self._lock:
            self.choices = []
            self.choices_loading = False
            self.choices_error = ""
            self._gen_user_node = None

    def on_message_send(self, user_input):
        # 玩家输入新内容（打字或点选项）后，旧选项作废
        self.clear_choices()
        return user_input

    # ---------- 触发 ----------
    def on_message_received(self, user_input, ai_reply):
        if not self.get_setting("auto", True):
            return
        self.maybe_generate()

    def on_command(self, command, args):
        if command not in ("cyoa", "choices", "选择"):
            return None
        arg = (args or "").strip().lower()
        if arg in ("show", "查看", "list"):
            with self._lock:
                items = list(self.choices)
            if not items:
                return "🎮 还没有选项，先输入 /cyoa 生成", False
            lines = "\n".join(f"{i}. " + (t.get("text") if isinstance(t, dict) else str(t))
                              for i, t in enumerate(items, 1))
            return f"🎮 当前选项：\n{lines}", False
        ok, msg = self.manual_generate()
        return msg, False

    # ---------- 生成 ----------
    def maybe_generate(self):
        """自动模式：若本回合还没生成过选项（且当前不在生成中），则生成"""
        if self.choices_loading:
            return
        uid = self._last_user_node_id()
        with self._lock:
            if self._gen_user_node == uid and self.choices:
                return  # 同一用户消息已生成过（滑条切候选时不重复生成）
        self._start_generate()

    def manual_generate(self):
        """手动触发（/cyoa 或前端 api_cyoa）。返回 (ok, 消息)"""
        if self.choices_loading:
            return False, "⏳ 正在生成选项，请稍候…"
        if not self.core.client:
            return False, "⚠️ 请先启动聊天（配置 API Key）"
        self._start_generate()
        return True, f"⏳ 正在生成 {int(self.get_setting('count', 3))} 个剧情选项…"

    def _start_generate(self):
        with self._lock:
            self.choices_loading = True
            self.choices_error = ""
        threading.Thread(target=self._generate, daemon=True).start()

    def _last_user_node_id(self):
        core = self.core
        nid = core.tree.current_leaf_id
        try:
            while nid and nid in core.tree.nodes:
                node = core.tree.nodes[nid]
                if node.role == "user":
                    return nid
                nid = node.parent_id
        except Exception:
            pass
        return None

    def _generate(self):
        # 等待主对话空闲（滑条候选可能还在收尾），最多等 60 秒
        deadline = time.time() + 60
        try:
            while self.core.is_processing and time.time() < deadline:
                time.sleep(0.02)
        except Exception:
            pass
        count = int(self.get_setting("count", 3) or 3)
        count = max(2, min(4, count))
        try:
            transcript = self._build_transcript()
            # 机制卡：若启用好感/状态，选项需附带机制效果（前端小字展示）
            mech = getattr(self.core, "_mech_config", None) or {}
            has_aff = isinstance(mech.get("affection"), dict) and bool(mech["affection"].get("enabled"))
            st_cfg = mech.get("status")
            has_st = isinstance(st_cfg, dict) and bool(st_cfg.get("enabled")) and bool(st_cfg.get("fields"))
            effect_fmt = []
            if has_aff:
                effect_fmt.append('"aff": 好感度变化整数（如 +2 / -1；无影响则省略）')
            if has_st:
                keys = [str(f.get("key")) for f in st_cfg.get("fields") or []
                        if isinstance(f, dict) and f.get("key")]
                effect_fmt.append('"st": 状态变化对象，键为 ' + "、".join(keys)
                                  + "，值为目标值或 ±N（无变化则省略）")
            system = (
                "你是视觉小说（Galgame）的选项生成器。根据最近剧情，"
                f"为玩家（用户）生成 {count} 个简短、可行、有区分度的下一步行动选项。"
                "要求：每个选项不超过 18 个字，口语化，贴合当前角色性格与剧情走向；"
                "不要剧透后续剧情，不要输出编号或'选项一'这类前缀。"
                '每个选项必须带 "result"：一句事件结果提示（≤12 字，模糊、不剧透具体数值，'
                '如 "她可能会心头一暖" / "气氛可能会尴尬"）。'
            )
            if effect_fmt:
                system += (
                    "当前角色卡启用了机制（好感度/状态），每个选项还必须附带机制效果标签："
                    '只输出 JSON 数组，每项为 {"text": "选项文本", "result": "结果提示", '
                    + ", ".join(effect_fmt) + '}。'
                    'text 不超过 18 字；效果要贴合该选项的后果（可能为正、负或无），'
                    '例如：[{"text":"温柔关心她","result":"她可能会心头一暖","aff":+3},'
                    '{"text":"冷嘲热讽","result":"可能会惹她生气","aff":-5,"st":{"心情":"生气"}}]'
                )
            else:
                system += (
                    '只输出 JSON 数组，每项为 {"text": "选项文本", "result": "结果提示"}，'
                    '例如：[{"text":"轻轻敲门","result":"屋里人可能会回应"},'
                    '{"text":"转身离开","result":"可能会就此错过"}]'
                )
            resp = self.core.client.chat.completions.create(
                model=self.core.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": transcript},
                ],
                stream=False,
                timeout=60,
            )
            raw = (resp.choices[0].message.content or "").strip()
            items = self._parse_options(raw, count)
            with self._lock:
                if items:
                    self.choices = items
                    self.choices_error = ""
                    self._gen_user_node = self._last_user_node_id()
                else:
                    self.choices = []
                    self.choices_error = "未能解析出选项（模型输出格式异常）"
        except Exception as e:
            with self._lock:
                self.choices = []
                self.choices_error = str(e)[:120]
            print(f"[Galgame 选项] 生成失败: {e}")
        finally:
            with self._lock:
                self.choices_loading = False
            print(f"[Galgame 选项] 完成，{len(self.choices)} 个选项")

    # ---------- 上下文 ----------
    def _build_transcript(self, max_msgs=8):
        core = self.core
        try:
            chain = [m for m in core.get_current_chain() if m.get("role") != "system"]
        except Exception:
            chain = []
        lines = []
        for m in chain[-max_msgs:]:
            role = m.get("role")
            content = str(m.get("content", ""))[:300]
            if not content.strip():
                continue
            if role == "user":
                lines.append("你：" + content)
            else:
                speaker = (m.get("metadata") or {}).get("speaker") or "AI"
                lines.append(f"{speaker}：" + content)
        return "\n".join(lines) if lines else "（尚无对话）"

    # ---------- 解析 ----------
    @staticmethod
    def _try_json(s):
        """宽容解析 JSON 数组：原文 / 提取 [..] 子串 / 容忍尾随逗号。失败返回 None"""
        s = (s or "").strip()
        candidates = [s]
        i = s.find("[")
        j = s.rfind("]")
        if i >= 0 and j > i:
            candidates.append(s[i:j + 1])
        cleaned = re.sub(r",\s*([}\]])", r"\1", s)   # 容忍尾随逗号（,} / ,]）
        if cleaned != s:
            candidates.append(cleaned)
            i2 = cleaned.find("[")
            j2 = cleaned.rfind("]")
            if i2 >= 0 and j2 > i2:
                candidates.append(cleaned[i2:j2 + 1])
        for c in candidates:
            try:
                arr = json.loads(c)
                if isinstance(arr, list):
                    return arr
            except Exception:
                continue
        return None

    def _parse_options(self, text, count):
        text = (text or "").strip()
        # 模型常输出 +N（JSON 数字不允许 + 前缀），先宽容化（不影响字符串内内容）
        text = re.sub(r'(?<=[:：])\s*\+', ' ', text)
        # 1) JSON 数组（字符串或 {text, aff, st} 对象，宽容解析）
        arr = self._try_json(text)
        if arr is not None:
            return self._clean(arr, count)
        # 2) 去掉 ```json ``` 代码块后再试
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            arr = self._try_json(m.group(1).strip())
            if arr is not None:
                return self._clean(arr, count)
        # 3) 编号/项目符号逐行；跳过 JSON 残留行（{/[ 开头，避免把 JSON 原文当选项文本显示）；
        #    单行且无列表标记 → 格式失败（避免把散文当选项）
        lines = []
        for l in re.split(r"[\n\r]+", text):
            s = l.strip()
            if not s or s.startswith(("{", "[")):
                continue
            lines.append(s)
        if len(lines) == 1 and not re.match(
                r"^\s*(?:[\[\(]?\d+[\]\)\.、:：)\s]+|[-*•·]\s+)", lines[0]):
            return []
        return self._clean(lines, count)

    @staticmethod
    def _clean(raw_items, count):
        out = []
        seen = set()
        for x in raw_items:
            if isinstance(x, dict):
                s = str(x.get("text") or "").strip()
                aff = x.get("aff")
                st = x.get("st")
                result = x.get("result")
                try:
                    aff = int(aff) if aff is not None else None
                except (TypeError, ValueError):
                    aff = None
                if not isinstance(st, dict):
                    st = None
                if not isinstance(result, str):
                    result = None
            else:
                s = str(x).strip()
                aff = None
                st = None
                result = None
            s = re.sub(r"^[\[\(]?\d+[\]\)\.、:：)\s]+", "", s)   # 1. 1、1: 等编号
            s = re.sub(r"^[-*•·]\s*", "", s)                      # 项目符号
            s = re.sub(r"[（(][^（）()]*[）)]\s*$", "", s)          # 末尾括号说明（模型常附加）
            s = s.strip().strip('"').strip("'").strip()
            if not s or len(s) > 50:                              # 空串/过长（散文）丢弃
                continue
            if s in seen:
                continue
            seen.add(s)
            item = {"text": s}
            if result:
                item["result"] = str(result).strip()[:20]
            if aff is not None:
                item["aff"] = aff
            if st:
                item["st"] = {str(k).strip()[:20]: v for k, v in st.items() if str(k).strip()}
            out.append(item)
            if len(out) >= count:
                break
        return out
