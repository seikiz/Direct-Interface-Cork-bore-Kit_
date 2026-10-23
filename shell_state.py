# -*- coding: utf-8 -*-
"""StateMixin —— 从 Direct-Interface Cork-bore Kit.py 的 HtmlApp 拆出（ast 精确切分）。

方法：_detect_ollama、_append_sys、_chain_nodes、_rebuild_messages、_save_tree、_build_system_prompt、_expand_macros、_handle_travel、_activate_core、_start_opening、_card_snapshot、_wallpaper_data_url、_l2d_state、_trpg_state、_offline_plan、_maybe_auto_turn、_run_auto_turn
"""
from __future__ import annotations

import json
import os
import random
import re
import save_guard
import threading

class StateMixin:
    def _detect_ollama(self):
        """后台探测本地 Ollama（localhost / 127.0.0.1），结果进 api_state"""
        try:
            import requests
            for url in ("http://localhost:11434/v1/models",
                        "http://127.0.0.1:11434/v1/models"):
                try:
                    r = requests.get(url, timeout=3)
                    if r.status_code < 500:
                        self.ollama_online = True
                        print("[Ollama] ✅ 本地 Ollama 已检测到")
                        return
                except Exception:
                    continue
        except Exception:
            pass
        self.ollama_online = False
        print("[Ollama] 未检测到本地服务（需要时先安装并启动 Ollama）")

    def _append_sys(self, content, kind="sys", speaker="系统"):
        """树外横幅（系统提示/命令回显），随重建一直显示"""
        with self._lock:
            self.sys_msgs.append({"kind": kind, "speaker": speaker, "content": content})
            if len(self.sys_msgs) > 200:
                self.sys_msgs = self.sys_msgs[-200:]
        self._rebuild_messages()

    def _chain_nodes(self):
        """从 core 树里取当前链（跳过 system 节点），返回 MessageNode 列表（root→leaf）"""
        tree = self.core.tree
        leaf = tree.current_leaf_id
        if not leaf or leaf not in tree.nodes:
            return []
        chain = []
        node = tree.nodes.get(leaf)
        while node is not None:
            chain.append(node)
            if node.parent_id and node.parent_id in tree.nodes:
                node = tree.nodes.get(node.parent_id)
            else:
                break
        chain.reverse()
        return [n for n in chain if n.role != "system"]

    def _rebuild_messages(self):
        """按 当前聊天树链 + 系统横幅 重建展示消息列表（epoch +1 通知前端整刷）。
        消息 seq 按 (类型,键) 缓存：重建不重排，前端旧 seq 依然有效。"""
        with self._lock:
            def nxt(key):
                if key in self.node_seq_cache:
                    return self.node_seq_cache[key]
                self.seq += 1
                self.node_seq_cache[key] = self.seq
                return self.seq

            msgs = []
            for i, s in enumerate(self.sys_msgs):
                if isinstance(s, str):
                    s = {"kind": "sys", "speaker": "系统", "content": s}
                msgs.append({"seq": nxt(("sys", i)), "kind": s.get("kind", "sys"),
                             "speaker": s.get("speaker", "系统"),
                             "content": s.get("content", ""), "image": s.get("image"), "node_id": None})
            for n in self._chain_nodes():
                seq = nxt(("node", n.id))
                meta = n.metadata or {}
                kind = "user" if n.role == "user" else "ai"
                speaker = meta.get("speaker")
                if kind == "user":
                    # 用户消息显示玩家卡名字（与头像<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌文件名一致），无名字时显示「你」
                    speaker = (self.persona or {}).get("name") or "你"
                elif not speaker:
                    # 单角色：AI 消息显示当前激活角色名；群聊/无角色时显示 AI
                    speaker = self.selected_roles[0] if len(self.selected_roles) == 1 else "AI"
                msgs.append({"seq": seq, "kind": kind, "speaker": speaker,
                             "content": n.content, "image": self.node_images.get(n.id),
                             "node_id": n.id})
            # 滑条信息：AI 消息的父用户节点有多个 assistant 子节点时给箭头
            for i, m in enumerate(msgs):
                if m["kind"] != "ai" or not m["node_id"]:
                    continue
                node = self.core.tree.nodes.get(m["node_id"])
                if node and node.parent_id and node.parent_id in self.core.tree.nodes:
                    sibs = [cid for cid in self.core.tree.nodes[node.parent_id].children_ids
                            if self.core.tree.nodes.get(cid) and self.core.tree.nodes[cid].role == "assistant"]
                    if len(sibs) > 1:
                        m["swipes"] = {"total": len(sibs), "index": sibs.index(m["node_id"])}
            self.messages = msgs
            self.render_epoch += 1

    def _save_tree(self, wait=True):
        """把当前聊天树写回第一个选中角色的文件（保留 name/system_prompt/card_data）

        wait=False：自动落盘走 io 线（见下），界面不必等磁盘。
        """
        if not self.selected_roles:
            return
        # 跑团会期锁定：被锁卡不可被当前会话清写/推送记忆树（防导入存档与跑团混淆）
        if self.selected_roles[0] in self._trpg_locked_names():
            return
        tree_data = self.core.get_all_nodes_data()
        # 空树（只有系统节点）不覆盖已有历史，防止切换/误操作清档
        if len(tree_data.get("nodes", {})) <= 1:
            return
        for r in self.roles:
            if r["name"] == self.selected_roles[0]:
                data = dict(r.get("data") or {})
                data["name"] = r["name"]
                data["system_prompt"] = r["prompt"]
                data["kind"] = "dick_card"
                data["history_tree"] = self.core.get_all_nodes_data()
                # 机制状态显式持久化到角色卡（修复"清空/重选回落 initial"：
                # 不依赖树的临时 ms 快照，保存当前状态供还原）
                try:
                    data["mechanics_state"] = self.core.mechanism_snapshot()
                except Exception:
                    pass
                # 进度同步时间戳（UTC ISO，跨设备按该串比较新旧）
                try:
                    from datetime import datetime, timezone
                    data["_tree_ts"] = datetime.now(timezone.utc).isoformat()
                except Exception:
                    pass
                try:
                    # 存档守护：覆盖前留底 + 原子写入（写一半崩溃也不会截断存档）
                    # 自动落盘（wait=False）走 io 线：整棵树可能几百 KB，写盘不该挡着界面刷新；
                    # 显式保存/备份/退出仍走同步（wait=True）—— 那几处必须确保真的落盘了。
                    _path = os.path.join(self.save_dir, r["file"])
                    if wait:
                        save_guard.backup_file(_path)
                        save_guard.atomic_write_json(_path, data)
                    else:
                        import jobs as _jobs
                        _jobs.submit("io", save_guard.atomic_write_json, _path, data,
                                     name="自动落盘：" + str(r["name"]),
                                     on_done=lambda _r, _e: None)
                except Exception:
                    pass
                # 同步内存快照：勾选/取消勾选切换时 _activate_core 从
                # r["data"]["history_tree"] 取记录，不同步会导致同一会话内
                # 重新勾选只恢复到旧快照（新建角色的记录甚至取不回）
                r["data"] = data
                # 进度同步：把聊天树推送到工坊服务器（后台线程，不阻塞保存）
                self._ws_save_upload_async(r["name"], data["history_tree"])
                break

    def _build_system_prompt(self):
        sb = []
        preset = None
        for p in self.presets:
            if p.get("name") == self.preset_name:
                preset = p
                break
        if preset and preset.get("system_prefix"):
            sb.append(preset["system_prefix"])
        chosen = [r for r in self.roles if r["name"] in self.selected_roles]
        for r in chosen:
            sb.append(r["prompt"])
        if len(chosen) > 1:
            sb.append("当前是群聊，参与角色：" + "、".join(r["name"] for r in chosen) +
                      "。每次由一位角色发言，用 [角色名]: 开头标注。用户 @角色名 表示指定该角色回复。")
        ws = [w for w in self.worlds if w.get("name") in self.selected_worlds]
        if ws:
            sb.append("【世界设定】")
            for w in ws:
                sb.append(str(w.get("name")) + "：" + str(w.get("description", "")))
        if self.persona:
            sb.append("【玩家角色卡】" + json.dumps(self.persona, ensure_ascii=False))
        if preset and preset.get("rules"):
            sb.append(preset["rules"])
        injection = self.plugin_manager.contextInjection() if hasattr(self.plugin_manager, "contextInjection") else ""
        if injection:
            sb.append(injection)
        if preset and preset.get("system_suffix"):
            sb.append(preset["system_suffix"])
        # 本轮角色锚点（最靠后，最贴合模型“最近注意力”）
        anchor = self._anchor_block()
        if anchor:
            sb.append(anchor)
        return "\n\n".join(x for x in sb if x and str(x).strip())

    def _expand_macros(self, text):
        """Quick Reply 宏展开（酒馆 {{player}}/{{char}} 的对等物）：
        {player} 玩家卡名 · {char} 当前角色 · {world} 当前世界 · {random:a|b|c} 随机取一
        未知宏原样保留。"""
        if not text or "{" not in text:
            return text
        import random as _r
        player = (self.persona or {}).get("name") or "你"
        char = self.selected_roles[0] if self.selected_roles else "AI"
        world = self.current_world or ""

        def rep(m):
            key = m.group(1).strip()
            if key == "player":
                return player
            if key == "char":
                return char
            if key == "world":
                return world
            if key.startswith("random:"):
                opts = [x for x in key[len("random:"):].split("|") if x]
                return _r.choice(opts) if opts else ""
            return m.group(0)

        import re as _re
        return _re.sub(r"\{([^{}]+)\}", rep, text)

    def _handle_travel(self, text):
        """/穿越 [世界名]：列出可穿越世界或直接穿越；返回提示文本或 None（不是穿越命令）"""
        parts = text.split(None, 1)
        if (parts[0] if parts else "").strip().lower() not in ("/穿越", "/travel"):
            return None
        target = parts[1].strip() if len(parts) > 1 else ""
        if not self.selected_worlds:
            return "⚠️ 还没有勾选世界卡（左侧世界列表勾选后即可穿梭）"
        if not target:
            lines = ["🌍 可穿越的世界："]
            for i, n in enumerate(self.selected_worlds, 1):
                mark = " ★当前所在" if n == self.current_world else ""
                lines.append(str(i) + ". " + n + mark)
            lines.append("用法：/穿越 世界名")
            return chr(10).join(lines)
        hit = next((n for n in self.selected_worlds if n == target or target in n), None)
        if not hit:
            return "⚠️ 没有找到世界「" + target + "」，可用 /穿越 查看列表"
        self.api_travel(hit)
        return "🚀 已穿越到「" + hit + "」"

    # ---------- 管理动作 ----------
    def _activate_core(self, reload_tree=True):
        """把选中角色/世界/预设/玩家卡接入 core（重建系统节点 + 首个角色的历史树）"""
        roles_data = []
        for i, name in enumerate(self.selected_roles):
            for r in self.roles:
                if r["name"] == name:
                    rd = {"name": r["name"], "system_prompt": r["prompt"],
                          "unlocked": r.get("unlocked", False),
                          "advanced": (r.get("data") or {}).get("advanced")}
                    if i == 0 and reload_tree and r.get("data") and r["data"].get("history_tree"):
                        rd["history_tree"] = r["data"]["history_tree"]
                    # 角色卡显式持久化的机制状态：传入 core 以便清空/重选时正确还原
                    if i == 0 and r.get("data"):
                        ms0 = (r["data"] or {}).get("mechanics_state")
                        if isinstance(ms0, dict):
                            rd["mechanics_state"] = ms0
                    roles_data.append(rd)
        self.core.set_active_roles(roles_data)
        self.core.set_worlds(self._worlds_for_core())
        self.core.set_player_persona(self.persona)
        preset = None
        for p in self.presets:
            if p.get("name") == self.preset_name:
                preset = p
                break
        self.core.set_prompt_preset(preset if preset and preset.get("name") else None)
        # 切换角色 = 新会话：旧剧情选项作废
        self._clear_choices()
        self.core.pending_event = None
        # 前瞻投机器的开关状态要跟着走：关键词是按角色存的，
        # 换了角色可能就从"有目标"变成"没目标"，这时必须摘掉投机器。
        self._sync_speculator()
        self._start_opening()
        self._rebuild_messages()

    def _start_opening(self):
        """新会话开场：把角色卡的开场白当【场景】交给模型，由它现场演出第一幕。

        为什么不是直接把开场白贴出来：
            贴出来的是作者写死的文字，和当前选中的世界卡/玩家卡/好感度无关，
            读起来像一段设定文档，而不是「她在对你说话」。
            交给模型演，开场才会对上当前配置，用户才有沉浸感。
        发不出去时（没配 Key / 没有开场白 / 正在忙）退回直接显示原文，
        免得界面一片空白 —— 有开场白总比空着强。
        """
        try:
            if len(self.selected_roles) != 1:
                return 0                     # 群聊不做开场，避免多个角色抢话
            tree = self.core.tree
            # 已有历史（续聊/存档）就不再演，否则每次切回来都重演一遍
            for n in tree.nodes.values():
                if n.role in ("user", "assistant"):
                    return 0
            name = self.selected_roles[0]
            role = next((r for r in self.roles if r["name"] == name), None)
            if not role:
                return 0
            data = role.get("data") or {}
            fields = role.get("fields") or {}
            mes = str(data.get("first_mes") or fields.get("first_mes") or "").strip()
            if not mes:
                return 0

            # 首选：让模型把这段场景演出来
            fired = False
            try:
                self.busy = True
                self.streaming = ""
                self.opening_loading = True      # 让界面在模型吐字之前就有加载提示
                fired = self.core.generate_opening(
                    mes,
                    on_stream=lambda full: setattr(
                        self, "streaming",
                        self.core.strip_mechanism_tags(full, apply=False)),
                    on_response=self._on_response,
                    on_error=self._on_error, on_busy=self._on_busy)
            except Exception:
                fired = False
                self.opening_loading = False
            if fired:
                self._rebuild_messages()
                return 1

            # 退路：发不出去就直接把开场白原文显示出来
            self.busy = False
            self.opening_loading = False
            nid = self.core.add_assistant_message(
                mes, parent_id=tree.current_leaf_id,
                metadata={"speaker": role.get("name"), "usage": None, "greeting": True})
            tree.current_leaf_id = nid
            tree.fix_leaf()
            return 1
        except Exception:
            return 0                          # 开场失败不该阻断开聊

    def _card_snapshot(self):
        """构造一份当前会话的存档快照（对话树 + 机制状态 + 进度元数据）"""
        from datetime import datetime, timezone
        tree = self.core.get_all_nodes_data()
        mech = None
        try:
            mech = self.core.mechanism_snapshot()
        except Exception:
            mech = None
        n_nodes = 0
        if isinstance(tree, dict):
            nodes = tree.get("nodes") or {}
            n_nodes = sum(1 for n in nodes.values()
                          if isinstance(n, dict) and (n.get("role") or "") != "system")
        return {
            "history_tree": tree,
            "mechanism_state": mech,
            "_tree_ts": datetime.now(timezone.utc).isoformat(),
            "progress": n_nodes,  # 正式聊天条数（不含系统节点）
        }

    def _wallpaper_data_url(self):
        p = self._wallpaper_path()
        if not os.path.isfile(p):
            return None
        try:
            with open(p, "rb") as f:
                raw = f.read()
        except Exception:
            return None
        import base64 as _b64
        ext = os.path.splitext(p)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp"}.get(ext, "image/png")
        return "data:" + mime + ";base64," + _b64.b64encode(raw).decode("ascii")

    def _l2d_state(self):
        """Live2D 已并入核心：恒启用；设置从插件读取，无则用默认。"""
        try:
            p = self.plugin_manager.get_plugin("Live2D 看板娘")
            if p is not None:
                s = dict(getattr(p, "settings", {}) or {})
                models = []
                for item in getattr(p, "settings_schema", None) or []:
                    if item.get("key") == "model":
                        models = item.get("options") or []
                return {
                    "enabled": True,
                    "model": s.get("model", ""),
                    "scale": s.get("scale", 100),
                    "pos": s.get("pos", "右下"),
                    "opacity": s.get("opacity", 95),
                    "draggable": s.get("draggable", True),
                    "breath": s.get("breath", True),
                    "models": models,
                }
        except Exception:
            pass
        return {"enabled": True, "model": "", "scale": 100, "pos": "右下",
                "opacity": 95, "draggable": True, "breath": True, "models": []}

    def _trpg_state(self):
        """跑团会话态（供前端渲染跑团提示条）。active 期间显示；否则若仍有锁定则提示可解除。"""
        try:
            p = self.plugin_manager.get_plugin("跑团模式")
            if p is not None:
                return {
                    "active": bool(getattr(p, "active", False)),
                    "gm": getattr(p, "gm", "") or "",
                    "pcs": list(getattr(p, "pcs", []) or []),
                    "turn": getattr(p, "turn", "") or "",
                    "round": getattr(p, "round", 0) or 0,
                    "locked": sorted(self._trpg_locked_names()),
                }
        except Exception:
            pass
        return {"active": False, "gm": "", "pcs": [], "turn": "", "round": 0,
                "locked": sorted(self._trpg_locked_names())}

    def _offline_plan(self):
        """算一份离线推进方案（不修改任何状态）"""
        import offline_advance
        import time_scale
        try:
            tree = self.core.get_all_nodes_data()
        except Exception:
            tree = None
        try:
            scale = float(time_scale.load())
        except Exception:
            scale = 1.0
        mech_cfg = getattr(self.core, "_mech_config", None)
        try:
            mech_state = self.core.mechanism_snapshot()
        except Exception:
            mech_state = None
        dismissed = (self.config.get("offline_dismissed") or {}).get(self._offline_key())
        try:
            return offline_advance.plan(tree, mech_cfg, mech_state, scale=scale,
                                        dismissed_ts=dismissed)
        except Exception as e:
            return {"ok": False, "skipped": "离线推进计算失败：" + str(e)[:120]}

    def _maybe_auto_turn(self, rounds):
        """群聊自动接话：当前回复后由其他角色接力发言（最多 rounds 轮）。
        选角策略 = 公平轮换（防饿死） + 内容相关性 + 小概率意外，并尊重 @角色名 显式指定。
        目标：让每个角色都被轮到、且人设切换发生在"该他说话的时候"，像真人群聊。"""
        if rounds <= 0 or not self.auto_turn or len(self.selected_roles) < 2 or self.busy:
            return
        roster = [r["name"] for r in self.roles if r["name"] in self.selected_roles]
        if not roster:
            return
        last = getattr(self.core, "last_speaker", None)

        # --- 0) 显式指定优先：最后一句用户文本若含 @角色名，直接让他接话 ---
        last_user = str(getattr(self, "_last_user", "") or "")
        explicit = None
        for nm in roster:
            if nm and ("@" + nm) in last_user:
                explicit = nm
                break
        if explicit:
            self._run_auto_turn(explicit, rounds)
            return

        candidates = [n for n in roster if n != last] or roster[:]

        # --- 1) 公平权重：越久没发言，权重越高（用最近链上各角色的发言次数） ---
        speak = {nm: 0 for nm in roster}
        try:
            for m in self.core.tree.get_current_chain():
                sp = (m.get("metadata") or {}).get("speaker")
                if sp in speak:
                    speak[sp] += 1
        except Exception:
            pass
        # 最近几轮里每被点到一次就记一笔；没点到的候选记 0 → 权重更大。
        # 反向：发言少的候选更可能被挑中，避免双人死循环/饿死第三人。

        # --- 2) 相关性：谁跟最后一句话题有关谁更可能接话（CJK 用字符 n-gram，无需分词） ---
        def _ngrams(s, n):
            s = re.sub(r"\s+", "", str(s))
            return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}
        def relevance(name):
            r = next((x for x in self.roles if x["name"] == name), None)
            if not r:
                return 0.0
            f = r.get("fields") or {}
            grain = " ".join(str(f.get(k) or "") for k in
                             ("personality", "speech", "background", "appearance", "notes"))
            # 用 2~4 字 shingles 取"人设主题"与"最后一句"的重叠，表征"这人跟话题有关"
            profile = _ngrams(grain, 2) | _ngrams(grain, 3) | _ngrams(grain, 4)
            msg = _ngrams(last_user, 2) | _ngrams(last_user, 3)
            overlap = msg & profile
            # 只计真正"有信息量的" shingle（含标点/常见字的噪声剔除）
            info = [g for g in overlap if any('\u4e00' <= c <= '\u9fff' for c in g)
                    and not re.search(r"[\s，。！？、的了是在我你他她这那]", g)]
            return min(len(info), 4) / 4.0

        # 从未满 rounds 的权重里加权：公平权重 = 1/(1+发言次数)；相关性加成；意外项减免。
        scorer = []
        for nm in candidates:
            fair = 1.0 / (1.0 + speak.get(nm, 0))
            rel = relevance(nm)
            score = 2.0 * fair + 1.6 * rel
            scorer.append((score, nm))
        scorer.sort(key=lambda pair: -pair[0])
        # 加权随机：按分数占比挑选（分数越高越可能，但也给低分机会）→ 更像真人
        total = sum(p[0] for p in scorer) or 1.0
        r = random.random() * total
        acc = 0.0
        chosen = scorer[0][1]
        for sc, nm in scorer:
            acc += sc
            if r <= acc:
                chosen = nm
                break

        # --- 3) 小概率意外：真人会冷场/抢话/临时改主意（尊重显式指定已排除） ---
        if random.random() < 0.12 and len(candidates) > 1:
            chosen = random.choice(candidates)

        self._run_auto_turn(chosen, rounds)

    def _run_auto_turn(self, speaker, rounds):
        """为指定角色启动一次自动接话（保持 busy/streaming 状态，延迟等 fetch 复位）。"""
        if speaker not in [r["name"] for r in self.roles]:
            return
        self.busy = True
        self.streaming = ""

        def go():
            try:
                self.core.send_auto_turn(
                    speaker,
                    on_response=lambda reply, usage: self._auto_turn_done(reply, usage, rounds),
                    on_error=lambda err: self._auto_turn_fail())
            except Exception:
                self._auto_turn_fail()

        # 延迟启动：等上一轮 fetch 的 is_processing 复位，避免被“正在处理中”拦截
        threading.Timer(0.5, go).start()
