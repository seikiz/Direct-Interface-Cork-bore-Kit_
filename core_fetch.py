# -*- coding: utf-8 -*-
"""FetchMixin —— 从 DICK_core.py 的 ChatCore 拆出（ast 精确切分）。

方法：_relay_target_url、_build_client、_maybe_switch_relay、_is_net_error、generate_candidate、send_message、_extract_usage、_mk_stream、_stream_create、_fetch_response、send_auto_turn、_fetch_auto_turn
"""
from __future__ import annotations

from core_llm import (_ensure_openai, APIConnectionError, APITimeoutError, httpx, _style_guard)
from typing import Dict, Optional
from notices import notify_busy
from core_context import time_context_for

import base64
import threading

class FetchMixin:
        # ---------- 基础<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌设置 ----------
        def _relay_target_url(self):
            """把直连 base_url 编码成内置中转的地址：<中转>/relay/<base64(base_url)>，
            客户端会把 /chat/completions 追加在后面，中转负责转发到真实厂商。"""
            if not self.relay_base or not self.base_url:
                return self.base_url
            enc = base64.urlsafe_b64encode(self.base_url.encode("utf-8")).decode("ascii").rstrip("=")
            return f"{self.relay_base}/relay/{enc}"

        def _build_client(self):
            """构造 OpenAI 客户端；配置了代理时走代理（保证被墙通道可用）；
            relay_on 后改走内置中转通道。"""
            kw = {"api_key": self.api_key or "free", "base_url": self.base_url}
            if self.relay_on and self.relay_base:
                kw["base_url"] = self._relay_target_url()
            if httpx is not None:
                try:
                    if self.proxy:
                        kw["http_client"] = httpx.Client(
                            proxy=self.proxy,
                            timeout=httpx.Timeout(600.0, connect=20.0),
                        )
                    else:
                        # 没配代理时【不要】继承 Windows 系统代理：
                        # 系统代理指向 127.0.0.1:7890 时，模型请求会被拖到超时。
                        kw["http_client"] = httpx.Client(
                            trust_env=False,
                            timeout=httpx.Timeout(600.0, connect=20.0),
                        )
                except Exception:
                    pass
            return _ensure_openai()(**kw)

        def _maybe_switch_relay(self):
            """直连网络失败 → 切内置中转通道并重建客户端。返回是否已切换。"""
            if self.relay_on or not self.relay_base:
                return False
            self.relay_on = True
            self.client = self._build_client()
            print("[代理通道] 直连失败，已自动切换内置中转通道（后续请求走中转）")
            return True

        @staticmethod
        def _is_net_error(e):
            return isinstance(e, (APIConnectionError, APITimeoutError))

        def generate_candidate(self, user_node_id: str, on_response=None, on_error=None, on_stream=None):
            """在指定用户节点下生成一条新的候选回复（树分支，不删除现有回复）"""
            node = self.tree.nodes.get(user_node_id)
            if not node or node.role != 'user':
                if on_error: on_error("候选生成失败：找不到用户节点")
                return
            self.tree.current_leaf_id = user_node_id
            # 翻译隐藏：聊天显示原文（content），发 AI 用译文（metadata.ja_input，中字日配不露痕迹）
            send_text = (node.metadata or {}).get('ja_input') or node.content
            threading.Thread(target=self._fetch_response,
                             args=(send_text, node.metadata.get('speaker'),
                                   on_response, on_error, user_node_id, on_stream),
                             daemon=True).start()

        def send_message(self, user_input: str, on_response=None, on_error=None, on_stream=None, on_busy=None):
            if not self.client:
                if on_error: on_error("请先设置 API Key")
                return
            if not user_input.strip():
                return
            with self._proc_lock:
                if self.is_processing:
                    notify_busy(on_busy, on_error)
                    return
                self.is_processing = True
            self.add_user_message(user_input)
            threading.Thread(
                target=self._fetch_response,
                args=(user_input, None, on_response, on_error, self.tree.current_leaf_id, on_stream, True),
                kwargs={"on_busy": on_busy},
                daemon=True
            ).start()

        def _extract_usage(self, usage) -> Dict:
            """安全提取 usage 为字典"""
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
            return usage_dict

        def _mk_stream(self, messages):
            """构造流式请求（兼容不支持 stream_options 的服务商）；停止序列/采样参数透传。

            出网前统一剥掉内部字段：裁剪用的 _node_id/_ts 带下划线前缀，
            绝不能发给 API（服务商会因为多余字段直接报错）。这里集中剥一次，
            好过在每条组装路径上各写一遍。
            """
            clean = [{k: v for k, v in m.items() if not str(k).startswith("_")}
                     if isinstance(m, dict) else m for m in messages]
            kw = {"model": self.model, "messages": clean, "stream": True, "timeout": 30}
            if self.stop_sequences:
                kw["stop"] = self.stop_sequences
            if self.temperature is not None:
                kw["temperature"] = self.temperature
            if self.top_p is not None:
                kw["top_p"] = self.top_p
            try:
                return self.client.chat.completions.create(**kw, stream_options={"include_usage": True})
            except TypeError:
                kw.pop("stream_options", None)
                return self.client.chat.completions.create(**kw)

        def _stream_create(self, messages, on_stream):
            """流式调用 API：逐块回调 on_stream(累计全文)，返回 (全文, usage)。
            - 直连网络失败时自动切内置中转通道重试一次；
            - 中途断流（长对话最常见）：若尚无可交付文本则重试，否则回传已收文本（不丢弃半截）。"""
            full = ""
            usage = None

            def _open_and_read(start_over):
                nonlocal full, usage
                stream = self._mk_stream(messages)
                if start_over:
                    full = ""
                for chunk in stream:
                    if getattr(chunk, "usage", None):
                        usage = chunk.usage
                    choices = getattr(chunk, "choices", None)
                    if choices:
                        delta = getattr(choices[0], "delta", None)
                        text = getattr(delta, "content", None) if delta else None
                        if text:
                            full += text
                            if on_stream:
                                try:
                                    on_stream(full)
                                except Exception:
                                    pass

            try:
                _open_and_read(False)
            except (APIConnectionError, APITimeoutError):
                # 打开即失败，尚未收到文本 → 切中转重试一次
                if self._maybe_switch_relay() and not full:
                    try:
                        _open_and_read(True)
                    except (APIConnectionError, APITimeoutError):
                        # 重试仍失败：保留已收文本（若有），交给上层处理
                        if not full:
                            raise
                elif not full:
                    # 无法切中转（无备用通道），且没收到任何文本 → 抛给上层
                    raise
            except Exception:
                # 非网络类异常（如序列化/参数）：不吞，原样抛
                raise
            return full, usage

        def _fetch_response(self, user_input: str, speaker: Optional[str], on_response, on_error, parent_node_id: str, on_stream=None, _locked=False, on_busy=None):
            if not self.client:
                if on_error: on_error("请先设置 API Key")
                return
            if not _locked:
                with self._proc_lock:
                    if self.is_processing:
                        notify_busy(on_busy, on_error)
                        return
                    self.is_processing = True
            try:
                chain = self.tree.get_current_chain()
                system_msgs = [m for m in chain if m['role'] == 'system']
                last_user_msg = chain[-1] if chain and chain[-1]['role'] == 'user' else None

                # ===== 真·多角色群聊：先确定本轮发言角色（物理隔离） =====
                # 1) 用户 @指定 → 用该角色；2) 未指定 → DICK 轮换（非最后发言者）。
                # 绝不把"选谁回应"交给模型（避免串戏/自问自答）；后续 system 注入与
                # 历史归属全部以这个角色为准。
                if len(self.active_roles) > 1:
                    _roster = self._roster_names()
                    _addressed = self._resolve_addressed(user_input)
                    if _addressed in _roster:
                        speaker = _addressed
                    else:
                        speaker = self._pick_group_speaker(user_input, _roster)
                    _group_speaker = speaker
                else:
                    _group_speaker = None

                messages = []

                # 创作前提不再放在最前面 —— 那里离当前轮最远，最没分量。
                # 改为在本轮即将发出前追加（见下面「近期指令」处），
                # 让它成为模型读到的最后一条 system。
                _premise_on = any(r.get('unlocked', False) for r in self.active_roles)

                # 原有系统消息
                if system_msgs:
                    if _group_speaker is not None:
                        # 真·多角色群聊：system = 公共框架 + 目标角色专属提示词（物理隔离）
                        target_role = self._role_by_name(_group_speaker)
                        base = system_msgs[0]['content']
                        if target_role:
                            base = base + "\n\n" + self._build_role_prompt(target_role)
                        messages.append({"role": "system", "content": base})
                    else:
                        messages.append({"role": "system", "content": system_msgs[0]['content']})

                # ===== 动态注入（世界书/知识库） =====
                if self.injector:
                    context = self.injector.get_context(user_input)
                    if context:
                        messages.append({"role": "system", "content": f"【相关背景知识】\n{context}"})

                # ===== 文档上下文（读入的 Word/Excel） =====
                if self.document_context:
                    messages.append({"role": "system", "content":
                                     f"【当前文档内容（供总结/改写/翻译/问答参考）】\n{self.document_context}"})

                # 历史消息：assistant 带 [发言者]: 前缀（群聊格式学习）
                # 时间粘在历史【之前】：让模型带着时间感去读下面这些对话。
                # 这就是"两条纸带粘一起"——一条记内容，一条记间隔。
                _tc = time_context_for(chain, self._time_scale())
                if _tc:
                    messages.append({"role": "system", "content": _tc})

                # 生活层：那边现在几点、今天吃了什么、手边有什么家伙（见 life_core.py）。
                # 紧挨着时间纸带放 —— 一个说"隔了多久"，一个说"那边此刻是什么日子"。
                _life_txt = self._life_injection(chain, speaker)
                if _life_txt:
                    messages.append({"role": "system", "content": _life_txt})

                # 空间层：她在哪、这段时间够去哪、上一跳有没有穿帮（见 space_core.py）。
                # 与时间纸带同源：世界过了多久 → 决定"移动合不合理"。
                _space_txt = self._space_injection(chain, speaker)
                if _space_txt:
                    messages.append({"role": "system", "content": _space_txt})

                # 世界记忆（演化）：这个世界已经发生过的事（见 world_memory.py）。
                # 放在空间层之后 —— 先"她在哪"，再"这个世界现在是什么样"。
                _wm_txt = self._world_memory_injection(chain, speaker, user_input)
                if _wm_txt:
                    messages.append({"role": "system", "content": _wm_txt})
                for msg in chain:
                    if msg['role'] == 'system':
                        continue
                    if msg['role'] == 'user' and msg == last_user_msg:
                        continue
                    if msg['role'] == 'assistant':
                        messages.append({"role": "assistant",
                                         "content": self._format_assistant_content(msg)})
                    else:
                        messages.append({"role": "user", "content": msg['content']})

                world_context = self._inject_world_context(user_input)
                if world_context:
                    messages.append({"role": "system", "content": world_context})

                # ===== 机制卡：事件注入（只进 API 载荷，不入历史树） =====
                if self.pending_event:
                    ev = self.pending_event
                    self.pending_event = None
                    self.last_event = ev  # 保留最近事件，供本轮后的选项生成结合剧情
                    messages.append({"role": "system", "content":
                        f"【事件触发：{ev.get('name') or ev.get('id')}】\n{ev.get('prompt', '')}"})

                # ===== 机制卡：动态注入最新状态（每轮刷新，AI 感知并自然演出） =====
                if self.mechanism_state and (self._mech_config or self._battle_config()):
                    st = self.mechanism_state
                    parts = []
                    aff = st.get("affection")
                    if aff is not None:
                        parts.append(f"好感度={aff}")
                    status = st.get("status") or {}
                    for k, v in status.items():
                        if k == "buffs":
                            continue
                        parts.append(f"{k}={v}")
                    if parts:
                        messages.append({"role": "system", "content":
                            "【当前状态】" + "，".join(str(x) for x in parts) +
                            "。状态异常时（体力低/心情差/好感度骤降等）在回复中自然体现（如'我有点不舒服'、"
                            "'今天没什么精神'），不要机械播报数值，不要解释你在引用状态。"})

                addressed = _group_speaker

                # ===== 近期指令：放在本轮用户消息之前，作为模型读到的最后一条 system =====
                # 模型对靠近当前轮的指令权重更高。放最前面时，它被后面几千字的设定稀释，
                # 这正是「热注入明明开了却没效果」的原因。
                if _premise_on:
                    messages.append({"role": "system", "content": self.CREATION_PREMISE})

                # ===== 输出多样性：这个位置已经有候选了，就要求换一条路 =====
                # 只在「重新生成」时触发（父节点下已经有 assistant 兄弟）。
                # 不加这条的话，重 roll 出来的几条往往只换几个词 —— 用户滑来滑去
                # 等于没得选，"树"就退化回一条单线。
                if parent_node_id and parent_node_id in self.tree.nodes:
                    try:
                        import tree_weight as _tw
                        _p = self.tree.nodes[parent_node_id]
                        _sibs = [self.tree.nodes[c].content
                                 for c in _p.children_ids
                                 if c in self.tree.nodes
                                 and self.tree.nodes[c].role == "assistant"]
                        if _sibs:
                            _hint = _tw.diversity_hint(_sibs)
                            if _hint:
                                messages.append({"role": "system", "content": _hint})
                    except Exception:
                        pass

                # ===== 开局：把角色卡的开场白当「场景」交给模型，由它现场演出第一幕 =====
                # 一次性：注入完就清掉，否则每轮都会重新演一遍开场。
                # 放在创作前提之后 —— 越靠近这次要生成的内容，权重越高。
                if self.opening_cue:
                    cue = self.opening_cue
                    self.opening_cue = None
                    messages.append({"role": "system",
                                     "content": self._opening_prompt(cue)})

                if last_user_msg:
                    final_content = last_user_msg['content']
                    if _group_speaker:
                        final_content = f"[{_group_speaker}]说：{final_content}"
                    # 玩家角色卡：用户消息以玩家角色名义发出（AI 知道是谁在说话）
                    if self.player_persona and not final_content.lstrip().startswith('['):
                        final_content = f"[{self.player_persona.get('name', '玩家')}]: {final_content}"
                    messages.append({"role": "user", "content": final_content})

                # ===== 上下文预算裁剪 =====
                messages = self._fit_budget(messages)

                # ===== 前瞻展开（可选）=====
                # 到这一步载荷已经组装完毕（system / 历史 / 本轮用户消息都在），
                # 但用户还没看到任何东西 —— 这是全流程里唯一"先生成再看"的时机。
                # 树壳之所以阻止不了漂移，就是因为它在生成【之后】；这一钩子把它挪到生成【之中】。
                # 投机器返回 None 就按老路走（不干预），所以关掉这个功能等于零影响。
                _picked = None
                if self.speculator is not None:
                    try:
                        _picked = self.speculator(messages)
                    except Exception as _e:
                        _picked = None
                        try:
                            if on_error:
                                on_error("前瞻展开失败，已按原路继续：" + str(_e)[:120])
                        except Exception:
                            pass
                if _picked:
                    ai_reply, usage = _picked, None
                    if on_stream:
                        try:
                            on_stream(_picked)
                        except Exception:
                            pass
                else:
                    # ===== 流式调用：逐块回调 on_stream(累计全文) =====
                    ai_reply, usage = self._stream_create(messages, on_stream)
                ai_reply = (ai_reply or "").strip()
                usage_dict = self._extract_usage(usage)

                # ===== 群聊：解析说话者并归属回复 =====
                speaker_name, clean_reply = (self._parse_speaker(ai_reply)
                                             if len(self.active_roles) > 1 else (None, ai_reply))
                if speaker_name is None:
                    speaker_name = addressed if len(self.active_roles) > 1 else None
                    if speaker_name is None and len(self.active_roles) > 1:
                        speaker_name = self._roster_names()[0] if self._roster_names() else None
                    clean_reply = ai_reply
                self.last_speaker = speaker_name
                self._bump_speaker(speaker_name)

                # 世界线切换：GM 回复带【世界线：xxx】标记 → 自动穿越 + 剔除标记
                clean_reply, switched_world = self.apply_world_marker(clean_reply)
                self.last_world_switch = switched_world

                # 确定性风格闸：写入上下文前洗掉文学腔表达（不删内容，断自增强）
                if self.style_guard and _style_guard is not None:
                    clean_reply = _style_guard(clean_reply, long_sentence=self.style_guard_long)

                node_id = self.tree.add_node(
                    'assistant',
                    clean_reply,
                    parent_id=parent_node_id,
                    metadata={"speaker": speaker_name, "usage": usage_dict}
                )
                if usage:
                    self.total_tokens += usage.total_tokens
                if on_response:
                    on_response(clean_reply, usage)
            except Exception as e:
                if on_error:
                    on_error(str(e))
            finally:
                self.is_processing = False

        # ---------- 群聊自动接话 ----------
        def send_auto_turn(self, speaker_name: str, on_response=None, on_error=None, on_stream=None, on_busy=None):
            """群聊自动接话：让指定角色基于当前上下文继续发言。
            合成指令不写入历史树，只有该角色的发言会作为 assistant 节点保存。
            """
            if not self.client or not speaker_name:
                if on_error: on_error("自动接话不可用")
                return
            with self._proc_lock:
                if self.is_processing:
                    notify_busy(on_busy, on_error)
                    return
                self.is_processing = True
            threading.Thread(target=self._fetch_auto_turn,
                             args=(speaker_name, on_response, on_error, on_stream, True),
                             daemon=True).start()

        def _fetch_auto_turn(self, speaker_name: str, on_response, on_error, on_stream=None, _locked=False):
            if not _locked:
                with self._proc_lock:
                    if self.is_processing:
                        notify_busy(on_busy, on_error)
                        return
                    self.is_processing = True
            try:
                chain = self.tree.get_current_chain()
                messages = []
                system_msgs = [m for m in chain if m['role'] == 'system']
                if system_msgs:
                    base = system_msgs[0]['content']
                    if len(self.active_roles) > 1:
                        # 真·多角色群聊：只给目标角色的专属 prompt（物理隔离）
                        target = self._role_by_name(speaker_name)
                        if target:
                            base = base + "\n\n" + self._build_role_prompt(target)
                    messages.append({"role": "system", "content": base})
                if self.document_context:
                    messages.append({"role": "system", "content":
                                     f"【当前文档内容（供总结/改写/翻译/问答参考）】\n{self.document_context}"})
                _tc2 = time_context_for(chain, self._time_scale())
                if _tc2:
                    messages.append({"role": "system", "content": _tc2})
                for msg in chain:
                    if msg['role'] == 'system':
                        continue
                    if msg['role'] == 'assistant':
                        messages.append({"role": "assistant",
                                         "content": self._format_assistant_content(msg)})
                    else:
                        messages.append({"role": "user", "content": msg['content']})
                messages.append({"role": "user", "content":
                    f"（现在轮到群成员「{speaker_name}」发言。请以 {speaker_name} 的口吻简短自然地接话，"
                    f"回复格式：[{speaker_name}]: 内容。如果 {speaker_name} 此刻没有想说的，只回复：[{speaker_name}]: 沉默）"})

                messages = self._fit_budget(messages)
                ai_reply, usage = self._stream_create(messages, on_stream)
                ai_reply = (ai_reply or "").strip()
                usage_dict = self._extract_usage(usage)

                parsed_speaker, clean_reply = self._parse_speaker(ai_reply)
                final_speaker = parsed_speaker or speaker_name
                final_reply = clean_reply if parsed_speaker else ai_reply
                if final_reply.strip() in ("沉默", "（沉默）", "(沉默)"):
                    final_reply = "（沉默）"
                self.last_speaker = final_speaker
                self._bump_speaker(final_speaker)

                if usage:
                    self.total_tokens += usage.total_tokens
                parent_id = self.tree.current_leaf_id
                self.tree.add_node(
                    'assistant',
                    final_reply,
                    parent_id=parent_id,
                    metadata={"speaker": final_speaker, "usage": usage_dict}
                )
                if on_response:
                    on_response(final_reply, usage)
            except Exception as e:
                if on_error:
                    on_error(str(e))
            finally:
                self.is_processing = False
