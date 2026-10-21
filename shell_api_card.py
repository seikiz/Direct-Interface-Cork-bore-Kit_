# -*- coding: utf-8 -*-
"""shell_api_card —— 从 Kit.py 拆出的 mixin（^api_card|^api_create_|^api_update_|^api_delete_|^api_import_card|^api_export_card|^api_ai_draft|^api_trpg|^api_clear_chat）。

包含方法：api_create_role、api_update_role、api_create_world、api_update_world、api_delete_world、api_ai_draft、api_delete_role、api_card_saves、api_card_save_new、api_card_save、api_card_save_load、api_card_save_delete…

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。
"""
from __future__ import annotations

import json
import os
import save_guard
import uuid
from shell_util import assemble_role_prompt

class ApiCardMixin:
    """shell_api_card"""

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
                    # 覆盖前先留底：清空机制/结局等"破坏<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌性编辑"也能从 backup/ 恢复回
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

