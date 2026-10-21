# -*- coding: utf-8 -*-
"""shell_api_misc —— 从 Kit.py 拆出的 mixin（^api_card|^api_export|^api_save|^api_delete|^api_create|^api_update|^api_clear|^api_switch|^api_memory|^api_）。

包含方法：api_job_submit、api_memory_audit、api_jobs_status、api_poll、api_pick_choice、api_cyoa、api_battle_move、api_quick_replies、api_dismiss_welcome、api_send、api_travel、api_create_role…

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

from shell_api_media import ApiMediaMixin
from shell_api_card import ApiCardMixin
from shell_api_chat import ApiChatMixin

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

class ApiMiscMixin(ApiMediaMixin, ApiCardMixin, ApiChatMixin):
    """shell_api_misc"""

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
            # 线满了：明确告诉前端（它可以退<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌化成同步调用），而不是悄悄不动
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

