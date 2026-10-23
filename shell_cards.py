# -*- coding: utf-8 -*-
"""CardsMixin —— 从 Direct-Interface Cork-bore Kit.py 的 HtmlApp 拆出（ast 精确切分）。

方法：_load_presets、_load_roles、_load_worlds、_roll_option、_worlds_for_core、_sync_worlds、_parse_role_input、_clean_advanced、_judge_endpoint、_speculate、_do_import_card、_do_export_card、_norm_entries、_reload_roles、_reload_worlds、_wire_sprites_to_speakers
"""
from __future__ import annotations

from shell_util import ROLE_FIELDS, WORLD_PARAMS, _parse_fields, _render_world_desc, html_app_clean_battle, html_app_clean_mechanics, role_prompt_from_card
import card_compat
import codex_core
import json
import os
import save_guard

class CardsMixin:
    # ---------- 数<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌据 ----------
    def _load_presets(self):
        self.presets = [{"name": "默认"}]
        try:
            for fn in sorted(os.listdir(self.preset_dir)):
                if fn.endswith(".json"):
                    with open(os.path.join(self.preset_dir, fn), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("name"):
                        self.presets.append(data)
        except Exception:
            pass
        self.preset_name = self.config.get("prompt_preset", "") or ""

    def _load_roles(self):
        self.roles = []
        try:
            for fn in sorted(os.listdir(self.save_dir)):
                if fn.startswith("."):
                    continue  # 跳过跑团会期锁等隐藏/元数据文件
                if not fn.endswith(".json"):
                    continue
                try:
                    path = os.path.join(self.save_dir, fn)
                    data = save_guard.guard_loaded(path, kind="role")
                    if data is None:
                        continue
                    if isinstance(data, dict) and data.get("system_prompt"):
                        prompt, fields, legacy = role_prompt_from_card(
                            data.get("name") or fn[:-5], data)
                        self.roles.append({"name": data.get("name") or fn[:-5],
                                           "file": fn, "prompt": prompt, "data": data,
                                           "fields": fields, "legacy": legacy,
                                           "unlocked": bool(data.get("unlocked", False))})
                except Exception:
                    continue
        except Exception:
            pass
        # 恢复上次选中的角色（与 Android 端一致：启动即恢复，恋爱条/机制卡初始就绪，
        # 无需再手动保存一遍才出现）。config.selected_roles（新版数组）或 last_role（旧版单值）。
        self.selected_roles = []
        try:
            saved = self.config.get("selected_roles") or []
            if not isinstance(saved, list):
                saved = []
            if not saved and self.config.get("last_role"):
                lr = str(self.config.get("last_role") or "").strip()
                if lr:
                    saved = [lr]
            self.selected_roles = [n for n in saved
                                   if any(r["name"] == n for r in self.roles)][:8]
        except Exception:
            self.selected_roles = []

    def _load_worlds(self):
        self.worlds = []
        try:
            for fn in sorted(os.listdir(self.world_dir)):
                if not fn.endswith(".json"):
                    continue
                try:
                    data = save_guard.guard_loaded(os.path.join(self.world_dir, fn), kind="world")
                    if isinstance(data, dict) and data.get("name"):
                        self.worlds.append(data)
                except Exception:
                    continue
        except Exception:
            pass
        self.selected_worlds = []

    def _roll_option(self, item):
        """点选项时按配置概率表 ROLL（百分比可配：机制卡 mechanics.roll，默认
        暴击10/稀有4/大失败2/天选0.1(千分之一)/坍缩0.001(十万分之一)；概率不公布）。
        返回 (effect, kind, note)"""
        import random as _r
        cfg = getattr(self.core, "_mech_config", None) or {}
        roll = cfg.get("roll") if isinstance(cfg, dict) else None
        if not isinstance(roll, dict):
            roll = {}
        def _p(key, dflt):
            try:
                return float(roll.get(key, dflt))
            except (TypeError, ValueError):
                return dflt
        # 天选 = 千分之一（兼容旧键 legend：旧卡没配 chosen 时沿用其传说概率）
        chosen_p = _p("chosen", _p("legend", 0.1))
        collapse_p = _p("collapse", 0.001)
        fail_p = _p("fail", 2)
        rare_p = _p("rare", 4)
        crit_p = _p("crit", 10)
        chosen_p = max(0.0, min(100.0, chosen_p)) / 100.0
        collapse_p = max(0.0, min(100.0, collapse_p)) / 100.0
        fail_p = max(0.0, min(100.0, fail_p)) / 100.0
        rare_p = max(0.0, min(100.0, rare_p)) / 100.0
        crit_p = max(0.0, min(100.0, crit_p)) / 100.0
        table = [
            (collapse_p, "collapse", "🌌 坍缩：十万分之一的奇迹坍缩成现实！"),
            (collapse_p + chosen_p, "chosen", "🌟 天选：千分之一的天命眷顾被触发了！"),
            (collapse_p + chosen_p + fail_p, "fail", "💥 结果出了岔子！"),
            (collapse_p + chosen_p + fail_p + rare_p, "rare", "✨ 命运的眷顾：触发了稀有事件！"),
            (collapse_p + chosen_p + fail_p + rare_p + crit_p, "crit", "✨ 效果暴击！"),
            (1.0, "normal", ""),
        ]
        r = _r.random()
        kind, note = "normal", ""
        for limit, k, n in table:
            if r < limit:
                kind, note = k, n
                break
        effect = {}
        if isinstance(item, dict):
            aff = item.get("aff")
            st = item.get("st")
            if isinstance(st, dict):
                effect["st"] = st
            if aff is not None:
                try:
                    aff = int(aff)
                except (TypeError, ValueError):
                    aff = None
            if aff is not None:
                if kind == "crit":
                    effect["aff"] = aff * 2
                elif kind == "fail":
                    effect["aff"] = -aff
                else:
                    effect["aff"] = aff
            elif kind in ("crit", "fail"):
                # 无机制效果的选项：暴击/失败仅提示，不空转
                note = ""
        return effect, kind, note

    def _worlds_for_core(self):
        """选中世界 → core 数据结构（背景中内嵌世界参数的人类可读渲染）"""
        out = []
        for w in self.worlds:
            if w.get("name") in self.selected_worlds:
                wc = dict(w)
                wc["description"] = _render_world_desc(w)
                out.append(wc)
        return out

    def _sync_worlds(self):
        """把选中世界接入 core；当前世界若不在选中列表则回退到第一个"""
        selected = self._worlds_for_core()
        self.core.set_worlds(selected)
        if self.current_world not in self.selected_worlds:
            self.current_world = self.selected_worlds[0] if self.selected_worlds else ""
        if self.current_world:
            self.core.set_current_world(self.current_world)
        self.config["current_world"] = self.current_world
        self._save_config()

    def _parse_role_input(self, name, fields_json):
        """解析角色卡输入：结构化字段 dict / JSON / 旧版纯文本设定 → (legacy, fields, unlocked, advanced)"""
        legacy = ""
        fields = {k: "" for k, _ in ROLE_FIELDS}
        raw = _parse_fields(fields_json)
        if isinstance(fields_json, str) and not raw and fields_json.strip() and not fields_json.strip().startswith("{"):
            legacy = fields_json.strip()
        else:
            legacy = (raw.get("legacy") or raw.get("system_prompt") or "")
            if isinstance(legacy, list):
                legacy = "、".join(str(x) for x in legacy)
            legacy = str(legacy).strip()
            fields = {}
            for k, _ in ROLE_FIELDS:
                v = raw.get(k) or ""
                if isinstance(v, list):
                    v = "、".join(str(x) for x in v if str(x).strip())
                fields[k] = str(v).strip()
        unlocked = False
        if isinstance(fields_json, dict):
            unlocked = bool(fields_json.get("unlocked", False))
        elif raw:
            unlocked = bool(raw.get("unlocked", False))
        # 高级设置（开发者模式）：game / extra_prompt / dev_notes / card_quick_replies
        advanced = None
        adv_raw = None
        if isinstance(fields_json, dict):
            adv_raw = fields_json.get("advanced")
        elif raw:
            adv_raw = raw.get("advanced")
        if isinstance(adv_raw, dict):
            advanced = adv_raw
        elif isinstance(adv_raw, str) and adv_raw.strip():
            try:
                parsed = json.loads(adv_raw)
                if isinstance(parsed, dict):
                    advanced = parsed
            except Exception:
                advanced = None
        return legacy, fields, unlocked, advanced

    @staticmethod
    def _clean_advanced(advanced):
        """规整高级设置字段（只保留已知键，类型安全）"""
        if not isinstance(advanced, dict):
            return None
        game = advanced.get("game")
        if isinstance(game, dict):
            game = {
                "name": str(game.get("name") or "").strip()[:60],
                "rules": str(game.get("rules") or "").strip(),
                "state": str(game.get("state") or "").strip(),
            }
        adv = {
            "game": game if isinstance(game, dict) and (game["rules"] or game["name"]) else None,
            "extra_prompt": str(advanced.get("extra_prompt") or "").strip(),
            "dev_notes": str(advanced.get("dev_notes") or "").strip(),
            "card_face": codex_core.sanitize_html(str(advanced.get("card_face") or "").strip()),
        }
        mech = advanced.get("mechanics")
        if isinstance(mech, dict):
            cleaned_mech = html_app_clean_mechanics(mech)
            if cleaned_mech:
                adv["mechanics"] = cleaned_mech
        battle = advanced.get("battle")
        if isinstance(battle, dict):
            cleaned_battle = html_app_clean_battle(battle)
            if cleaned_battle:
                adv["battle"] = cleaned_battle
        regex_rules = advanced.get("regex_rules")
        if isinstance(regex_rules, list):
            cleaned_rr = []
            for x in regex_rules:
                if not isinstance(x, dict) or not str(x.get("pattern") or "").strip():
                    continue
                scope = str(x.get("scope") or "both")
                if scope not in ("ai", "user", "both"):
                    scope = "both"
                cleaned_rr.append({
                    "id": str(x.get("id") or "")[:30],
                    "name": str(x.get("name") or x.get("id") or "")[:30],
                    "pattern": str(x.get("pattern") or "").strip(),
                    "replace": str(x.get("replace") or ""),
                    "scope": scope,
                    "enabled": bool(x.get("enabled", True)),
                })
            if cleaned_rr:
                adv["regex_rules"] = cleaned_rr
        qrs = advanced.get("card_quick_replies")
        if isinstance(qrs, list):
            cleaned = []
            for x in qrs:
                if isinstance(x, dict) and x.get("label"):
                    cleaned.append({"label": str(x.get("label")).strip()[:30],
                                    "text": str(x.get("text") or "").strip()})
            adv["card_quick_replies"] = cleaned
        else:
            adv["card_quick_replies"] = []
        if not any(v for k, v in adv.items() if k != "card_quick_replies") and not adv["card_quick_replies"]:
            return None
        return adv

    def _judge_endpoint(self, text):
        """价值判定：给端点回复打 0~1。

        优先用【你自己训出来的排序器】——它的权重是从你的偏好里拟合的，
        比手搓的那套更懂你要什么；没有模型时退回 rubric（模型判定）。
        两者都没有就返回 None，前瞻退回纯启发式。
        """
        # ① 训好的排序器（纯本地，零 API 调用 —— 这也是它比 rubric 便宜的地方）
        if (self.config.get("ranker") or {}).get("on"):
            try:
                import ranker
                m = ranker.load(self._ranker_path())
                if m:
                    chain = self.core.get_current_chain()
                    parent = ""
                    for x in reversed(chain):
                        if x.get("role") == "assistant":
                            parent = str(x.get("content") or "")
                            break
                    s = ranker.score(m.get("w"), text, parent, [], 
                                     self._drift_keys(), self._case_text())
                    if s is not None:
                        return s
            except Exception:
                pass
        # ② 退回 rubric（要一次模型调用）
        crit = self._rubric()
        if not crit:
            return None
        try:
            import rubric as _rb
        except Exception:
            return None
        core = self.core

        def _complete(msgs):
            txt, _u = core._stream_create(list(msgs), None)
            return txt or ""

        r = _rb.judge(_complete, crit, self.core.get_current_chain(), text)
        return r.get("score")

    def _speculate(self, messages):
        """投机器：拿到本轮完整载荷，先往前生成几条路，挑端点最正的交给用户。

        返回 None 表示不干预（走原来的单路生成）。
        跑在 _fetch_response 的工作线程里，不阻塞界面。
        """
        cfg = self.config.get("lookahead") or {}
        if not cfg.get("on"):
            return None
        keys = self._drift_keys()
        if not keys:
            return None                      # 没目标就不前瞻（否则等于瞎挑）
        try:
            import lookahead
        except Exception:
            return None
        core = self.core

        def _complete(msgs):
            txt, _usage = core._stream_create(list(msgs), None)
            return txt or ""

        try:
            res = lookahead.expand(
                _complete, list(messages),
                branches=int(cfg.get("branches") or lookahead.DEF_BRANCHES),
                depth=int(cfg.get("depth") or lookahead.DEF_DEPTH),
                keys=keys, case_text=self._case_text(),
                cap=int(cfg.get("cap") or lookahead.COST_CAP),
                judge_fn=self._judge_endpoint
                if (self._rubric() or (self.config.get("ranker") or {}).get("on"))
                else None)
        except Exception as e:
            self._append_sys("⚠️ 前瞻展开异常，已按原路继续：" + str(e)[:120], kind="warn")
            return None
        if not res.get("ok"):
            return None
        try:
            self._append_sys("🧭 " + lookahead.describe(res).replace("\n", "；"))
        except Exception:
            pass
        return res.get("first")

    def _do_import_card(self, path):
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as e:
            return {"ok": False, "err": "读取失败：" + str(e)}
        low = path.lower()
        if low.endswith(".png") or low.endswith(".webp"):
            data = card_compat.png_extract_card(raw)
            if data is None:
                return {"ok": False, "err": "这张图片里没有找到角色卡（chara/ccv3 块）"}
        else:
            try:
                data = json.loads(raw.decode("utf-8-sig"))
            except Exception as e:
                return {"ok": False, "err": "JSON 解析失败：" + str(e)}
        # 类型校验：拒绝把「聊天树快照」当角色卡导入（{kind:dick_tree} 或 裸 {ts,tree}）。
        # 这是"导入存档 vs 跑团"最容易串的槽位：快照里没有 system_prompt/name，绝不是角色卡。
        if isinstance(data, dict):
            _tree_like = (data.get("kind") == "dick_tree") or (
                isinstance(data.get("tree"), dict) and not data.get("system_prompt") and not data.get("name"))
            if _tree_like:
                return {"ok": False, "err": "这是聊天树快照，不是角色卡（请导入角色卡 .json/.png/.webp）"}
        conv = card_compat.to_dick(data)
        if not conv:
            return {"ok": False, "err": "无法识别的角色卡格式（需要 v1/v2/v3 或 DICK 格式）"}
        name = conv["name"]
        base_name = name
        i = 2
        while any(r["name"] == name for r in self.roles):
            name = base_name + "_" + str(i)
            i += 1
        fn = self._safe_name(name) + ".json"
        saved = {"kind": "dick_card", "name": name, "system_prompt": conv["system_prompt"]}
        if isinstance(conv.get("card_data"), dict):
            saved["card_data"] = conv["card_data"]
        # 完全适配：结构化字段拆分（可编辑）+ 备用开场白
        if isinstance(conv.get("fields"), dict) and conv["fields"]:
            for k, v in conv["fields"].items():
                saved[k] = v
        if conv.get("alternate_greetings"):
            saved["alternate_greetings"] = conv["alternate_greetings"]
        save_guard.atomic_write_json(os.path.join(self.save_dir, fn), saved)
        self.roles.append({"name": name, "file": fn, "prompt": conv["system_prompt"], "data": saved})
        if low.endswith((".png", ".webp")):
            try:
                avdir = os.path.join(self.save_dir, "avatars")
                os.makedirs(avdir, exist_ok=True)
                ext = "webp" if low.endswith(".webp") else "png"
                with open(os.path.join(avdir, self._safe_name(name) + "." + ext), "wb") as f:
                    f.write(raw)
            except Exception:
                pass
        # 完全适配：酒馆 v2 内嵌世界书（extensions.world）→ DICK 世界卡
        world_note = ""
        entries = conv.get("world_entries") or []
        if entries:
            try:
                wn = name + " 的世界书"
                found = next((w for w in self.worlds if w.get("name") == wn), None)
                if found:
                    merged = found.get("entries") or []
                    existing_ids = {str(e.get("id")) for e in merged}
                    for e in entries:
                        if str(e.get("id")) not in existing_ids:
                            merged.append(e)
                    found["entries"] = merged
                    save_guard.atomic_write_json(
                        os.path.join(self.world_dir, self._safe_name(wn) + ".json"), found)
                else:
                    wdata = {"name": wn,
                             "description": "从角色卡「" + name + "」导入的酒馆世界书",
                             "rules": [], "entries": entries, "params": {}}
                    save_guard.atomic_write_json(
                        os.path.join(self.world_dir, self._safe_name(wn) + ".json"), wdata)
                    self.worlds.append(wdata)
                world_note = "，世界书 " + str(len(entries)) + " 条 → 世界卡「" + wn + "」"
            except Exception as e:
                print(f"[导入] 世界书写入失败: {e}")
        return {"ok": True, "name": name, "note": world_note}

    def _do_export_card(self, name, fmt, path):
        role = next((r for r in self.roles if r["name"] == name), None)
        if not role:
            return {"ok": False, "err": "角色不存在"}
        # 关联世界卡（`<角色名> 的世界书`）→ 导出时写回酒馆 extensions.world（无损反向）
        world_entries = []
        try:
            wn = name + " 的世界书"
            w = next((x for x in self.worlds if x.get("name") == wn), None)
            if w:
                world_entries = w.get("entries") or []
        except Exception:
            pass
        card = card_compat.dick_to_v2(name, role["prompt"],
                                      (role.get("data") or {}).get("card_data"),
                                      world_entries=world_entries)
        try:
            if fmt == "json":
                save_guard.atomic_write_json(path, card)
            else:
                png = None
                avdir = os.path.join(self.save_dir, "avatars")
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    p = os.path.join(avdir, self._safe_name(name) + ext)
                    if os.path.exists(p):
                        with open(p, "rb") as f:
                            png = f.read()
                        break
                if png is None:
                    png = card_compat.placeholder_png(name)
                with open(path, "wb") as f:
                    f.write(card_compat.png_embed_card(png, card))
        except Exception as e:
            return {"ok": False, "err": "导出失败：" + str(e)}
        return {"ok": True}

    def _norm_entries(self, entries_json):
        """规范化世界书条目列表（字段齐全、类型安全）"""
        try:
            raw = json.loads(entries_json) if isinstance(entries_json, str) else (entries_json or [])
        except Exception:
            raw = []
        if not isinstance(raw, list):
            raw = []

        def num(v, d):
            try:
                return float(v)
            except (TypeError, ValueError):
                return d

        entries = []
        for e in raw:
            if not isinstance(e, dict):
                continue
            keywords = e.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.replace("，", ",").split(",") if k.strip()]
            keywords = [str(k).strip() for k in keywords if str(k).strip()]
            content = str(e.get("content", "")).strip()
            if not content:
                continue
            entries.append({
                "id": str(e.get("id") or ""),
                "keywords": keywords,
                "content": content,
                "match": str(e.get("match") or "any").lower(),
                "weight": num(e.get("weight"), 100),
                "probability": num(e.get("probability"), 100),
                "depth": int(num(e.get("depth"), 1)),
                "enabled": bool(e.get("enabled", True)),
                "constant": bool(e.get("constant", False)),
            })
        return entries

    def _reload_roles(self):
        """从磁盘重建角色列表（保留选中项）"""
        self.roles = []
        try:
            for fn in sorted(os.listdir(self.save_dir)):
                if fn.startswith("."):
                    continue  # 跳过跑团会期锁等隐藏/元数据文件
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(self.save_dir, fn), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("system_prompt"):
                        prompt, fields, legacy = role_prompt_from_card(
                            data.get("name") or fn[:-5], data)
                        self.roles.append({"name": data.get("name") or fn[:-5], "file": fn,
                                           "prompt": prompt, "data": data,
                                           "fields": fields, "legacy": legacy})
                except Exception:
                    continue
        except Exception:
            pass
        self.selected_roles = [n for n in self.selected_roles if any(r["name"] == n for r in self.roles)]

    def _reload_worlds(self):
        """从磁盘重建世界列表（保留选中项）"""
        self.worlds = []
        try:
            for fn in sorted(os.listdir(self.world_dir)):
                if not fn.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(self.world_dir, fn), "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("name"):
                        self.worlds.append(data)
                except Exception:
                    continue
        except Exception:
            pass
        self.selected_worlds = [n for n in self.selected_worlds if any(w.get("name") == n for w in self.worlds)]

    @staticmethod
    def _wire_sprites_to_speakers(self, name):
        """把包内立绘按角色名（或顺序）自动挂到还没立绘的台词上。返回挂接次数。"""
        pkg = self._codex_pkg_path(name)
        jp = os.path.join(pkg, "codex.json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return 0
        sdir = os.path.join(pkg, "sprites")
        allsp = []
        if os.path.isdir(sdir):
            try:
                allsp = sorted(f for f in os.listdir(sdir)
                               if os.path.isfile(os.path.join(sdir, f)))
            except Exception:
                pass
        if not allsp:
            return 0

        def match_sprite(key):
            if not key:
                return None
            for f in allsp:
                stem = os.path.splitext(f)[0]
                if key in stem or stem in key:
                    return f
            return None

        # 收集角色名（首次出现顺序）
        speakers = []
        for sc in data.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            for ln in sc.get("lines") or []:
                if isinstance(ln, dict) and ln.get("speaker"):
                    sp = str(ln["speaker"]).strip()
                    if sp and sp not in speakers:
                        speakers.append(sp)
        speaker_sprite = {}
        used = set()
        for sp in speakers:
            m = match_sprite(sp)
            if m and m not in used:
                speaker_sprite[sp] = m
                used.add(m)
            else:
                for f in allsp:
                    if f not in used:
                        speaker_sprite[sp] = f
                        used.add(f)
                        break
        wired = 0
        for sc in data.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            for ln in sc.get("lines") or []:
                if not isinstance(ln, dict):
                    continue
                if ln.get("speaker") and not ln.get("sprite"):
                    sp = str(ln["speaker"]).strip()
                    if sp in speaker_sprite and speaker_sprite[sp]:
                        ln["sprite"] = "sprites/" + speaker_sprite[sp]
                        wired += 1
        try:
            save_guard.atomic_write_json(jp, data)
        except Exception:
            pass
        return wired
