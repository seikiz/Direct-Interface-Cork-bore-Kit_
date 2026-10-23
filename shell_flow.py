# -*- coding: utf-8 -*-
"""FlowMixin —— 从 Direct-Interface Cork-bore Kit.py 的 HtmlApp 拆出（ast 精确切分）。

方法：_on_busy、_regex_rules_all、_apply_regex_pipeline、_present_ending、_start_fetch、_split_hidden、_send_text、_on_response、_on_error
"""
from __future__ import annotations

import json
import notices
import os
import re
import text_shield

class FlowMixin:
    def _on_busy(self, msg=""):
        notices.busy_toast(self, msg)      # 忙=轻提示；去重与弹法都在 notices

    def _regex_rules_all(self, scope):
        """生效规则：全局 regex_rules.json + 当前角色卡 regex_rules（角色卡优先）"""
        rules = []
        try:
            with open(os.path.join(self.base_dir, "regex_rules.json"), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                rules.extend(data)
        except Exception:
            pass
        for name in self.selected_roles:
            for r in self.roles:
                if r["name"] == name:
                    adv = (r.get("data") or {}).get("advanced") or {}
                    rr = adv.get("regex_rules") or []
                    if isinstance(rr, list):
                        rules = list(rr) + rules
                    break
        # 玩家卡规则（同规格待遇）：<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌对玩家输入生效，优先于角色卡
        p = self.persona or {}
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = {}
        if isinstance(p, dict):
            prr = (p.get("advanced") or {}).get("regex_rules") or []
            if isinstance(prr, list):
                rules = list(prr) + rules
        out = []
        for x in rules:
            if not isinstance(x, dict) or not x.get("enabled", True):
                continue
            if not str(x.get("pattern") or "").strip():
                continue
            if (x.get("scope") or "both") not in (scope, "both"):
                continue
            out.append(x)
        return out

    def _apply_regex_pipeline(self, text, scope):
        """应用正则管道（存储前调用 → 树里存转换后文本，回溯/分支天然一致）"""
        if not text:
            return text
        for rule in self._regex_rules_all(scope):
            try:
                pattern = str(rule.get("pattern") or "")
                repl = str(rule.get("replace") or "")
                if scope == "user":
                    # 用户输入里的括号是动作描写，不是噪声：规则若会吃掉它，宁可跳过（见 text_shield.py）
                    text, _blocked = text_shield.keeps_user_text(
                        lambda t=text, p=pattern, r=repl: re.sub(p, r, t),
                        text, rule.get("id") or rule.get("name") or "")
                    continue
                text = re.sub(pattern, repl, text)
            except Exception:
                continue
        return text

    def _present_ending(self):
        """结局达成：读取 mechanics.endings，命中（达成事件链/状态）→ 弹结局横幅 + 注入收束到下一轮。"""
        try:
            ending = self.core.check_endings()
            if not ending:
                return
            nm = ending.get("name") or "结局"
            desc = ending.get("desc") or ""
            self._append_sys(f"🏁 结局达成：「{nm}」" + ((" · " + desc) if desc else "") + "（可回档到之前重走别的结局）")
            self.core.pending_event = {"id": "_ending", "name": "结局达成",
                "prompt": f"剧情已自然抵达结局「{nm}」。请以这一段收束剧情：{desc}。就写到这里，不要再展开新的支线。"}
        except Exception:
            pass

    def _start_fetch(self, user_node_id):
        """在指定用户节点下生成回复（候选/滑条/分支共用入口）"""
        self.busy = True
        self.streaming = ""
        self.core.generate_candidate(
            user_node_id,
            on_stream=lambda full: setattr(self, "streaming",
                                           self.core.strip_mechanism_tags(full, apply=False)),
            on_response=self._on_response,
            on_error=self._on_error, on_busy=self._on_busy)

    def _split_hidden(self, processed):
        """翻译隐藏标记解析 → (显示文本, 发送文本)。无标记则两者相同。
        约定：jp_patch 自动日译返回 "\u200b<原文>\u200b<译文>"。"""
        if not processed:
            return processed, processed
        mark = "\u200b"
        if isinstance(processed, str) and processed.startswith(mark):
            parts = processed.split(mark)
            if len(parts) >= 3:
                return parts[1], mark.join(parts[2:])
        return processed, processed

    def _send_text(self, display_text, hidden_send, image, is_choice=False):
        # 零宽字符防线：白烧 token / 卡界面 / 藏提示词注入 / 绕过关键词过滤。
        # 放在最前面 —— 后面入树、发 API、渲染用的都是清干净的文本。
        try:
            import text_guard
            display_text, _grep = text_guard.sanitize(display_text)
            if _grep.get("changed"):
                self._append_sys(text_guard.summary(_grep), kind="warn", speaker="安全")
            if hidden_send:
                hidden_send, _ = text_guard.sanitize(hidden_send)
        except Exception:
            pass
        # 括号诊断：玩家的「（动作）」是内容不是噪声。真被谁吃掉时，这里会留下原文与结果。
        try:
            _lost, _chars = text_shield.lost_brackets(hidden_send if hidden_send else display_text,
                                                     display_text)
            if _lost:
                print("[括号诊断] 显示文本丢了 %d 个括号（%s）：%r → %r"
                      % (_lost, "".join(_chars), hidden_send if hidden_send else display_text, display_text))
        except Exception:
            pass
        # 显示/存储用原文；若翻译隐藏（hidden_send 非空且不同），译文存 metadata["ja_input"]，
        # _fetch_response 发 AI 时优先用译文（聊天永远看不到日文）
        content = self._apply_regex_pipeline(display_text or "", "user")
        self._last_user = display_text or ""
        speaker = (self.persona or {}).get("name") or "你"
        node_id = self.core.add_user_message(content)
        try:
            self.core.tree.nodes[node_id].metadata["speaker"] = speaker
            if is_choice:
                # GAL 选项点：标记该用户节点为「选项」，供树视图选项骨架/收纳用
                self.core.tree.nodes[node_id].metadata["is_choice"] = True
            if hidden_send and hidden_send != display_text:
                self.core.tree.nodes[node_id].metadata["ja_input"] = hidden_send
            if self.core.mechanism_state is not None:
                self.core.tree.nodes[node_id].metadata["ms"] = self.core.mechanism_snapshot()
        except Exception:
            pass
        if image:
            self.node_images[node_id] = image
        self._start_fetch(node_id)
        self._rebuild_messages()

    def _on_response(self, ai_reply, usage):
        # 回复到了 → 开场加载态结束（无论这轮是不是开局，清掉都安全）
        self.opening_loading = False
        notices.set_status(self, "")      # 收起输入栏上方那行状态
        # 模型也可能吐零宽字符（尤其被用户诱导时）→ 同样清掉再入树，
        # 否则它会一直躺在聊天记录里，每次请求都白烧 token
        try:
            import text_guard
            ai_reply, _grep = text_guard.sanitize(ai_reply)
        except Exception:
            pass
        if usage:
            self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)
        # 中字日配：提取 [ja]...[/ja] 隐藏配音句（存节点 metadata，正文剥离）
        ja_text = ""
        try:
            m = re.search(r"\[ja\]([\s\S]*?)\[/ja\]", ai_reply or "")
            if m:
                ja_text = m.group(1).strip()
                ai_reply = re.sub(r"\[ja\][\s\S]*?\[/ja\]", "", ai_reply)
        except Exception:
            pass
        # 机制卡：解析 [aff:+N]/[键:值] 标签 → 应用状态 → 更新节点内容 → 检查事件
        try:
            clean = self.core.strip_mechanism_tags(ai_reply or "", apply=True)
            # 正则管道（ai 作用域）：标签剥离后、写入树前应用
            clean = self._apply_regex_pipeline(clean, "ai")
            if self.core.mechanism_state is not None:
                leaf = self.core.tree.current_leaf_id
                if leaf and leaf in self.core.tree.nodes:
                    node = self.core.tree.nodes[leaf]
                    if clean != (node.content or ""):
                        node.content = clean
                    ev = self.core.check_mech_events(self._last_user)
                    if ev:
                        self.core.pending_event = ev
                    node.metadata["ms"] = self.core.mechanism_snapshot()
                    if ja_text:
                        node.metadata["ja"] = ja_text
            ai_reply = clean
        except Exception:
            pass
        self._present_ending()
        # 世界线切换同步到 UI（GM 标记已由 core 解析并切换）——更新当前世界/配置/横幅
        try:
            sw = getattr(self.core, "last_world_switch", None)
            if sw:
                self.core.last_world_switch = None
                self.current_world = sw
                self.config["current_world"] = sw
                self._save_config()
                self._append_sys("🌐 已穿越到世界线「" + str(sw) + "」")
        except Exception:
            pass
        self._save_tree(wait=False)  # 自动落盘：走 io 线，别挡界面
        self._rebuild_messages()
        self.streaming = ""
        self.busy = False
        if self.auto_turn and len(self.selected_roles) > 1:
            self._maybe_auto_turn(2)
        for p in self.plugin_manager.get_all_plugins():
            if p.enabled:
                # 同上：钩子不挡回复（plugin 线 + 单任务 15 秒超时）
                try:
                    import jobs as _jobs
                    _jobs.submit("plugin", p.on_message_received,
                                 getattr(self, "_last_user", ""), ai_reply,
                                 name="插件钩子：" + str(getattr(p, "name", "?")),
                                 timeout=15)
                except Exception:
                    pass
        # 围棋：从模型回复里解析落子（引擎校验；非法/找不到就驳回重选或兜底）
        try:
            if getattr(self, "_go", None) is not None:
                self._go_after_reply(ai_reply if isinstance(ai_reply, str) else "")
        except Exception:
            pass

    def _on_error(self, err_msg):
        self.streaming = ""
        self.busy = False
        self.opening_loading = False     # 出错也要收掉开场加载态，否则会一直转圈
        self._save_tree(wait=False)  # 自动落盘：走 io 线，别挡界面
        # 商业化质量的错误提示：把裸异常转成"用户能行动"的指引
        msg = str(err_msg or "")
        low = msg.lower()
        hint = None
        if any(k in low for k in ("401", "invalid api key", "unauthorized", "authentication", "api key")):
            hint = "API Key 无效或未填。请到「设置 → 模型」里粘贴你的 Key（或检查是否过期）。"
        elif any(k in low for k in ("404", "not found", "model")):
            hint = "模型名或服务地址可能填错了。请到「设置 → 模型」核对 base_url 与模型名。"
        elif any(k in low for k in ("429", "rate limit", "too many", "超限", "insufficient")):
            hint = "请求过于频繁或余额不足。稍等再试，或检查账户额度。"
        elif any(k in low for k in ("timeout", "timed out", "connection", "network", "refused", "resolve")):
            hint = "网络连不上（可能被墙/代理没配）。可到「设置」开代理，或启用内置中转通道。"
        if hint:
            self._append_sys("❌ " + msg + "\n💡 " + hint)
        else:
            self._append_sys("❌ " + msg)
