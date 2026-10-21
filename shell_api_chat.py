# -*- coding: utf-8 -*-
"""shell_api_chat —— 从 Kit.py 拆出的 mixin（^api_poll|^api_state|^api_send|^api_pick_choice|^api_cyoa|^api_battle|^api_quick|^api_dismiss|^api_travel|^api_regenerate|^api_edit|^api_branch）。

包含方法：api_poll、api_pick_choice、api_cyoa、api_battle_move、api_quick_replies、api_dismiss_welcome、api_send、api_travel、api_regenerate、api_edit_message、api_branches

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。
"""
from __future__ import annotations

import app_version
import i18n
import json
import os
import threading
from shell_util import BUILTIN_RELAY, PROVIDERS

class ApiChatMixin:
    """shell_api_chat"""

    # ---------- js_<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌api ----------
    def api_state(self):
        with self._lock:
            return {
                "lang": self.language,
                # 版号：唯一真相是根目录 version.json（见 app_version.py）。
                # 前端拿它打控制台横幅 / 关于区，不再自己写死一个号。
                "version": app_version.display(),
                "version_full": app_version.full(),
                "roles": [r["name"] for r in self.roles],
                "role_unlocked": {r["name"]: bool(r.get("unlocked", False)) for r in self.roles},
                "worlds": [w.get("name", "") for w in self.worlds],
                "presets": [p.get("name", "默认") for p in self.presets],
                "selected_roles": list(self.selected_roles),
                "selected_worlds": list(self.selected_worlds),
                "current_world": self.current_world,
                "preset": self.preset_name,
                "persona": self.persona,
                "has_key": bool(self.api_keys.get(self.provider_id) or self.config.get("api_key")),
                "model": self.config.get("model", "deepseek-flash"),
                "base_url": self.config.get("base_url", "https://api.deepseek.com"),
                "providers": PROVIDERS,
                "provider": self.provider_id,
                "proxy": self.config.get("proxy", ""),
                "relay_url": self.config.get("relay_url") or BUILTIN_RELAY,
                "relay_on": bool(getattr(self.core, "relay_on", False)),
                "stop_input": list(self.config.get("stop_sequences") or []),
                "stop_sequences": list(getattr(self.core, "stop_sequences", None) or []),
                "temperature": self.config.get("temperature"),
                "top_p": self.config.get("top_p"),
                "dev_mode": bool(self.config.get("dev_mode", False)),
                "humanize": bool(getattr(self.core, "humanize", True)),
                "style_guard": bool(getattr(self.core, "style_guard", True)),
                "style_guard_long": bool(getattr(self.core, "style_guard_long", False)),
                "welcome_shown": bool(self.config.get("welcome_shown", False)),
                "ollama_online": bool(getattr(self, "ollama_online", False)),
                "api_keys": self.api_keys,
                "image_gen_key": self.config.get("image_gen_key", ""),
                "image_gen_base_url": self.config.get("image_gen_base_url", "https://api.siliconflow.cn/v1"),
                "image_gen_model": self.config.get("image_gen_model", "black-forest-labs/FLUX.1-schnell"),
                "image_gen_backend": self.config.get("image_gen_backend", "auto"),
                # 上次生图的输入（面板打开时自动回填，省得反复重敲提示词）
                "image_gen_last": dict(self.config.get("image_gen_last") or {}),
                "auto_turn": self.auto_turn,
                "font": self.font_size,
                "budget": int(self.config.get("context_budget", 0) or 0),
                "document": self.loaded_document,
                "plugins": [{"name": p.name, "version": p.version, "description": p.description,
                             "enabled": bool(p.enabled),
                             "schema": getattr(p, "settings_schema", None) or [],
                             "settings": dict(getattr(p, "settings", {}) or {})}
                            for p in self.plugin_manager.get_all_plugins()
                            if p.name not in self.CORE_UI_PLUGINS],
                "l2d": self._l2d_state(),
                "chat_wallpaper": os.path.isfile(self._wallpaper_path()),
                "trpg": self._trpg_state(),
                "theme": self.config.get("ui_theme", 0),
                "accent": self.config.get("ui_accent", 0),
                "messages": self.messages,
                "streaming": self.streaming,
                "busy": self.busy,
                "opening_loading": self.opening_loading,
                "tokens": self.total_tokens,
                "epoch": self.render_epoch,
                "choices": self._choices_state(),
                "mechanism": {"config": getattr(self.core, "_mech_config", None),
                              "state": self.core.mechanism_snapshot()},
                "battle": self.core.battle_ui_state(),
                "codex_auto_open": self.codex_auto_open,
            }

    # ---------- 分道执行：通用异步通道 ----------
    # 前端调 api_job_submit(kind, args) → 立刻拿到 job id；干完的结果从 poll 的 jobs 流回去。
    # 这样慢活儿（工坊网络/看图/插件钩子）不再占着一次 js_api 调用等在那儿。
    #
    # 任务体直接复用现成的 api_* 实现（不另写一份）—— 名字映射，避免出现第二套逻辑。
    JOB_KINDS = {
        # kind                           线         现成的实现
        "workshop.test": ("net", "workshop_test"),
        "workshop.list": ("net", "workshop_list"),
        "workshop.search": ("net", "workshop_search"),
        "workshop.download": ("net", "workshop_download"),
        "workshop.like": ("net", "workshop_like"),
        "workshop.upload": ("net", "workshop_upload"),
        "workshop.plugins": ("net", "workshop_plugins"),
        "workshop.install_plugin": ("net", "workshop_install_plugin"),
    }



    def api_poll(self, last_seq):
        with self._lock:
            items = [m for m in self.messages if m["seq"] > last_seq]
            return {"items": items, "streaming": self.streaming, "busy": self.busy,
                    "opening_loading": self.opening_loading,
                    "tokens": self.total_tokens, "epoch": self.render_epoch,
                    "choices": self._choices_state(),
                    "mechanism": {"config": getattr(self.core, "_mech_config", None),
                                  "state": self.core.mechanism_snapshot()},
                    "battle": self.core.battle_ui_state(),
                    # 分道执行的结果流：异步任务（工坊/语音/记忆…）干完了从这里回来，
                    # 前端不需要为它们额外开通道，坐着现有的 poll 就行。
                    "jobs": self._jobs_delta()}



    def api_pick_choice(self, text):
        """Galgame 选项：点击某个选项 = 隐藏 ROLL 出结果 + 以该行动作为玩家输入发言"""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "err": "empty"}
        if self.busy:
            return {"ok": False, "err": "busy"}
        # 选项效果（好感/状态）：从插件当前选项里按文本匹配
        p = self._choices_plugin()
        item = None
        if p:
            try:
                for it in (getattr(p, "choices", None) or []):
                    if isinstance(it, dict) and it.get("text") == text:
                        item = it
                        break
            except Exception:
                pass
        # 隐藏 ROLL：按内置概率表出结果
        effect, kind, note = self._roll_option(item or {"text": text})
        self.core.apply_mechanism_effect(effect)
        if kind == "rare":
            self.core.pending_event = {"id": "_roll_rare", "name": "命运的眷顾",
                                       "prompt": "（稀有事件）这段剧情出现了意想不到的转折，"
                                                 "请自然地演出一个令人惊喜的展开。"}
            if note:
                self._append_sys(note)
        elif kind == "chosen":
            self.core.pending_event = {"id": "_roll_chosen", "name": "天选",
                                       "prompt": "（天选事件）千分之一的天命眷顾发生了！"
                                                 "请演出一个不可思议的、足以载入史册的剧情转折。"}
            if note:
                self._append_sys(note)
        elif kind == "collapse":
            self.core.pending_event = {"id": "_roll_collapse", "name": "坍缩",
                                       "prompt": "（坍缩事件）十万分之一的奇迹坍缩成现实！"
                                                 "战斗数值全部坍缩为 2000。"
                                                 "请演出一个撼动世界观的、堪称神话的剧情展开。"}
            try:
                self.core.collapse_battle_values()
            except Exception:
                pass
            if note:
                self._append_sys(note)
        elif kind in ("crit", "fail") and note:
            self._append_sys(note)
        # 世界线切换（B）：隐藏 ROLL 命中预设世界线时自动跳线（如坍缩→黑化线）
        self._maybe_world_line_on(kind)
        # 选项是按钮上的短标签；真正发言用 "say"（生成时补全好的玩家台词）。
        # 没有 say（旧存档、模型没给、或用户关掉了这个开关）就退回标签 —— 行为与以前一致。
        say = ""
        if isinstance(item, dict):
            say = str(item.get("say") or "").strip()
        if say and p is not None:
            try:
                if not p.get_setting("use_say", True):
                    say = ""
            except Exception:
                pass
        self._clear_choices()
        self._send_text(say or text, None, None, is_choice=True)
        return {"ok": True}



    def api_cyoa(self):
        """Galgame 选项：手动生成一组剧情选项（不写进聊天记录）"""
        p = self._choices_plugin()
        if not p or not p.enabled:
            return {"ok": False, "err": "插件未启用（⚙️ 设置 → 插件 → Galgame 选项）"}
        ok, msg = p.manual_generate()
        return {"ok": ok, "msg": msg}



    def api_battle_move(self, move_id):
        """战斗：玩家出招 → 引擎结算伤害/消耗 → 结算文本作为系统横幅 + 行动作为玩家消息发出（AI 演出）"""
        move_id = (move_id or "").strip()
        if not move_id:
            return {"ok": False, "err": "empty"}
        if self.busy:
            return {"ok": False, "err": "busy"}
        cfg = self.core._battle_config()
        if not cfg:
            return {"ok": False, "err": "当前角色未启用战斗系统"}
        move_name = move_id
        for m in (cfg.get("moves") or []):
            if isinstance(m, dict) and str(m.get("id", "")).strip() == move_id:
                move_name = str(m.get("name") or m.get("id"))
                break
        txt, is_legend = self.core.resolve_battle_move(move_id)
        if txt is None:
            return {"ok": False, "err": "招式不存在"}
        # 天选之人：0.00001% 战斗奇迹
        if is_legend:
            self.core.pending_event = {"id": "_battle_legend", "name": "天选之人",
                                       "prompt": "（传说事件）战斗中发生了十万分之一的奇迹！"
                                                 "请演出一个足以载入史册的惊天转折。"}
            self._append_sys("🌟 天选之人：十万分之一的战斗奇迹被触发了！")
        if txt.startswith("⚠️"):
            self._append_sys(txt)
            return {"ok": True, "msg": txt}
        self._append_sys(txt)
        # 结算结果注入下一轮请求（AI 知道伤害数字，演出受击反应）
        self.core.pending_event = {"id": "_battle_result", "name": "战斗结算",
                                   "prompt": f"（战斗结算）{txt} 请以角色口吻演出受击反应与战况。"}
        self._send_text(f"使用 {move_name}", None, None)
        return {"ok": True, "msg": txt}



    def api_quick_replies(self):
        """Quick Reply 列表：全局 quick_replies.json + 当前激活卡片的 card_quick_replies"""
        out = []
        try:
            with open(os.path.join(self.base_dir, "quick_replies.json"), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                out.extend({"label": str(x.get("label") or ""), "text": str(x.get("text") or "")}
                           for x in data if isinstance(x, dict) and x.get("label"))
        except Exception:
            pass
        # 当前卡片自带快捷回复（高级设置）排在最前
        for name in self.selected_roles:
            for r in self.roles:
                if r["name"] == name:
                    adv = (r.get("data") or {}).get("advanced") or {}
                    for q in adv.get("card_quick_replies") or []:
                        if q.get("label"):
                            out.insert(0, {"label": str(q["label"]), "text": str(q.get("text") or "")})
                    break
        return out

    # ---------- 正则管道（ST 风格：清洗/格式化；存储前应用，树状天然一致） ----------


    def api_dismiss_welcome(self):
        """标记首次引导已看完（不再弹引导框）"""
        self.config["welcome_shown"] = True
        self._save_config()
        return {"ok": True}



    def api_send(self, text, image_b64=None, mime=None):
        text = (text or "").strip()
        if self.busy:
            return {"ok": False, "err": "busy"}
        if not text and not image_b64:
            return {"ok": False, "err": "empty"}
        if text.startswith("/"):
            travel = self._handle_travel(text)
            if travel:
                self._append_sys(text, kind="user", speaker="你")
                self._append_sys(travel)
                return {"ok": True}
            if text.strip().lower().startswith("/mettertools"):
                # METTERTOOLS：按上限百分比一键填好感（罪恶都市梗；/mettertools 90 = 填到 90%）
                self._append_sys(text, kind="user", speaker="你")
                parts = text.split()
                pct = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
                val = self.core.set_affection_percent(pct)
                if val is None:
                    self._append_sys("⚠️ 当前角色未启用好感度（机制卡 → ❤ 好感度）")
                else:
                    self._append_sys(f"✨ METTERTOOLS！好感度已填至 {pct}% → {val}。")
                return {"ok": True}
            if text.strip() == "/read" or text.startswith("/read "):
                self._append_sys(text, kind="user", speaker="你")
                arg = text[5:].strip() if text.startswith("/read ") else None
                r = self.api_read_document(arg)
                if r.get("ok"):
                    self._append_sys("✅ 已注入文档上下文（可用 /readclear 清除）")
                elif r.get("err") != "cancelled":
                    self._append_sys("⚠️ " + r.get("err", "读取失败"))
                return {"ok": True}
            if text.strip() == "/readclear":
                self._append_sys(text, kind="user", speaker="你")
                self.api_clear_document()
                return {"ok": True}
            result = self.plugin_manager.handle_command(text)
            self._append_sys(text, kind="user", speaker="你")
            self._append_sys(result or i18n.t("unknown_cmd", "未知命令"))
            return {"ok": True}
        # Quick Reply 宏展开：{player} {char} {world} {random:a|b|c}
        text = self._expand_macros(text)
        processed = self.plugin_manager.onMessageSend(text) if hasattr(self.plugin_manager, "onMessageSend") else text
        if processed is None:
            return {"ok": False, "err": "blocked"}
        # 翻译隐藏：显示/存储用原文，发给 AI 用译文（中字日配不露痕迹）
        display_text, send_text = self._split_hidden(processed)
        # 玩家发送新消息（打字或点选项之外的自由输入）后，旧剧情选项作废
        self._clear_choices()
        image = None
        if image_b64:
            image = "data:" + (mime or "image/png") + ";base64," + image_b64
        # 传图补丁：先视觉描述（后台线程）
        if image_b64:
            self.busy = True
            speaker = (self.persona or {}).get("name") or "你"
            node_id = self.core.add_user_message(display_text)  # 树里存原文（翻译隐藏）
            try:
                self.core.tree.nodes[node_id].metadata["speaker"] = speaker
            except Exception:
                pass
            self.node_images[node_id] = image
            self._rebuild_messages()
            threading.Thread(target=self._vision_then_send,
                             args=(node_id, send_text, image_b64, mime), daemon=True).start()  # 发译文给 AI
            return {"ok": True}
        self._send_text(display_text, send_text, None)

        return {"ok": True}



    def api_travel(self, name):
        """穿梭：把角色移动到指定世界（世界书条目只跟随当前世界）"""
        name = (name or "").strip()
        if not name or name not in self.selected_worlds:
            return {"ok": False, "err": "请先勾选该世界再穿越"}
        self.current_world = name
        self.core.set_current_world(name)
        self.config["current_world"] = name
        self._save_config()
        return {"ok": True, "current": name}



    def api_regenerate(self, seq):
        """重新生成：为最后一条 AI 消息生成新候选（滑条）"""
        msg = next((m for m in self.messages if m["seq"] == seq), None)
        if not msg or msg["kind"] != "ai":
            return {"ok": False, "err": "只能对 AI 消息重新生成"}
        if self.busy:
            return {"ok": False, "err": "busy"}
        node = self.core.tree.nodes.get(msg["node_id"])
        if not node or not node.parent_id or node.parent_id not in self.core.tree.nodes:
            return {"ok": False, "err": "节点不存在"}
        self._start_fetch(node.parent_id)
        return {"ok": True}



    def api_edit_message(self, seq, new_content):
        """编辑消息：AI 消息原地改；用户消息开新分支并自动重新生成"""
        new_content = (new_content or "").strip()
        if not new_content:
            return {"ok": False, "err": "内容不能为空"}
        msg = next((m for m in self.messages if m["seq"] == seq), None)
        if not msg:
            return {"ok": False, "err": "无效消息"}
        node = self.core.tree.nodes.get(msg["node_id"])
        if not node:
            return {"ok": False, "err": "节点不存在"}
        if node.role == "assistant":
            node.content = new_content
            self._save_tree()
            self._rebuild_messages()
            return {"ok": True}
        if self.busy:
            return {"ok": False, "err": "busy"}
        new_id = self.core.tree.add_node("user", new_content,
                                         parent_id=node.parent_id,
                                         metadata=dict(node.metadata or {}))
        if node.id in self.node_images:
            self.node_images[new_id] = self.node_images[node.id]
        self._start_fetch(new_id)
        return {"ok": True}



    def api_branches(self):
        """列出可切换的其他分支（叶子节点）"""
        tree = self.core.tree
        out = []
        for nid, node in tree.nodes.items():
            if node.role == "system" or node.children_ids:
                continue
            if nid == tree.current_leaf_id:
                continue
            previews = []
            n = node
            depth = 0
            while n is not None and len(previews) < 2:
                if n.role != "system":
                    previews.append(n.content)
                depth += 1
                if n.parent_id and n.parent_id in tree.nodes:
                    n = tree.nodes[n.parent_id]
                else:
                    break
            previews.reverse()
            out.append({"node_id": nid, "kind": node.role, "depth": depth,
                        "preview": " / ".join((p or "").replace(chr(10), " ")[:40] for p in previews)})
        out.sort(key=lambda x: -x["depth"])
        return out


