# -*- coding: utf-8 -*-
"""shell_api_codex —— 从 Kit.py 拆出的 mixin（^api_codex）。

包含方法：api_codex_list、api_codex_create、api_codex_sample、api_codex_auto_voice、api_codex_draft、api_codex_import_folder、api_codex_get、api_codex_save、api_codex_validate、api_codex_delete、api_codex_export、api_codex_import_zip…

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

from shell_util import BASE_DIR

import codex_core
import json
import os
import plugin_manager
import save_guard
import shutil
import subprocess
import sys
import threading

class ApiCodexMixin:
    """shell_api_codex"""

    def api_codex_list(self):
        """列出所有 CODEX 包：name / intro / 场景数 / 资源统计"""
        out = []
        try:
            for fn in sorted(os.listdir(self.codex_dir)):
                d = os.path.join(self.codex_dir, fn)
                if not os.path.isdir(d):
                    continue
                info = {"name": fn, "intro": "", "scenes": 0,
                        "sprites": 0, "bg": 0, "bgm": 0, "voice": 0,
                        "has_script": False}
                jp = os.path.join(d, "codex.json")
                if os.path.isfile(jp):
                    try:
                        with open(jp, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        info["has_script"] = True
                        info["intro"] = str(data.get("intro") or "")[:120]
                        info["scenes"] = len(data.get("scenes") or [])
                    except Exception:
                        pass
                for kind in codex_core.SUBDIRS:
                    kd = os.path.join(d, kind)
                    if os.path.isdir(kd):
                        try:
                            info[kind] = len([x for x in os.listdir(kd)
                                              if os.path.isfile(os.path.join(kd, x))])
                        except Exception:
                            pass
                out.append(info)
        except Exception:
            pass
        return {"ok": True, "packages": out}


    def api_codex_create(self, name):
        """新建 CODEX 包：生成示例剧本 + 空资源目录"""
        name = (name or "").strip()[:60]
        if not name:
            return {"ok": False, "err": "empty"}
        dst = self._codex_pkg_path(name)
        try:
            os.makedirs(dst, exist_ok=True)
            for k in codex_core.SUBDIRS:
                os.makedirs(os.path.join(dst, k), exist_ok=True)
            jp = os.path.join(dst, "codex.json")
            if not os.path.isfile(jp):
                with open(jp, "w", encoding="utf-8") as f:
                    json.dump(codex_core.make_template(name), f,
                              ensure_ascii=False, indent=2)
            return {"ok": True, "name": os.path.basename(dst)}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_sample(self, name="示例·夏日祭"):
        """一键示例包：生成带占位立绘/背景/音乐/配音的真实可播 CODEX 包"""
        ok, dst = codex_core.make_sample_package(self.codex_dir, name)
        if not ok:
            return {"ok": False, "err": "生成失败：" + str(dst)[:120]}
        return {"ok": True, "name": os.path.basename(dst)}


    def api_codex_auto_voice(self, name, lang="ja"):
        """素材供应链：一键配音——为剧本里所有有 text 的台词批量合成配音，
        写入包内 voice/ 并更新剧本引用。lang: ja(日文) / zh(中文，需声库支持)。
        返回 {ok, done, msg}。"""
        pkg = self._codex_pkg_path(name)
        jp = os.path.join(pkg, "codex.json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return {"ok": False, "err": "读剧本失败：" + str(e)[:120]}
        # UTA<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌U 插件
        p = None
        try:
            if self.plugin_manager:
                p = self.plugin_manager.get_plugin("UTAU 语音")
        except Exception:
            p = None
        if not p or not getattr(p, "enabled", False):
            return {"ok": False, "err": "未启用 UTAU 语音插件（设置 → 插件 → UTAU 语音）"}
        if not hasattr(p, "_speak"):
            return {"ok": False, "err": "UTAU 插件缺少合成接口"}
        voice_dir = os.path.join(pkg, "voice")
        os.makedirs(voice_dir, exist_ok=True)
        done = 0
        failed = 0
        scenes = data.get("scenes") or []
        for si, sc in enumerate(scenes):
            for li, ln in enumerate(sc.get("lines") or []):
                if not isinstance(ln, dict):
                    continue
                text = str(ln.get("text") or "").strip()
                if not text or len(text) > 200:
                    continue
                try:
                    res = p._speak(text)
                    # _speak 播放并返回 "🗣️ text"；找到刚生成的 wav（tts_cache 最新）
                    base = getattr(app_paths, "get_base_dir", lambda: BASE_DIR)()
                    cache = os.path.join(base, "tts_cache")
                    cand = []
                    if os.path.isdir(cache):
                        cand = sorted([os.path.join(cache, f) for f in os.listdir(cache)
                                       if f.endswith(".wav")], key=os.path.getmtime, reverse=True)
                    if not cand:
                        failed += 1
                        continue
                    src = cand[0]
                    fn = f"auto_{si}_{li}.wav"
                    import shutil
                    shutil.copy2(src, os.path.join(voice_dir, fn))
                    ln["voice"] = "voice/" + fn
                    done += 1
                except Exception as e:
                    failed += 1
                    print(f"[CODEX voice] {si}/{li} 失败: {e}")
        save_guard.atomic_write_json(jp, data)
        return {"ok": True, "done": done, "failed": failed,
                "msg": f"配音完成：{done} 句成功" + (f"，{failed} 句失败" if failed else "")}


    def api_codex_draft(self, name, idea, count=3):
        """素材供应链：AI 起草剧本——给一句话主题，生成完整 codex.json。
        返回 {ok, script}（不落盘，前端预览后可保存）。"""
        idea = (idea or "").strip()
        if not idea:
            return {"ok": False, "err": "empty idea"}
        client = getattr(self.core, "client", None)
        if not client:
            return {"ok": False, "err": "未配置模型（设置里填 API Key）"}
        try:
            count = max(1, min(5, int(count or 3)))
        except (TypeError, ValueError):
            count = 3
        sys_prompt = (
            "你是视觉小说（GALGAME）剧本作家。根据用户给出的主题，生成一份 CODEX 剧本 JSON。\n"
            "格式（严格遵循，只输出 JSON）：\n"
            "{\n"
            '  "name": "剧本名",\n'
            '  "intro": "一句话简介",\n'
            '  "scenes": [\n'
            '    {"id": "s1", "title": "章节名", "bg": "", "lines": [\n'
            '      {"note": "舞台说明（旁白，无 speaker）"},\n'
            '      {"speaker": "角色名", "text": "台词"},\n'
            '      {"speaker": "角色名", "sprite": "", "text": "带动作的台词"},\n'
            '      {"choice": [{"text": "选项A", "goto": "s2"}, {"text": "选项B", "goto": "s3"}]},\n'
            '      {"end": "结局标题"}\n'
            '    ]}\n'
            '  ]\n'
            "}\n"
            "要求：\n"
            f"1. 生成 {count} 个场景（s1 起，id 连续），至少 2 个分支结局。\n"
            "2. 台词口语化、有情感张力，符合视觉小说节奏；旁白用 note 行。\n"
            "3. 选项分支用 goto 指向对应场景；场景末尾可 jump 回主线或用 end 结束。\n"
            "4. 只输出 JSON，不要 markdown 代码块包裹，不要额外说明。\n"
        )
        resp = client.chat.completions.create(
            model=self.core.model,
            messages=[{"role": "system", "content": sys_prompt},
                      {"role": "user", "content": idea}],
            stream=False, timeout=90,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # 宽容解析：去代码块、取 JSON 对象
        import re as _re
        m = _re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {"ok": False, "err": "模型未输出有效 JSON"}
        try:
            data = json.loads(m.group(0))
        except Exception as e:
            return {"ok": False, "err": "JSON 解析失败：" + str(e)[:100]}
        if not isinstance(data, dict) or not data.get("scenes"):
            return {"ok": False, "err": "剧本缺少 scenes"}
        data.setdefault("name", (name or "我的故事"))
        data.setdefault("author", "")
        ok_v, issues = codex_core.validate_codex(data)
        return {"ok": True, "script": data, "valid": ok_v, "issues": issues}



    def api_codex_import_folder(self):
        """文件对话框选文件夹 → 自动归类为 CODEX 包（傻瓜化导入）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(webview.FileDialog.FOLDER)
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        src = res[0]
        base = os.path.basename(src.rstrip("/\\")) or "未命名"
        r = codex_core.import_folder(src, self.codex_dir, base)
        return {"ok": r["ok"], "msg": r.get("msg", ""), "name": base,
                "moved": r.get("moved", {})}


    def api_codex_get(self, name):
        """读取剧本 codex.json（JSON 功能：编辑预填）"""
        jp = os.path.join(self._codex_pkg_path(name), "codex.json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            ok, issues = codex_core.validate_codex(data)
            return {"ok": True, "script": data, "valid": ok, "issues": issues}
        except FileNotFoundError:
            return {"ok": False, "err": "not found"}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_save(self, name, script_json):
        """保存剧本（校验 + 原子写盘）"""
        try:
            data = json.loads(script_json or "{}")
        except Exception as e:
            return {"ok": False, "err": "JSON 解析失败：" + str(e)[:120]}
        if not isinstance(data, dict):
            return {"ok": False, "err": "剧本必须是 JSON 对象"}
        data.setdefault("name", name)
        # 傻瓜化：保存时对位包内资源（粘贴/文本/AI 剧本统一受益）
        data = codex_core.normalize_script(data, pkg_dir=self._codex_pkg_path(name))
        ok, issues = codex_core.validate_codex(data)
        jp = os.path.join(self._codex_pkg_path(name), "codex.json")
        try:
            save_guard.atomic_write_json(jp, data)
        except Exception as e:
            return {"ok": False, "err": "写入失败：" + str(e)[:120]}
        return {"ok": True, "valid": ok, "issues": issues}


    def api_codex_validate(self, name):
        """重新校验剧本，返回 (valid, issues)"""
        jp = os.path.join(self._codex_pkg_path(name), "codex.json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                data = json.load(f)
            ok, issues = codex_core.validate_codex(data)
            return {"ok": True, "valid": ok, "issues": issues}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}


    def api_codex_delete(self, name):
        """删除 CODEX 包（整个目录）"""
        import shutil
        d = self._codex_pkg_path(name)
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
            except Exception as e:
                return {"ok": False, "err": str(e)[:120]}
        return {"ok": True}


    def api_codex_export(self, name):
        """导出 CODEX 包为 zip（JSON 功能：分享/备份）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            safe = codex_core._safe_name(name)
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=safe + ".zip",
                                         file_types=("CODEX 包 (*.zip)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            path = res[0]
            if not path.lower().endswith(".zip"):
                path += ".zip"
            if codex_core.export_zip(self._codex_pkg_path(name), path):
                return {"ok": True, "file": os.path.basename(path)}
            return {"ok": False, "err": "导出失败"}
        except Exception as e:
            return {"ok": False, "err": "导出失败：" + str(e)[:120]}


    def api_codex_import_zip(self):
        """导入 CODEX zip 包"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("CODEX 包 (*.zip)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        ok, name, msg = codex_core.import_zip(res[0], self.codex_dir)
        return {"ok": ok, "name": name, "msg": msg}


    def api_codex_pack(self, name):
        """打包：把 CODEX 包生成独立单文件 HTML（GALGAME，双击即玩，可分发）。
        默认保存到包内 dist/ 目录，返回可直接打开/分发的路径。"""
        pkg = self._codex_pkg_path(name)
        dist_dir = os.path.join(pkg, "dist")
        try:
            os.makedirs(dist_dir, exist_ok=True)
            safe = codex_core._safe_name(name)
            out = os.path.join(dist_dir, safe + ".html")
            ok, path, counts = codex_core.build_standalone_file(pkg, out)
            if not ok:
                return {"ok": False, "err": "打包失败"}
            size = os.path.getsize(path)
            return {"ok": True, "path": path, "size": size,
                    "counts": counts, "rel": os.path.relpath(path, pkg).replace("\\", "/")}
        except Exception as e:
            return {"ok": False, "err": "打包失败：" + str(e)[:200]}


    def api_codex_pack_save_as(self, name):
        """打包并另存为（另存对话框选位置）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            safe = codex_core._safe_name(name)
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=safe + ".html",
                                         file_types=("GALGAME (*.html)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            out = res[0]
            if not out.lower().endswith(".html"):
                out += ".html"
            ok, path, counts = codex_core.build_standalone_file(self._codex_pkg_path(name), out)
            if not ok:
                return {"ok": False, "err": "打包失败"}
            return {"ok": True, "path": path,
                    "size": os.path.getsize(path), "counts": counts}
        except Exception as e:
            return {"ok": False, "err": "打包失败：" + str(e)[:200]}

    # ---------- 打包 EXE（独立可执行，双击即玩） ----------

    # ---------- 打包 EXE（独立可执行，双击即玩） ----------
    def api_codex_pack_exe(self, name):
        """打包 CODEX 包为独立 EXE（后台线程，完成后可 api_codex_pack_exe_status 查询）。
        需要本机 Python 环境含 PyInstaller。输出到 codex/<包名>/dist/。"""
        import threading
        try:
            pkg = self._codex_pkg_path(name)
            if not os.path.isfile(os.path.join(pkg, "codex.json")):
                return {"ok": False, "err": "包不存在"}
            state_file = os.path.join(pkg, "dist", ".exe_build_state.json")
            try:
                os.makedirs(os.path.dirname(state_file), exist_ok=True)
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump({"state": "building", "msg": "开始打包…"}, f)
            except Exception:
                pass
            threading.Thread(target=self._codex_exe_worker, args=(name,), daemon=True).start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_pack_exe_status(self, name):
        """查询打包 EXE 进度（前端轮询）"""
        state_file = os.path.join(self._codex_pkg_path(name), "dist", ".exe_build_state.json")
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return {"ok": True, **json.load(f)}
        except FileNotFoundError:
            return {"ok": True, "state": "idle", "msg": "尚未开始"}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}

    # ---------- 导出到「叙事引擎」原生播放器（Kotlin，EXE / APK） ----------
    # 和上面「打包 HTML EXE」的区别：这里产出的是真正的原生窗口程序，
    # 引擎与渲染器分离，同一份 codex.json 还能喂给安卓 APK 和 DICK 主程序。

    PLAYER_DIRNAME = "DICK-Narrative"
    PLAYER_EXE = "DICK-Narrative.exe"


    def api_codex_export_player(self, name):
        """把 CODEX 包导出成「播放器 + 故事」的成品目录（后台线程）。
        产出结构：
            <目标目录>/<包名>/
                DICK-Narrative.exe  app/  runtime/    ← 原生播放器（自带运行时）
                story/codex.json  sprites/ bg/ bgm/ voice/
                玩这个.txt
        """
        try:
            pkg = self._codex_pkg_path(name)
            if not os.path.isfile(os.path.join(pkg, "codex.json")):
                return {"ok": False, "err": "包不存在"}
            player = self._find_player_dir()
            if not player:
                return {"ok": False,
                        "err": "还没构建播放器。先在 DICK-Narrative 目录跑一次 build.ps1 -Exe，"
                               "或把窗口里的「目标目录」指到已构建好的播放器上。"}
            # 选目标目录（默认桌面）
            dest_root = None
            try:
                import webview
                win = webview.windows[0] if getattr(webview, "windows", None) else None
                if win is not None:
                    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                    res = win.create_file_dialog(
                        webview.FileDialog.FOLDER,
                        directory=desktop if os.path.isdir(desktop) else os.path.expanduser("~"))
                    if not res:
                        return {"ok": False, "err": "cancelled"}
                    dest_root = res[0]
            except Exception:
                dest_root = None
            if not dest_root:
                dest_root = os.path.join(pkg, "dist", "player")

            safe = codex_core._safe_name(name)
            dest = os.path.join(dest_root, safe)
            state_file = os.path.join(pkg, "dist", ".player_build_state.json")
            try:
                os.makedirs(os.path.dirname(state_file), exist_ok=True)
                save_guard.atomic_write_json(state_file,
                                             {"state": "building", "msg": "准备导出…"})
            except Exception:
                pass
            threading.Thread(target=self._codex_player_worker,
                             args=(name, player, dest, state_file),
                             daemon=True).start()
            return {"ok": True, "dest": dest}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_player_status(self, name):
        """查询「导出到播放器」进度（前端轮询）"""
        state_file = os.path.join(self._codex_pkg_path(name), "dist", ".player_build_state.json")
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return {"ok": True, **json.load(f)}
        except FileNotFoundError:
            return {"ok": True, "state": "idle", "msg": "尚未开始"}
        except Exception as e:
            return {"ok": False, "err": str(e)[:120]}


    def api_codex_player_ready(self):
        """播放器是否已构建（前端用来提示/禁用按钮）"""
        p = self._find_player_dir()
        return {"ok": True, "ready": bool(p), "dir": p or ""}

    # ================= CODEX 系统权限（DICK 内置特权引擎） =================


    def api_codex_register_assoc(self):
        """注册 .codex 文件关联：双击 .codex 包 → 用 DICK 打开播放。
        写 HKCU 注册表（无需管理员）。返回 (ok, msg)。"""
        try:
            import winreg
            exe = os.path.abspath(sys.executable) if getattr(sys, "frozen", False) else \
                os.path.join(BASE_DIR, "DICK-HTML.exe")
            if not os.path.isfile(exe):
                exe = sys.executable
            # 1) ProgID
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Classes\DICK.Codex\shell\open\command") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, f'"{exe}" "%1"')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Classes\DICK.Codex\DefaultIcon") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, f'"{exe}",0')
            # 2) 扩展名关联
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                  r"Software\Classes\.codex") as k:
                winreg.SetValue(k, "", winreg.REG_SZ, "DICK.Codex")
            return {"ok": True, "msg": "✅ 已注册：双击 .codex 包将直接用 DICK 打开播放"}
        except Exception as e:
            return {"ok": False, "err": "注册失败：" + str(e)[:200]}


    def api_codex_export_codex(self, name):
        """导出 .codex 包（系统权限：保存到用户选的任意位置，双击即可在 DICK 打开）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            safe = codex_core._safe_name(name)
            res = win.create_file_dialog(webview.FileDialog.SAVE,
                                         save_filename=safe + ".codex",
                                         file_types=("CODEX 包 (*.codex)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            path = res[0]
            if not path.lower().endswith(".codex"):
                path += ".codex"
            if codex_core.export_zip(self._codex_pkg_path(name), path):
                return {"ok": True, "file": os.path.basename(path)}
            return {"ok": False, "err": "导出失败"}
        except Exception as e:
            return {"ok": False, "err": "导出失败：" + str(e)[:200]}


    def api_codex_import_codex(self):
        """导入 .codex 包（系统权限：从任意位置选文件，自动解包到 codex/）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=("CODEX 包 (*.codex)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        ok, name, msg = codex_core.import_zip(res[0], self.codex_dir)
        return {"ok": ok, "name": name, "msg": msg}


    def api_codex_import_script(self, text):
        """傻瓜化：粘贴剧本自动转化为 codex.json。支持两种输入：
        - 文本以 '{' 开头 → 当作 codex.json 直接规整（补默认、对位资源）；
        - 否则 → 纯文本剧本（parse_script_text 解析）。
        不落盘，返回 {ok, script, valid, issues, kind, autoName}，前端预览后保存。"""
        text = (text or "").strip()
        if not text:
            return {"ok": False, "err": "empty"}
        kind = "text"
        data = None
        if text.startswith("{"):
            try:
                data = json.loads(text)
                kind = "json"
            except Exception:
                data = None
        if data is None:
            data = codex_core.parse_script_text(text)
            if data is None:
                if text.startswith("{"):
                    return {"ok": False, "err": "JSON 解析失败"}
                return {"ok": False,
                        "err": "无法识别剧本格式（首行用【场景】标题，或用 > 旁白、角色名：台词）"}
            kind = "text"
        data = codex_core.normalize_script(data)
        ok, issues = codex_core.validate_codex(data)
        return {"ok": True, "script": data, "valid": ok, "issues": issues,
                "kind": kind, "autoName": str(data.get("name") or "").strip() or "未命名剧本"}


    def api_codex_import_sprites(self, name):
        """立绘傻瓜化导入：多选图片 → 放入包内 sprites/，自动按角色名/顺序把缺立绘的
        台词挂上立绘并保存。返回 {ok, added, wired, msg}。"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=True,
                file_types=("图片 (*.png;*.jpg;*.jpeg;*.webp;*.gif)", "All files (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        if not isinstance(res, (list, tuple)):
            res = [res]
        pkg = self._codex_pkg_path(name)
        sprites_dir = os.path.join(pkg, "sprites")
        os.makedirs(sprites_dir, exist_ok=True)
        import shutil as _sh
        added = []
        for src in res:
            base = os.path.basename(str(src))
            ext = os.path.splitext(base)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                continue
            out = os.path.join(sprites_dir, base)
            i = 1
            while os.path.exists(out):
                stem, e = os.path.splitext(base)
                out = os.path.join(sprites_dir, f"{stem}_{i}{e}")
                i += 1
            try:
                _sh.copy2(src, out)
                added.append(os.path.basename(out))
            except Exception:
                pass
        if not added:
            return {"ok": False, "err": "未导入任何图片"}
        wired = self._wire_sprites_to_speakers(name)
        return {"ok": True, "added": added, "wired": wired,
                "msg": f"导入 {len(added)} 张立绘，自动挂接 {wired} 处台词"}


    def api_codex_get_player_template(self, name):
        """高级模式：返回可编辑的播放器模板源码。包内若有 player.html（自定义）则用之，
        否则返回系统内置模板。name 为空时恒返回系统内置模板（用于“恢复默认”）。"""
        try:
            if not (name or "").strip():
                return {"ok": True, "html": codex_core.DEFAULT_EDITABLE_TEMPLATE, "is_custom": False}
            pkg = self._codex_pkg_path(name)
            tpl = codex_core._load_custom_template(pkg)
            if tpl is not None:
                return {"ok": True, "html": tpl, "is_custom": True}
            return {"ok": True, "html": codex_core.DEFAULT_EDITABLE_TEMPLATE, "is_custom": False}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_save_player_template(self, name, html):
        """高级模式：保存自定义播放器模板到包内 player.html。模板需保留 __CODEX_PAYLOAD__ 注入点。"""
        html = (html or "").strip()
        if not html:
            return {"ok": False, "err": "empty"}
        if "__CODEX_PAYLOAD__" not in html and "__CODEX_EMBED__" not in html:
            return {"ok": False, "err": "模板需保留 __CODEX_PAYLOAD__（或 __CODEX_EMBED__）数据注入点"}
        try:
            pkg = self._codex_pkg_path(name)
            pt = os.path.join(pkg, "player.html")
            with open(pt, "w", encoding="utf-8") as f:
                f.write(html)
            return {"ok": True, "msg": "模板已保存"}
        except Exception as e:
            return {"ok": False, "err": "保存失败：" + str(e)[:200]}


    def api_codex_render(self, name, html=None):
        """高级模式：用给定模板实时渲染包为独立 HTML（现场试玩）。
        html 为空则用包内自定义/系统默认模板。返回 {ok, html}。"""
        try:
            pkg = self._codex_pkg_path(name)
            if html and html.strip():
                tpl = html
            else:
                tpl = codex_core._load_custom_template(pkg)
            out, _counts = codex_core.render_standalone(pkg, tpl, state=getattr(self.core, "mechanism_state", None))
            return {"ok": True, "html": out}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_run_program(self, cmd):
        """系统权限：执行本地程序/命令（action 钩子扩展）。
        cmd 是命令字符串，如 notepad.exe 或 完整路径。仅限一次调用，不做 shell 拼接注入。"""
        cmd = (cmd or "").strip()
        if not cmd:
            return {"ok": False, "err": "empty"}
        # 安全检查：只允许 exe/bat/cmd/vbs 直接执行；含 & | ; 等拼接符拒绝
        import re as _re
        if _re.search(r"[&|;><`]", cmd):
            return {"ok": False, "err": "禁止命令拼接"}
        low = cmd.lower().split()
        first = low[0] if low else ""
        if not (first.endswith(".exe") or first.endswith(".bat") or first.endswith(".cmd")
                or first in ("notepad", "calc", "mspaint", "explorer", "cmd", "start")):
            return {"ok": False, "err": "仅允许可执行程序"}
        try:
            import subprocess
            subprocess.Popen(cmd, shell=False)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_volume(self, level):
        """多媒体权限：设置播放器音量（0-100）。返回当前音量。"""
        try:
            level = max(0, min(100, int(level)))
        except (TypeError, ValueError):
            level = 100
        self.codex_volume = level
        return {"ok": True, "volume": level}


    def api_codex_fullscreen(self):
        """多媒体权限：CODEX 播放器全屏独占（pywebview 窗口切换）"""
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            win.toggle_fullscreen()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_clear_auto_open(self):
        """清除双击打开标记（前端播放器启动后调用，避免重复弹窗）"""
        self.codex_auto_open = None
        return {"ok": True}



    def api_codex_release(self, name):
        """两步发布（决战兵器·分发闭环）：一键打包 EXE + HTML + .codex 三件套到包内 dist/。
        后台线程执行，api_codex_pack_exe_status 轮询进度。"""
        import threading
        try:
            pkg = self._codex_pkg_path(name)
            if not os.path.isfile(os.path.join(pkg, "codex.json")):
                return {"ok": False, "err": "包不存在"}
            state_file = os.path.join(pkg, "dist", ".exe_build_state.json")
            try:
                os.makedirs(os.path.dirname(state_file), exist_ok=True)
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump({"state": "building", "msg": "开始发布…"}, f)
            except Exception:
                pass
            threading.Thread(target=self._codex_release_worker, args=(name,), daemon=True).start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}


    def api_codex_asset(self, name, kind, file):
        """返回 CODEX 包内资源的 dataURL（播放器/预览用）。
        kind: sprites/bg/bgm/voice；file: 相对该 kind 目录的文件名"""
        kind = (kind or "").lower()
        if kind not in codex_core.SUBDIRS:
            return {"ok": False, "err": "bad kind"}
        base = os.path.basename((file or "").replace("\\", "/"))
        if not base:
            return {"ok": False, "err": "bad file"}
        p = os.path.join(self._codex_pkg_path(name), kind, base)
        try:
            with open(p, "rb") as f:
                raw = f.read()
        except Exception:
            return {"ok": False, "err": "not found"}
        import base64 as _b64
        ext = os.path.splitext(base)[1].lower()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".webp": "image/webp", ".gif": "image/gif",
                ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
                ".flac": "audio/flac", ".mp4": "audio/mp4", ".m4a": "audio/mp4"}.get(ext, "application/octet-stream")
        return {"ok": True, "data": "data:" + mime + ";base64," + _b64.b64encode(raw).decode("ascii")}

    # 素材类型 → (文件对话框说明, 允许的扩展名)
    ASSET_KINDS = {
        "sprites": ("图片 (*.png;*.jpg;*.jpeg;*.webp;*.gif)", (".png", ".jpg", ".jpeg", ".webp", ".gif")),
        "bg": ("图片 (*.png;*.jpg;*.jpeg;*.webp;*.gif)", (".png", ".jpg", ".jpeg", ".webp", ".gif")),
        "bgm": ("音频 (*.mp3;*.wav;*.ogg;*.flac;*.m4a)", (".mp3", ".wav", ".ogg", ".flac", ".m4a")),
        "voice": ("音频 (*.mp3;*.wav;*.ogg;*.flac;*.m4a;*.mp4)", (".mp3", ".wav", ".ogg", ".flac", ".m4a", ".mp4")),
    }


    def api_codex_import_asset(self, name, kind):
        """把素材文件导入包内对应目录（sprites/bg/bgm/voice），支持多选。
        返回 {ok, added:[文件名], files:{按类型分组}}，方便前端刷新下拉。"""
        if kind not in codex_core.SUBDIRS:
            return {"ok": False, "err": "未知素材类型：" + str(kind)}
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            desc, _exts = self.ASSET_KINDS[kind]
            res = win.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                         file_types=(desc, "所有文件 (*.*)"))
        except Exception as e:
            return {"ok": False, "err": "对话框失败：" + str(e)}
        if not res:
            return {"ok": False, "err": "cancelled"}
        if not isinstance(res, (list, tuple)):
            res = [res]
        ok_exts = self.ASSET_KINDS[kind][1]
        dst_dir = os.path.join(self._codex_pkg_path(name), kind)
        os.makedirs(dst_dir, exist_ok=True)
        import shutil as _sh
        added = []
        for src in res:
            base = os.path.basename(str(src))
            if os.path.splitext(base)[1].lower() not in ok_exts:
                continue
            out = os.path.join(dst_dir, base)
            i = 1
            while os.path.exists(out):
                stem, e = os.path.splitext(base)
                out = os.path.join(dst_dir, f"{stem}_{i}{e}")
                i += 1
            try:
                _sh.copy2(src, out)
                added.append(os.path.basename(out))
            except Exception:
                pass
        if not added:
            return {"ok": False, "err": "没有导入任何文件（格式不支持？）"}
        files = self.api_codex_script_files(name).get("files", {})
        return {"ok": True, "added": added, "files": files}


    def api_codex_script_files(self, name):
        """列出包内全部资源文件（按 kind 分组）——播放器/编辑器引用列表"""
        out = {k: [] for k in codex_core.SUBDIRS}
        for kind in codex_core.SUBDIRS:
            kd = os.path.join(self._codex_pkg_path(name), kind)
            if os.path.isdir(kd):
                try:
                    out[kind] = sorted(x for x in os.listdir(kd)
                                       if os.path.isfile(os.path.join(kd, x)))
                except Exception:
                    pass
        return {"ok": True, "files": out}

    # ================= 围棋（规则引擎 + 提示词注入） =================
    # 设计：规则全部由 go_engine 决定，模型只负责「从候选点里挑一个 + 说台词」。
    # 19 路每步有 250+ 合法点，ASCII 坐标又不携带形状信息，让模型自由算棋必乱下；
    # 所以每轮把引擎挑出的候选点一起注入，模型选，引擎校验。


    def api_codex_analyze(self, script_json, pkg_name=""):
        """剧本体检：对【编辑器里当前这份（可能还没保存的）剧本】做结构分析。

        script_json 由前端 JSON.stringify(galScript) 直接传过来 —— 不要求先保存，
        所以作者改一行就能立刻体检。pkg_name 用来同时检查素材引用（缺文件/孤儿文件）。
        """
        import codex_core
        try:
            data = json.loads(script_json or "{}")
        except Exception as e:
            return {"ok": False, "err": "剧本 JSON 解析失败：" + str(e)[:120]}
        pkg_dir = None
        try:
            name = (pkg_name or "").strip()
            if name:
                cand = os.path.join(self.codex_dir, name)
                if os.path.isdir(cand):
                    pkg_dir = cand
        except Exception:
            pkg_dir = None
        try:
            rep = codex_core.analyze_codex(data, pkg_dir=pkg_dir)
        except Exception as e:
            return {"ok": False, "err": "体检失败：" + str(e)[:140]}
        rep["checked_pkg"] = pkg_dir or ""
        return rep


    def api_codex_run_action(self, cmd):
        """播放器行动钩子（CODEX 深度集成 DICK 的系统权限）。
        支持：
          plugin:<命令>   调用插件命令（如 plugin:/speak こんにちは）
          model:<文本>    调用模型生成一句话（如 model:请描述这个场景的天气）
          aff:<±N>        修改当前角色好感度（机制卡）
          run:<程序>      调用本地程序（如 run:notepad.exe）
          <其他>          默认按插件命令处理（兼容旧剧本 /speak 等）
        返回 {ok, out}。"""
        cmd = (cmd or "").strip()
        if not cmd:
            return {"ok": True, "out": ""}
        low = cmd.lower()
        try:
            if low.startswith("model:"):
                prompt = cmd[len("model:"):].strip()
                if not prompt:
                    return {"ok": True, "out": ""}
                client = getattr(self.core, "client", None)
                if not client:
                    return {"ok": True, "out": "（未配置模型）"}
                try:
                    resp = client.chat.completions.create(
                        model=self.core.model,
                        messages=[{"role": "user", "content": prompt}],
                        stream=False, timeout=30)
                    text = (resp.choices[0].message.content or "").strip()
                    return {"ok": True, "out": text[:200]}
                except Exception as e:
                    return {"ok": True, "out": "（模型调用失败：" + str(e)[:60] + "）"}
            if low.startswith("aff:"):
                try:
                    delta = int(cmd[len("aff:"):].strip())
                    st = getattr(self.core, "mechanism_state", None)
                    if st is None or "affection" not in st:
                        return {"ok": True, "out": "（未启用好感度）"}
                    cfg = getattr(self.core, "_mech_config", None) or {}
                    aff = cfg.get("affection") if isinstance(cfg.get("affection"), dict) else {}
                    hi = int(aff.get("max", 100) or 100)
                    lo = int(aff.get("min", 0) or 0)
                    cur = int(st.get("affection", 50) or 50)
                    st["affection"] = max(lo, min(hi, cur + delta))
                    return {"ok": True, "out": f"❤️ 好感 {cur}→{st['affection']}"}
                except Exception as e:
                    return {"ok": True, "out": "（好感调整失败）"}
            if low.startswith("run:"):
                prog = cmd[len("run:"):].strip()
                r = self.api_codex_run_program(prog)
                return {"ok": r.get("ok", False), "out": r.get("err", "已调用本地程序")}
            # 默认：插件命令（兼容 plugin: 前缀与旧裸命令）
            plugin_cmd = cmd[len("plugin:"):].strip() if low.startswith("plugin:") else cmd
            if self.plugin_manager:
                out = self.plugin_manager.handle_command(plugin_cmd)
                if isinstance(out, str):
                    return {"ok": True, "out": out}
                if isinstance(out, tuple) and out:
                    return {"ok": True, "out": str(out[0])}
        except Exception as e:
            print(f"[CODEX action] 执行失败: {e}")
        return {"ok": True, "out": ""}


    def _find_player_dir(self):
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

