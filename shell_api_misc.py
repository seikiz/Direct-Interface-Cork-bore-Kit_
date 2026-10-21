# -*- coding: utf-8 -*-
"""shell_api_misc —— 从 Kit.py 拆出的 mixin（^api_card|^api_export|^api_save|^api_delete|^api_create|^api_update|^api_clear|^api_switch|^api_memory|^api_）。

包含方法：api_job_submit、api_memory_audit、api_jobs_status、api_poll、api_pick_choice、api_cyoa、api_battle_move、api_quick_replies、api_dismiss_welcome、api_send、api_travel、api_create_role…

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

from shell_util import BASE_DIR, BUILTIN_RELAY, PROVIDERS, assemble_role_prompt

import app_version
import doc_reader
import i18n
import image_gen
import jobs
import json
import mem_isolate
import novel_export
import os
import plugin_manager
import preference_export
import ranker
import save_guard
import shutil
import threading
import uuid
import zipfile

class ApiMiscMixin:
    """shell_api_misc"""

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


    def api_job_submit(self, kind, args=None):
        """投一个异步任务。返回 {ok, job} —— 结果稍后从 poll 的 jobs 里回来。"""
        import jobs
        spec = self.JOB_KINDS.get(str(kind or ""))
        if not spec:
            return {"ok": False, "err": "未知任务类型：" + str(kind)[:40]}
        lane, api_name = spec
        fn = getattr(self, "api_" + api_name, None)
        if not callable(fn):
            return {"ok": False, "err": "任务实现缺失：api_" + api_name}
        argv = args if isinstance(args, (list, tuple)) else []
        jid = jobs.submit(lane, fn, *argv, name=kind)
        if jid is None:
            # 线满了：明确告诉前端（它可以退化成同步调用），而不是悄悄不动
            return {"ok": False, "err": "任务队列已满（%s）" % lane, "busy_lane": lane}
        return {"ok": True, "job": jid, "lane": lane}


    def api_memory_audit(self):
        """记忆隔离体检：人物专属记忆里有没有混进别人、世界记忆是否独立。

        返回 {ok, verdict, report(人话), problems, legacy, warnings, migration(迁移计划), stats}
        """
        import mem_isolate
        try:
            names = [r.get("name") for r in (self.roles or []) if r.get("name")]
        except Exception:
            names = []
        mem_dir = os.path.join(self.base_dir, "memory")
        try:
            rep = mem_isolate.audit(mem_dir, role_names=names)
        except Exception as e:
            return {"ok": False, "err": "体检失败：" + str(e)[:140]}
        out = {"ok": True, "verdict": rep.get("verdict"),
               "report": mem_isolate.render_report(rep),
               "problems": rep.get("problems") or [],
               "legacy": rep.get("legacy") or [],
               "warnings": rep.get("warnings") or [],
               "stats": rep.get("stats") or {},
               "path": mem_dir}
        if rep.get("verdict") in ("legacy", "leaky"):
            try:
                out["migration"] = mem_isolate.plan_migration(mem_dir, role_names=names)
            except Exception:
                out["migration"] = []
        return out


    def api_jobs_status(self):
        """分道执行状态：每条线在跑什么、队列多长、最近耗时/错误。"""
        try:
            import jobs
            return {"ok": True, **jobs.status()}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}


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


    def api_create_role(self, name, fields_json=None):
        name = (name or "").strip()
        if not name:
            return {"ok": False, "err": "empty"}
        legacy, fields, unlocked, advanced = self._parse_role_input(name, fields_json)
        advanced = self._clean_advanced(advanced)
        prompt = assemble_role_prompt(name, fields, legacy)
        if not prompt:
            return {"ok": False, "err": "empty"}
        fn = self._safe_name(name) + ".json"
        data = {"name": name, "system_prompt": prompt, "legacy": legacy,
                "unlocked": bool(unlocked)}
        for k, v in fields.items():
            if v:
                data[k] = v
        if advanced:
            data["advanced"] = advanced
        save_guard.atomic_write_json(os.path.join(self.save_dir, fn), data)
        self.roles.append({"name": name, "file": fn, "prompt": prompt, "data": data,
                           "fields": fields, "legacy": legacy, "unlocked": bool(unlocked)})
        return {"ok": True}


    def api_update_role(self, name, fields_json=None):
        """编辑人物卡（保持文件名/头像/聊天树/卡数据，只更新设定与结构化字段）"""
        if self._is_card_locked(name):
            return {"ok": False, "err": "🎭 会期进行中，该角色卡已锁定（先 /trpg end 解锁）"}
        legacy, fields, unlocked, advanced = self._parse_role_input(name, fields_json)
        advanced = self._clean_advanced(advanced)
        prompt = assemble_role_prompt(name, fields, legacy)
        if not prompt:
            return {"ok": False, "err": "empty"}
        for r in self.roles:
            if r["name"] == name:
                r["prompt"] = prompt
                r["fields"] = fields
                r["legacy"] = legacy
                r["unlocked"] = bool(unlocked)
                data = dict(r.get("data") or {})
                data["name"] = name
                data["system_prompt"] = prompt
                data["legacy"] = legacy
                data["unlocked"] = bool(unlocked)
                for k, v in fields.items():
                    if v:
                        data[k] = v
                    else:
                        data.pop(k, None)
                if advanced:
                    data["advanced"] = advanced
                else:
                    data.pop("advanced", None)
                r["data"] = data
                try:
                    # 覆盖前先留底：清空机制/结局等"破坏性编辑"也能从 backup/ 恢复回
                    save_guard.backup_file(os.path.join(self.save_dir, r["file"]))
                    save_guard.atomic_write_json(os.path.join(self.save_dir, r["file"]), data)
                except Exception:
                    pass
                if name in self.selected_roles:
                    self._activate_core(reload_tree=False)
                return {"ok": True}
        return {"ok": False, "err": "not found"}


    def api_create_world(self, name, description, rules_text, entries_json=None, params_json=None):
        """创建世界卡：rules 每行一条；entries 世界书条目；params 世界参数（科技/超自然/物理等）"""
        name = (name or "").strip()
        if not name or not (description or "").strip():
            return {"ok": False, "err": "empty"}
        rules = [x.strip() for x in (rules_text or "").splitlines() if x.strip()]
        data = {"name": name, "description": (description or "").strip(),
                "rules": rules, "entries": self._norm_entries(entries_json),
                "params": self._parse_world_params(params_json)}
        fn = self._safe_name(name) + ".json"
        save_guard.atomic_write_json(os.path.join(self.world_dir, fn), data)
        self.worlds.append(data)
        if name in self.selected_worlds:
            self.core.set_worlds(self._worlds_for_core())
        return {"ok": True}


    def api_update_world(self, name, description, rules_text, entries_json=None, params_json=None):
        """编辑世界卡（按名定位；entries_json/params_json 为 None 时保留原值）"""
        for w in self.worlds:
            if w.get("name") == name:
                w["description"] = (description or "").strip()
                w["rules"] = [x.strip() for x in (rules_text or "").splitlines() if x.strip()]
                if entries_json is not None:
                    w["entries"] = self._norm_entries(entries_json)
                if params_json is not None:
                    w["params"] = self._parse_world_params(params_json)
                try:
                    fn = self._safe_name(name) + ".json"
                    # 覆盖前留底：破坏性编辑可从 backup/ 恢复
                    save_guard.backup_file(os.path.join(self.world_dir, fn))
                    save_guard.atomic_write_json(os.path.join(self.world_dir, fn), w)
                except Exception:
                    pass
                if name in self.selected_worlds:
                    self.core.set_worlds(self._worlds_for_core())
                return {"ok": True}
        return {"ok": False, "err": "not found"}


    def api_delete_world(self, name):
        for w in self.worlds:
            if w.get("name") == name:
                try:
                    # 删除前先留底到 backup/：误删可从备份捞回
                    save_guard.backup_file(os.path.join(self.world_dir, self._safe_name(name) + ".json"))
                    os.remove(os.path.join(self.world_dir, self._safe_name(name) + ".json"))
                except Exception:
                    pass
        self.worlds = [w for w in self.worlds if w.get("name") != name]
        self.selected_worlds = [n for n in self.selected_worlds if n != name]
        return {"ok": True}


    def api_ai_draft(self, kind, idea):
        """AI 起草：人物卡/世界卡（需已配置 API Key）"""
        idea = (idea or "").strip()
        if not idea:
            return {"ok": False, "err": "empty idea"}
        client = getattr(self.core, "client", None)
        if not client:
            return {"ok": False, "err": "未配置 API Key，请先在设置里填写"}
        fence = chr(96) * 3
        NL = chr(10)
        if kind == "world":
            prompt = ("根据下面的灵感，设计一个世界卡。只输出 JSON（不要多余解释）：" + NL +
                      '{"name": "世界名", "description": "背景描述", "params": {"tech_level": "科技水平", "supernatural": "超自然体系（无则写：无）", "physics": "物理法则（如：与地球相同）", "time_flow": "时间流速", "climate": "气候环境", "geography": "地理格局", "politics": "政治格局", "economy": "经济体系"}, "rules": ["规则1", "规则2", "规则3"]}' + NL +
                      "灵感：" + idea)
        else:
            prompt = ("根据下面的灵感，撰写一张角色卡。只输出 JSON（不要多余解释）：" + NL +
                      '{"name": "角色名", "appearance": "外貌", "personality": "性格（详写）", "background": "过去经历（详写）", "speech": "说话方式（语气/口癖/句式）", "first_mes": "开场白", "mes_example": "对话示例", "notes": "备注"}' + NL +
                      "灵感：" + idea)
        model = self.config.get("model", "deepseek-flash")
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=False, timeout=90,
            )
            text = (resp.choices[0].message.content or "").strip()
            if fence in text:
                parts = text.split(fence)
                for p in parts:
                    p = p.strip()
                    if p.startswith("json"):
                        p = p[4:].strip()
                    if p.startswith("{"):
                        text = p
                        break
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start:end + 1]
            data = json.loads(text)
            return {"ok": True, "data": data}
        except Exception as e:
            return {"ok": False, "err": "AI 起草失败：" + str(e)[:200]}


    def api_delete_role(self, name):
        if self._is_card_locked(name):
            return {"ok": False, "err": "🎭 会期进行中，该角色卡已锁定（先 /trpg end 解锁）"}
        was_selected = name in self.selected_roles
        for r in self.roles:
            if r["name"] == name:
                try:
                    # 删除前先留底到 backup/：误删可从备份捞回（"清空有还原"）
                    save_guard.backup_file(os.path.join(self.save_dir, r["file"]))
                    os.remove(os.path.join(self.save_dir, r["file"]))
                except Exception:
                    pass
        self.roles = [r for r in self.roles if r["name"] != name]
        self.selected_roles = [n for n in self.selected_roles if n != name]
        self.config["selected_roles"] = list(self.selected_roles)
        self.config["last_role"] = self.selected_roles[0] if self.selected_roles else ""
        self._save_config()
        if was_selected:
            self._activate_core(reload_tree=True)
        return {"ok": True}


    def api_card_saves(self, name):
        """列出某角色卡的存档点（只返回摘要，不返回整棵树）"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        return {"ok": True, "saves": [self._save_summary(s) for s in saves],
                "active_save": data.get("active_save") or None}


    def api_card_save_new(self, name, label):
        """『新存档』：把当前进度固化为一个新的存档点，并设为当前活动存档"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        snap = self._card_snapshot()
        sid = "s-" + uuid.uuid4().hex[:10]
        entry = {"id": sid,
                 "label": (label or "").strip() or "存档 " + str(len(saves) + 1),
                 "created_ts": snap["_tree_ts"], "updated_ts": snap["_tree_ts"],
                 "history_tree": snap["history_tree"], "mechanism_state": snap["mechanism_state"],
                 "_tree_ts": snap["_tree_ts"], "progress": snap["progress"]}
        saves.append(entry)
        data["saves"] = saves
        data["active_save"] = sid
        self._commit_card_data(r, data)
        return {"ok": True, "save": self._save_summary(entry), "active_save": sid}


    def api_card_save(self, name, label, save_id=None):
        """『存档』：把当前进度写入目标存档点；无目标则新建一个（可附新标签）"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        sid = save_id or data.get("active_save")
        snap = self._card_snapshot()
        entry = None
        if sid:
            entry = next((s for s in saves if s.get("id") == sid), None)
            if entry:
                entry["history_tree"] = snap["history_tree"]
                entry["mechanism_state"] = snap["mechanism_state"]
                entry["_tree_ts"] = snap["_tree_ts"]
                entry["updated_ts"] = snap["_tree_ts"]
                entry["progress"] = snap["progress"]
                if label and str(label).strip():
                    entry["label"] = str(label).strip()
            else:
                sid = None
        if not sid:
            sid = "s-" + uuid.uuid4().hex[:10]
            entry = {"id": sid,
                     "label": (label or "").strip() or "存档 " + str(len(saves) + 1),
                     "created_ts": snap["_tree_ts"], "updated_ts": snap["_tree_ts"],
                     "history_tree": snap["history_tree"], "mechanism_state": snap["mechanism_state"],
                     "_tree_ts": snap["_tree_ts"], "progress": snap["progress"]}
            saves.append(entry)
        data["saves"] = saves
        data["active_save"] = sid
        self._commit_card_data(r, data)
        return {"ok": True, "save": self._save_summary(entry), "active_save": sid}


    def api_card_save_load(self, name, save_id):
        """『读档/切换』：把指定存档点还原为当前会话（对话树 + 机制状态 + 进度时间戳）"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        entry = next((s for s in saves if s.get("id") == save_id), None)
        if not entry:
            return {"ok": False, "err": "存档不存在"}
        data["history_tree"] = entry.get("history_tree")
        data["mechanics_state"] = entry.get("mechanism_state")
        data["_tree_ts"] = entry.get("_tree_ts") or data.get("_tree_ts")
        data["active_save"] = save_id
        self._commit_card_data(r, data)
        # 该角色当前被选中且是核心会话角色时，重载 core 以刷新聊天树与机制状态
        if name in self.selected_roles:
            self._activate_core(reload_tree=True)
        return {"ok": True}


    def api_card_save_delete(self, name, save_id):
        """『删除』：移除一个存档点；若删除的是活动存档则清空活动指针"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        if not isinstance(saves, list):
            saves = []
        saves = [s for s in saves if s.get("id") != save_id]
        data["saves"] = saves
        if data.get("active_save") == save_id:
            data["active_save"] = None
        self._commit_card_data(r, data)
        return {"ok": True}


    def api_card_save_rename(self, name, save_id, label):
        """『重命名』：修改存档点标签"""
        r = self._role_by_name(name)
        if not r:
            return {"ok": False, "err": "角色不存在"}
        data = r.get("data") or {}
        saves = data.get("saves") or []
        entry = next((s for s in saves if s.get("id") == save_id), None)
        if not entry:
            return {"ok": False, "err": "存档不存在"}
        entry["label"] = (label or "").strip() or entry.get("label") or "未命名存档"
        self._commit_card_data(r, data)
        return {"ok": True, "save": self._save_summary(entry)}


    def api_clear_chat_wallpaper(self):
        removed = False
        for e in self._WALLPAPER_EXTS:
            q = os.path.join(self.save_dir, "wallpaper" + e)
            if os.path.exists(q):
                try:
                    os.remove(q)
                    removed = True
                except Exception:
                    pass
        return {"ok": True, "removed": removed}

    # ---------- Live2D 看板娘（核心态） ----------

    def api_trpg_end(self):
        """退出跑团（核心）：结束会话、解除角色卡锁定、复位轮次与行动者。"""
        try:
            p = self.plugin_manager.get_plugin("跑团模式")
            if p is not None and hasattr(p, "end_session"):
                msg = p.end_session()
                return {"ok": True, "msg": msg}
            pth = os.path.join(self.save_dir, ".trpg_lock.json")
            if os.path.exists(pth):
                try:
                    os.remove(pth)
                except Exception:
                    pass
            return {"ok": True, "msg": "🏁 已退出跑团模式"}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    # ---------- 滑条 / 编辑 / 分支 ----------
    # ---------- 漂移核查（三态 + 延迟定案） ----------

    def api_export_preferences(self):
        """把树里已经形成的偏好对导出成 JSONL（只读，不改任何东西）。

        为什么现在就要导：偏好信号只在产生的那一刻存在。你滑过去了，
        "他拒绝了哪条"就沉进树里 —— 不导出就永远拿不到，而且它只增不减。
        顺带给出【启发式与你实际选择的一致率】，那是"能不能用这个价值函数做前瞻"的实证依据。
        """
        try:
            import preference_export
        except Exception as e:
            return {"ok": False, "err": "缺少 preference_export 模块：" + str(e)[:120]}
        try:
            r = preference_export.scan_dir(self.save_dir)
        except Exception as e:
            return {"ok": False, "err": "扫描存档失败：" + str(e)[:200]}
        recs = r.get("records") or []
        if not recs:
            return {"ok": True, "samples": 0, "by_role": {},
                    "msg": "还没有可用的偏好样本。样本来自「同一个问题下生成过多条候选」——"
                           "多用几次重 roll（♻ 重新生成）就会有。"}
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self._pick_save_path("DICK_偏好数据_" + ts + ".jsonl", ("JSONL (*.jsonl)",))
        if not out.lower().endswith(".jsonl"):
            out += ".jsonl"
        try:
            n = preference_export.export_jsonl(recs, out)
        except Exception as e:
            return {"ok": False, "err": "写入失败：" + str(e)[:160]}
        s = r.get("sum") or {}
        return {"ok": True, "file": out, "name": os.path.basename(out), "written": n,
                "by_role": r.get("by_role") or {}, "stats": s,
                "msg": "已导出 %d 条偏好对（来自 %d 个角色）" %
                       (n, len(r.get("by_role") or {}))}

    # ---------- 平民化训练（调试面板 · 非开发者可用） ----------

    def api_event_progress(self):
        """事件进度面板：每个事件现在是什么状态（已触发/冷却中/差多少好感/可以触发）。

        命名约定：pywebview 暴露给前端的方法一律以 api_ 开头，
        前端写 pywebview.api.event_progress()（前缀由桥自动加）。
        所以这里必须是 api_event_progress，两边去掉前缀后同名才算接上。
        （test_js_api_binding 会抓这个名字不一致，静默失效很难查。）
        """
        cfg = None
        try:
            cfg = self.core._mech_config
        except Exception:
            cfg = None
        try:
            items = self.core.event_progress(cfg)
        except Exception as e:
            return {"ok": False, "err": "读事件进度失败：" + str(e)[:160]}
        st = self.core.mechanism_state or {}
        cfgs = cfg if isinstance(cfg, dict) else {}
        aff_cfg = cfgs.get("affection") if isinstance(cfgs.get("affection"), dict) else None
        return {
            "ok": True,
            "enabled": bool(cfgs.get("events")),
            "affection": st.get("affection"),
            "aff_max": (int(aff_cfg.get("max", 100) or 100) if aff_cfg else None),
            "turn": st.get("_turn", 0),
            "items": items,
            "fired": sum(1 for x in items if x.get("fired")),
            "total": len(items),
        }


    def api_memory_debug(self):
        """记忆调试：看当前历史每条的记忆清晰度、年龄、隐藏衰减率、还剩多少寿命。

        为什么必须有这个：遗忘被刻意设计成【不可建模】的（每个节点一个隐藏衰减率），
        所以从外部观察根本判断不出它有没有坏。必须能直接看内部数字。
        """
        import time as _t
        core = self.core
        try:
            import salience as _sal
        except Exception as e:
            return {"ok": False, "err": "缺 salience 模块：" + str(e)[:120]}
        now = _t.time()
        try:
            chain = core.tree.get_current_chain()
        except Exception as e:
            return {"ok": False, "err": "读历史失败：" + str(e)[:120]}
        rows = []
        for m in chain:
            if m.get("role") == "system":
                continue
            nid = m.get("_node_id")
            s = _sal.salience(m, now=now) if nid else 0.0
            dec = _sal.hidden_decay(nid) if nid else 0.0
            age_days = 0.0
            try:
                ts = float(m.get("_ts") or 0)
                if ts:
                    age_days = max(0.0, (now - ts) / 86400.0)
            except (TypeError, ValueError):
                pass
            rows.append({
                "id": nid,
                "age_days": round(age_days, 2),
                "salience": round(s, 4),
                "decay_per_day": round(dec, 4),
                "alive": bool(s >= _sal.KEEP_THRESHOLD),
                "role": m.get("role"),
                "preview": str(m.get("content") or "")[:40],
            })
        alive = [r for r in rows if r["alive"]]
        return {
            "ok": True,
            "threshold": _sal.KEEP_THRESHOLD,
            "recent_window": getattr(core, "recent_window", None),
            "total": len(rows),
            "alive": len(alive),
            "forgotten": len(rows) - len(alive),
            "rows": rows,
            "params": {"decay_min": _sal.DECAY_MIN, "decay_max": _sal.DECAY_MAX,
                       "decay_portion": _sal.DECAY_PORTION},
        }


    def api_ranker_status(self):
        """给非开发者看的：数据够不够、模型有没有、它在用什么特征。"""
        out = {"ok": True}
        try:
            import preference_export, ranker
        except Exception as e:
            return {"ok": False, "err": "缺少模块：" + str(e)[:120]}
        try:
            r = preference_export.scan_dir(self.save_dir)
            recs = r.get("records") or []
            rd = ranker.readiness(recs)
        except Exception as e:
            return {"ok": False, "err": "读偏好数据失败：" + str(e)[:160]}
        out["readiness"] = rd
        out["by_role"] = r.get("by_role") or {}
        # 现在有多少条没打分的样本（训之前先打分才有一致率可比）
        s = r.get("sum") or {}
        out["heuristic_agreement"] = s.get("agreement")
        m = ranker.load(self._ranker_path())
        if m:
            out["model"] = {"train_acc": m.get("train_acc"),
                            "holdout_acc": m.get("holdout_acc"),
                            "n_samples": m.get("n_samples"),
                            "top": ranker.explain(m, top=6)}
        else:
            out["model"] = None
        out["enabled"] = bool((self.config.get("ranker") or {}).get("on"))
        return out


    def api_train_ranker(self):
        """在本地把偏好数据训成一个排序器。纯 numpy，几秒钟，不需要服务器。"""
        try:
            import preference_export, ranker
        except Exception as e:
            return {"ok": False, "err": "缺少模块：" + str(e)[:120]}
        try:
            r = preference_export.scan_dir(self.save_dir)
            recs = r.get("records") or []
        except Exception as e:
            return {"ok": False, "err": "读偏好数据失败：" + str(e)[:160]}
        # 案卷用当前角色的（特征里的 confab 要用）
        try:
            m = ranker.train(recs, keys=self._drift_keys(), case_text=self._case_text())
        except Exception as e:
            return {"ok": False, "err": "训练失败：" + str(e)[:200]}
        if not m.get("ok"):
            return {"ok": False, "err": m.get("err"), "readiness": m.get("readiness")}
        try:
            ranker.save(m, self._ranker_path())
        except Exception as e:
            return {"ok": False, "err": "模型存不下来：" + str(e)[:160]}
        return {"ok": True, "train_acc": m.get("train_acc"),
                "holdout_acc": m.get("holdout_acc"),
                "n_pairs": m.get("n_pairs"), "n_samples": m.get("n_samples"),
                "top": ranker.explain(m, top=6),
                "path": self._ranker_path(),
                "msg": "训练完成（纯本地，没有联网、没有用你的 API Key）"}


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


    def api_switch_swipe(self, seq, index):
        """切换滑条：选择父用户节点下的第 index 条 assistant 候选"""
        msg = next((m for m in self.messages if m["seq"] == seq), None)
        if not msg or msg["kind"] != "ai":
            return {"ok": False, "err": "无效消息"}
        node = self.core.tree.nodes.get(msg["node_id"])
        if not node or not node.parent_id or node.parent_id not in self.core.tree.nodes:
            return {"ok": False, "err": "节点不存在"}
        sibs = [cid for cid in self.core.tree.nodes[node.parent_id].children_ids
                if self.core.tree.nodes.get(cid) and self.core.tree.nodes[cid].role == "assistant"]
        try:
            target = sibs[int(index)]
        except (ValueError, IndexError):
            return {"ok": False, "err": "滑条越界"}
        self.core.tree.current_leaf_id = target
        self._save_tree()
        self._rebuild_messages()
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


    def api_switch_branch(self, node_id):
        tree = self.core.tree
        if not node_id or node_id not in tree.nodes:
            return {"ok": False, "err": "节点不存在"}
        tree.current_leaf_id = node_id
        self.core.restore_mechanisms(node_id)
        self._save_tree()
        self._rebuild_messages()
        return {"ok": True}


    def api_backtrack(self, node_id):
        """树状回溯：把对话定位到任意节点（从这里继续/切换分支）"""
        tree = self.core.tree
        if not node_id or node_id not in tree.nodes:
            return {"ok": False, "err": "节点不存在"}
        if node_id == tree.current_leaf_id:
            return {"ok": True}
        tree.current_leaf_id = node_id
        self.core.restore_mechanisms(node_id)
        self._save_tree()
        self._rebuild_messages()
        return {"ok": True}

    # ---------- 酒馆角色卡导入导出 ----------

    def api_import_card(self):
        """文件对话框导入酒馆角色卡（.png/.webp/.json）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("角色卡 (*.png;*.webp;*.json)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        return self._do_import_card(res[0])


    def api_export_card(self, name, fmt):
        """导出角色卡：fmt = json | png（酒馆 v2 格式，PNG 嵌卡）"""
        fmt = (fmt or "json").lower()
        if fmt not in ("json", "png"):
            return {"ok": False, "err": "格式必须是 json 或 png"}
        ext = "json" if fmt == "json" else "png"
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=self._safe_name(name) + "." + ext,
                file_types=("JSON (*.json)",) if fmt == "json" else ("PNG (*.png)",))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        path = res[0]
        if fmt == "json" and not path.lower().endswith(".json"):
            path += ".json"
        if fmt == "png" and not path.lower().endswith(".png"):
            path += ".png"
        return self._do_export_card(name, fmt, path)

    # ---------- 世界书条目 ----------

    def api_open_path(self, path):
        """在资源管理器中打开/定位文件（打包产物定位用）"""
        try:
            if path and os.path.exists(path):
                os.startfile(os.path.dirname(os.path.abspath(path)))
                return {"ok": True}
            return {"ok": False, "err": "not found"}
        except Exception as e:
            return {"ok": False, "err": str(e)}


    def api_toggle_unlock(self, name):
        """破甲模式快速开关（角色级：任一启用则对话注入破甲提示）"""
        for r in self.roles:
            if r["name"] == name:
                r["unlocked"] = not r.get("unlocked", False)
                data = dict(r.get("data") or {})
                data["unlocked"] = r["unlocked"]
                r["data"] = data
                try:
                    save_guard.atomic_write_json(os.path.join(self.save_dir, r["file"]), data)
                except Exception:
                    pass
                if name in self.selected_roles:
                    self._activate_core(reload_tree=False)
                return {"ok": True, "unlocked": r["unlocked"]}
        return {"ok": False, "err": "not found"}


    def api_read_document(self, path=None):
        """读入 Word/Excel 文档供 AI 分析（文件对话框或给定路径）"""
        if not path:
            try:
                import webview
                win = webview.windows[0] if getattr(webview, "windows", None) else None
                if win is None:
                    return {"ok": False, "err": "窗口未就绪"}
                res = win.create_file_dialog(
                    webview.FileDialog.OPEN, allow_multiple=False,
                    file_types=("文档 (*.docx;*.xlsx;*.txt)", "All files (*.*)"))
                if not res:
                    return {"ok": False, "err": "cancelled"}
                path = res[0]
            except Exception as e:
                return {"ok": False, "err": "对话框失败：" + str(e)}
        path = path.strip().strip('"')
        try:
            import doc_reader
            text = doc_reader.read_document(path)
        except ValueError as e:
            # 兼容 .txt 直读
            if path.lower().endswith(".txt"):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except Exception as e2:
                    return {"ok": False, "err": str(e2)}
            else:
                return {"ok": False, "err": str(e)}
        except Exception as e:
            return {"ok": False, "err": "读取失败：" + str(e)[:200]}
        if not text or not text.strip():
            return {"ok": False, "err": "文档内容为空"}
        cap = 20000
        if len(text) > cap:
            text = text[:cap] + chr(10) + "…（文档过长，已截断，可用 /readclear 清除）"
        self.core.set_document_context(text)
        self.loaded_document = {"name": os.path.basename(path), "chars": len(text)}
        self._append_sys("📄 已读入文档：" + self.loaded_document["name"] +
                         "（" + str(len(text)) + " 字符），后续对话自动参考")
        return {"ok": True, "name": self.loaded_document["name"], "chars": len(text)}


    def api_clear_document(self):
        self.core.clear_document_context()
        self.loaded_document = None
        self._append_sys("🧹 已清除文档上下文")
        return {"ok": True}


    def api_export_chat(self):
        """把当前聊天记录导出为 Word 文档"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename="聊天记录.docx",
                                         file_types=("Word (*.docx)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            path = res[0]
            if not path.lower().endswith(".docx"):
                path += ".docx"
            from docx import Document
            doc = Document()
            doc.add_heading("Direct-Interface Cork-bore Kit · 聊天记录", level=1)
            for m in self.messages:
                who = m.get("speaker") or ("你" if m.get("kind") == "user" else "AI")
                doc.add_paragraph("")
                p = doc.add_paragraph()
                run = p.add_run(who + "：")
                run.bold = True
                doc.add_paragraph(m.get("content") or "")
            doc.save(path)
            return {"ok": True, "file": os.path.basename(path)}
        except Exception as e:
            return {"ok": False, "err": "导出失败：" + str(e)[:200]}


    def api_export_novel(self, fmt="epub"):
        """把当前聊天记录导出成【小说】（EPUB / Word）。

        与 api_export_chat 的区别：那个导的是扁平消息列表（分支、重生成、回溯过的内容
        全糊在一起）；这个走树上的实际路径（root → current_leaf_id），并把当时没走过的
        分支收成脚注 —— 于是每局对话都能变成一部读得下去的作品。
        """
        import novel_export
        try:
            tree = self.core.get_all_nodes_data()
        except Exception as e:
            return {"ok": False, "err": "读取聊天树失败：" + str(e)[:120]}
        # 标题：当前选中的角色名（群聊就拼起来）
        try:
            names = [r.get("name") for r in (self.roles or [])
                     if r.get("name") in (self.selected_roles or [])]
        except Exception:
            names = []
        who = "、".join([n for n in names if n][:3]) or "对话"
        title = who + " · 对话小说"
        try:
            author = ((self.persona or {}).get("name") or "").strip()
        except Exception:
            author = ""
        fmt = (fmt or "epub").strip().lower()
        is_word = fmt in ("docx", "word")
        default_name = novel_export.safe_name(title) + (".docx" if is_word else ".epub")
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            types = ("Word (*.docx)",) if is_word else ("EPUB (*.epub)",)
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=default_name, file_types=types)
            if not res:
                return {"ok": False, "err": "cancelled"}
            path = res[0]
            want = ".docx" if is_word else ".epub"
            if not path.lower().endswith(want):
                path += want
        except Exception as e:
            return {"ok": False, "err": "保存对话框失败：" + str(e)[:120]}
        ok, msg = novel_export.export_novel(tree, fmt, path, title=title, author=author)
        if not ok:
            return {"ok": False, "err": msg}
        return {"ok": True, "file": os.path.basename(path), "path": path, "msg": msg,
                "title": title}


    def api_backup_password_check(self, password):
        """门面：口令强度判定在 modules/backup（不存任何东西）"""
        try:
            return self._backup_service().password_check(password or "")
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}


    def api_backup_make_password(self):
        """门面：随机强口令由 modules/backup 生成（32 字节 → base32，抄纸上收好）"""
        try:
            return self._backup_service().make_password()
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}


    def api_export_backup_encrypted(self, password):
        """加密备份：整体打包 → 用口令加密成【一个文件】。

        门面：打包内容（_backup_entries）与"存到哪"（保存对话框）留在壳层，
        口令闸门与容器封装在 modules/backup —— 那部分必须能脱离界面被单独测。
        """
        try:
            svc = self._backup_service()
        except Exception as e:
            return {"ok": False, "err": "缺少加密模块 crypto_core：" + str(e)[:120]}
        ok, err = svc.require_strong(password)
        if not ok:
            return {"ok": False, "err": err}
        try:
            import datetime as _dt
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            entries = self._backup_entries()
            raw_zip = self._zip_entries(entries, "DICK_备份_" + ts)
            blob = svc.seal(raw_zip, password)
            out = self._pick_save_path("DICK_加密备份_" + ts + self.BACKUP_EXT,
                                       ("DICK 加密备份 (*" + self.BACKUP_EXT + ")",))
            if not out.lower().endswith(self.BACKUP_EXT):
                out += self.BACKUP_EXT
            with open(out, "wb") as f:
                f.write(blob)
            return {"ok": True, "file": out, "name": os.path.basename(out),
                    "size": os.path.getsize(out),
                    "entries": len(entries),
                    "zip_bytes": len(raw_zip),
                    "container_bytes": len(blob),
                    "info": svc.info(blob)}
        except Exception as e:
            return {"ok": False, "err": "加密备份失败：" + str(e)[:200]}


    def api_import_backup_encrypted(self, password):
        """还原加密备份：解密 → 解压 → 覆盖 saves/worlds/personas/config。
        覆盖前会把原文件复制到 saves/backup/ 下，避免一失手全没了。

        门面：解密与铺盘在 modules/backup；这里只问用户要哪个文件。
        """
        try:
            svc = self._backup_service()
        except Exception as e:
            return {"ok": False, "err": "缺少加密模块：" + str(e)[:120]}
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=("DICK 加密备份 (*" + self.BACKUP_EXT + ")", "所有文件 (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)[:120]}
        if not res:
            return {"ok": False, "err": "cancelled"}
        src = res[0]
        try:
            with open(src, "rb") as f:
                blob = f.read()
        except Exception as e:
            return {"ok": False, "err": "读不到文件：" + str(e)[:120]}
        try:
            raw_zip = svc.unseal(blob, password)
        except Exception as e:
            return {"ok": False, "err": str(e)[:160]}
        try:
            import io
            import zipfile
            z = zipfile.ZipFile(io.BytesIO(raw_zip))
        except Exception as e:
            return {"ok": False, "err": "备份内容损坏：" + str(e)[:120]}

        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = os.path.join(self.save_dir, "backup", "restore_" + ts)
        try:
            restored = self._restore_from_zip(z, bak)
        except Exception as e:
            return {"ok": False, "err": "还原失败：" + str(e)[:200]}
        return {"ok": True, "restored": restored,
                "backup_dir": bak if os.path.isdir(bak) else "",
                "msg": "已还原：存档 %d / 世界 %d / 玩家卡 %d / 剧情包 %d / 设置 %d。"
                       "（原文件已备份到 saves/backup/）"
                       % (restored["saves"], restored["worlds"],
                          restored["personas"], restored["codex"],
                          restored["config"])}


    def api_export_backup(self):
        """一键备份：把所有角色卡(含聊天树)、世界卡、玩家卡、以及 config 打进一个 zip。
        安全网入口：用户把 zip 存到别处/云端，即可完整迁移/还原。默认存到桌面。"""
        try:
            import zipfile
            import datetime as _dt
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            # 选择保存位置（保存对话框优先；失败/无UI时退回桌面）
            fname = f"DICK_备份_{ts}.zip"
            out = None
            try:
                import webview
                win = webview.windows[0] if getattr(webview, "windows", None) else None
                if win is not None:
                    res = win.create_file_dialog(webview.FileDialog.SAVE,
                                                 save_filename=fname,
                                                 file_types=("Zip (*.zip)",))
                    if res:
                        out = res[0]
            except Exception:
                pass
            if not out:
                out = os.path.join(os.path.expanduser("~"), "Desktop", fname)
            if not out.lower().endswith(".zip"):
                out += ".zip"
            zipname = os.path.splitext(os.path.basename(out))[0]
            count = {"roles": 0, "worlds": 0, "persona": 0, "tree": 0, "config": 0}
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                # 角色卡（带聊天树）
                for r in self.roles:
                    data = dict(r.get("data") or {})
                    data["name"] = r["name"]
                    data["system_prompt"] = r.get("prompt") or data.get("system_prompt", "")
                    # 若内存树比存档新，用最新的
                    if r["name"] in self.selected_roles:
                        td = self.core.get_all_nodes_data()
                        if len(td.get("nodes", {})) > 1:
                            data["history_tree"] = td
                    z.writestr(f"{zipname}/saves/{r['file']}",
                               json.dumps(data, ensure_ascii=False, indent=2))
                    count["roles"] += 1
                    if isinstance(data.get("history_tree"), dict) and data["history_tree"].get("nodes"):
                        count["tree"] += 1
                # 世界卡
                for w in self.worlds:
                    fn = self._safe_name(w.get("name") or "") + ".json"
                    z.writestr(f"{zipname}/worlds/{fn}",
                               json.dumps(w, ensure_ascii=False, indent=2))
                    count["worlds"] += 1
                # 玩家卡 persona
                if self.persona:
                    z.writestr(f"{zipname}/personas/persona.json",
                               json.dumps(self.persona, ensure_ascii=False, indent=2))
                    count["persona"] = 1
                # config（脱敏加密写盘副本）
                safe_cfg = self._encrypt_config_secrets(self.config) or self.config
                z.writestr(f"{zipname}/config.json",
                           json.dumps(safe_cfg, ensure_ascii=False, indent=2))
                count["config"] = 1
            return {"ok": True, "file": out, "zip": os.path.basename(out),
                    "counts": count}
        except Exception as e:
            return {"ok": False, "err": "备份失败：" + str(e)[:200]}

    # ================= CODEX 专属 GALGAME（PC 端独有） =================
    # 傻瓜化：选文件夹自动归类立绘/背景/音乐/配音 → 生成剧本模板 → 播放器直接能播。
    # JSON 功能：codex.json 可视化编辑 + 校验 + zip 导入导出。

        """找到已构建好的播放器目录（含 DICK-Narrative.exe）；没有返回 None。
        先试约定位置，再在数据目录（及下两层）里扫一遍，容忍用户随便放。"""
        exe = self.PLAYER_EXE

        def has_exe(d):
            try:
                return bool(d) and os.path.isfile(os.path.join(d, exe))
            except Exception:
                return False

        b = self.base_dir
        dev = os.path.join(self.PLAYER_DIRNAME, "app", "build", "compose",
                           "binaries", "main", "app", self.PLAYER_DIRNAME)
        name = self.PLAYER_DIRNAME
        up1 = os.path.dirname(b)          # dist\DICK-HTML → dist\dist
        up2 = os.path.dirname(up1)        # 再上一层：打包版 DICK 就靠这个找到工程里的播放器
        cands = [
            os.environ.get("DICK_PLAYER_DIR"),
            os.path.join(b, dev),                              # 开发：构建输出
            os.path.join(b, "player", name),
            os.path.join(b, name + "-播放器"),
            os.path.join(b, "播放器", name),
            os.path.join(b, "播放器"),
            os.path.join(b, name),
            # 上一层 / 上两层：兼容「DICK-HTML 在子目录、播放器在工程根」这种布局
            os.path.join(up1, dev),
            os.path.join(up1, name + "-播放器"),
            os.path.join(up1, name),
            os.path.join(up2, dev),
            os.path.join(up2, name + "-播放器"),
            os.path.join(up2, name),
        ]
        for c in cands:
            if has_exe(c):
                return c

        # 兜底扫描：数据目录本身 → 一层子目录 → 两层子目录
        def subdirs(d):
            try:
                return [os.path.join(d, n) for n in sorted(os.listdir(d))
                        if os.path.isdir(os.path.join(d, n))]
            except Exception:
                return []

        for d in [b] + subdirs(b) + subdirs(up1) + subdirs(up2):
            if has_exe(d):
                return d
            for d2 in subdirs(d):
                if has_exe(d2):
                    return d2
        return None


    def api_speak_node(self, node_id):
        """消息旁喇叭按钮：按 node_id 朗读该条 AI 消息（合成缓存于 tts_cache，重复点击不重合成）。
        取 [ja] 日配句优先，无则用正文；走 UTAU/HANASU 双引擎。"""
        try:
            node = self.core.tree.nodes.get(node_id)
            if not node:
                return {"ok": False, "err": "节点不存在"}
            if node.role != "assistant":
                return {"ok": False, "err": "仅 AI 消息可朗读"}
            p = None
            try:
                if self.plugin_manager:
                    p = self.plugin_manager.get_plugin("UTAU 语音")
            except Exception:
                p = None
            if not p or not getattr(p, "enabled", False):
                return {"ok": False, "err": "未启用语音插件（设置 → 插件 → UTAU 语音）"}
            if not hasattr(p, "_speak"):
                return {"ok": False, "err": "语音插件缺少合成接口"}
            # 优先 [ja] 日配句
            text = ""
            try:
                ja = (node.metadata or {}).get("ja")
                if isinstance(ja, str) and ja.strip():
                    text = ja.strip()
            except Exception:
                pass
            if not text:
                text = str(node.content or "").strip()
            if not text:
                return {"ok": False, "err": "无内容可朗读"}
            # 合成缓存：按 node_id 复用
            base = getattr(app_paths, "get_base_dir", lambda: BASE_DIR)()
            cache = os.path.join(base, "tts_cache")
            os.makedirs(cache, exist_ok=True)
            cached = os.path.join(cache, "node_" + str(node_id) + ".wav")
            if os.path.exists(cached):
                p._play(cached)
                return {"ok": True, "cached": True}
            # 合成前预处理：中文 → 日文（走日文补丁翻译，日文声库才能念）
            final_text = text[:200]
            if hasattr(p, "_prepare_text"):
                final_text, _tr = p._prepare_text(final_text, cache)
            out, _eng = p._engine().synthesize(final_text, cache, pitch_mode="auto") if hasattr(p, "_engine") else (None, None)
            if out and os.path.exists(out):
                try:
                    import shutil
                    shutil.copyfile(out, cached)
                except Exception:
                    pass
                p._play(out)
                return {"ok": True}
            # 兼容旧插件（无 _engine 的 _speak 直接播放）
            res = p._speak(text[:200])
            if isinstance(res, str) and res.startswith("⚠️"):
                return {"ok": False, "err": res}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}


    def api_gen_image(self, prompt, preset="anime", size="1024x1024", negative_prompt="",
                      extra="", seed=None):
        """生图：预设风格 + 提示词 → 图片（base64/url）。配置走设置里的生图 Key/端点/后端。

        seed 留空 = 后端随机；填了就固定（配合「🎲 重抽」可以一直换到满意为止）。
        上一次的输入会记进 config.image_gen_last，下次打开面板自动回填 ——
        调提示词是个反复试的过程，不该每次都重新敲一遍。
        """
        import image_gen
        c = self._image_gen_cfg()
        # 要不要 key 交给引擎按【后端】判断：三种本地/免费后端允许留空，
        # 别在 UI 层写死 —— 写死了就没法用免费生图。
        if not c["key"] and image_gen.needs_key(c["base_url"], c["backend"]):
            return {"ok": False, "err": "未配置生图 API Key（设置 → 生图；"
                                        "或把端点换成免费的 Pollinations / 本地 SD）"}
        presets = image_gen.load_presets(self.base_dir)
        # 只有「空」才算随机；seed=0 是合法种子，别当成没填
        if seed is None or (isinstance(seed, str) and not seed.strip()):
            seed = None
        try:
            seed = int(seed) if seed is not None else None
        except Exception:
            seed = None
        ok, data, msg = image_gen.generate(
            prompt, preset=preset, size=size, api_key=c["key"], base_url=c["base_url"],
            model=c["model"], negative_prompt=negative_prompt, extra=extra,
            seed=seed, presets=presets, backend=c["backend"])
        if not ok:
            return {"ok": False, "err": msg}
        # 记住这次的输入（调提示词要反复试，别让人每次重敲）
        try:
            self.config["image_gen_last"] = {
                "prompt": prompt, "preset": preset, "size": size,
                "negative_prompt": negative_prompt, "extra": extra,
                "seed": data.get("seed") if data.get("seed") is not None else seed,
            }
            self._save_config()
        except Exception:
            pass
        # 生图结果进聊天（sys_msgs 带 image 字段，_rebuild_messages 会展示）
        try:
            if data.get("b64"):
                # 用引擎回报的真实类型：免 Key 后端（Pollinations）回的是 JPEG，
                # 一律写成 image/png 属于谎报类型（浏览器通常能猜对，但别指望）
                mime = data.get("mime") or "image/png"
                data_url = "data:" + mime + ";base64," + data["b64"]
            elif data.get("url"):
                data_url = data["url"]
            else:
                return {"ok": False, "err": "生图无结果"}
            self.sys_msgs.append({"kind": "ai", "speaker": "🎨 生图",
                                  "content": "[" + preset + "] " + prompt,
                                  "image": data_url, "node_id": None})
            self._rebuild_messages()
            return {"ok": True, "image": data_url, "preset": preset,
                    "seed": data.get("seed"), "note": "" if msg == "ok" else msg,
                    "backend": image_gen.resolve_backend(c["base_url"], c["backend"])}
        except Exception as e:
            return {"ok": False, "err": "生图结果处理失败：" + str(e)[:100]}


    def api_gen_presets(self):
        """生图预设列表（内置 + 用户自定义 image_presets.json）"""
        import image_gen
        return {"ok": True, "presets": image_gen.list_presets(
            image_gen.load_presets(self.base_dir))}


    def api_save_image_presets_file(self, text):
        """保存用户预设文件（传 '{}' 即恢复内置默认）。"""
        import json as _json
        import image_gen
        try:
            obj = _json.loads(text or "{}")
        except Exception as e:
            return {"ok": False, "err": "JSON 格式有误：" + str(e)[:120]}
        ok, msg = image_gen.save_presets(self.base_dir, obj)
        if not ok:
            return {"ok": False, "err": msg}
        return {"ok": True, "msg": msg, "presets": image_gen.list_presets(
            image_gen.load_presets(self.base_dir))}

    # ---------- 插件要界面：走 host_ui 这条唯一通道（别让插件自己拉 GUI 库） ----------

    def api_save_key(self, key, base_url, model, provider_id=None):
        pid = (provider_id or self.provider_id or "deepseek").strip()
        self.provider_id = pid
        k = (key or "").strip()
        self.api_keys[pid] = k
        self.config["api_keys"] = self.api_keys
        self.config["provider"] = pid
        self.config["api_key"] = k  # 兼容旧字段
        self.config["base_url"] = (base_url or "").strip()
        self.config["model"] = (model or "").strip()
        # 无条件重建客户端：切换厂商时不能沿用旧厂商的 Key 与 URL
        # 免费厂商（OVH 免费链/Ollama）无 Key：用占位符构造客户端（其服务端忽略认证头）
        self.core.set_api_key(k if k else "free")
        if self.config["base_url"]:
            self.core.set_base_url(self.config["base_url"])
        if self.config["model"]:
            self.core.set_model(self.config["model"])
        # 重建客户端会丢失代理，重新应用
        if self.config.get("proxy"):
            self.core.set_proxy(self.config["proxy"])
        # 换厂商后停止序列按新模型家族默认生效
        self.core.set_stop_sequences(self._effective_stop())
        # 免费厂商默认走中转绕墙：免费链（OVH/本地）常被墙或不稳，直连大概率失败。
        # 若配了中转地址，直接 relay_on，免费模型全程走中转，避免"第一次直连失败"的停顿。
        prov = next((p for p in PROVIDERS if p["id"] == pid), None)
        if prov and prov.get("free"):
            self.core.relay_on = bool(self.core.relay_base or self.config.get("relay_url") or BUILTIN_RELAY)
            self.core.client = self.core._build_client()
        else:
            self.core.relay_on = False
        self._save_config()
        # 进度同步：把模型连接配置推到工坊服务器（后台线程，不阻塞）
        self._ws_push_api()
        return {"ok": True, "provider": pid}

    # ---- 向导第③步：测试并保存（2026-11 新增） ----

    def api_test_and_save_key(self, key, base_url, model, provider_id=None):
        """向导第③步「测试并保存」：**先真连一次，通了才落盘**。

        判据（宁严不松）：
          ① GET {base}/models 返回 2xx → 通；
          ② 该端点 404/405（少数 OpenAI 兼容实现不实现 /models）→ 用一条 1 token 的最小对话兜底；
          ③ 其它状态码 → 不保存，回 `err`（人话）+ `hint`（下一步怎么做）。
        免 Key 厂商（OVH 免费链 / Ollama 本地）没有 Key 可验，直接落到保存。
        """
        import requests
        pid = (provider_id or self.provider_id or "deepseek").strip()
        prov = next((p for p in PROVIDERS if p["id"] == pid), None)
        k = (key or "").strip()
        base = (base_url or (prov or {}).get("base_url") or "").strip().rstrip("/")
        models = (prov or {}).get("models") or []
        m = (model or "").strip() or (models[0] if models else "")
        free = bool(prov and prov.get("free"))
        if not base:
            return {"ok": False, "err": "Base URL 是空的",
                    "hint": "回第①步选一个服务商，Base URL 会跟着填好"}
        if not k and not free:
            return {"ok": False, "err": "还没有填 Key",
                    "hint": "回第②步粘一枚 Key；不想填就点「稍后再说」用免费链"}

        def _save():
            self.api_save_key(k, base, m, pid)
            return {"ok": True, "provider": pid, "model": m, "base_url": base}

        if free:
            return _save()
        proxy = self.config.get("proxy") or None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        headers = {"Authorization": "Bearer " + k}
        try:
            r = requests.get(base + "/models", headers=headers, proxies=proxies, timeout=12)
            if r.status_code in (200, 201):
                return _save()
            if r.status_code in (404, 405):
                body = {"model": m, "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 1, "stream": False}
                h2 = dict(headers)
                h2["Content-Type"] = "application/json"
                r2 = requests.post(base + "/chat/completions", headers=h2, json=body,
                                   proxies=proxies, timeout=25)
                if r2.status_code in (200, 201):
                    return _save()
                return {"ok": False, "err": self._probe_reason(r2.status_code, r2.text),
                        "hint": self._probe_hint(r2.status_code)}
            return {"ok": False, "err": self._probe_reason(r.status_code, r.text),
                    "hint": self._probe_hint(r.status_code)}
        except Exception as e:
            return {"ok": False, "err": "%s: %s" % (type(e).__name__, e),
                    "hint": "网络层失败：多半是超时或被墙，填个代理再试；也可以先点「稍后再说」用免费链"}


    def api_save_image_gen(self, key, base_url, model, backend="auto"):
        """保存生图配置（key/端点/模型/后端），存 config.json"""
        import image_gen
        self.config["image_gen_key"] = (key or "").strip()
        self.config["image_gen_base_url"] = (base_url or "https://api.siliconflow.cn/v1").strip()
        self.config["image_gen_model"] = (model or "black-forest-labs/FLUX.1-schnell").strip()
        b = (backend or "auto").strip().lower()
        self.config["image_gen_backend"] = b if b in image_gen.BACKENDS else "auto"
        self._save_config()
        return {"ok": True, "backend": image_gen.resolve_backend(
            self.config["image_gen_base_url"], self.config["image_gen_backend"]),
            "needs_key": image_gen.needs_key(self.config["image_gen_base_url"],
                                             self.config["image_gen_backend"])}


    def api_open_url(self, url):
        """在系统浏览器打开模型商官网（注册/充值跳转）"""
        url = (url or "").strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return {"ok": False, "err": "invalid url"}
        try:
            import webbrowser
            webbrowser.open(url)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)}

