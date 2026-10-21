# -*- coding: utf-8 -*-
"""shell_codex —— 从 Kit.py 拆出的 mixin（^_codex|^_player）。

包含方法：_codex_pkg_path、_codex_exe_worker、_player_size_mb、_codex_player_worker、_codex_release_worker

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

import codex_core
import os
import save_guard
import shutil

class CodexMixin:
    """shell_codex"""

    def _codex_pkg_path(self, name):
        p = os.path.join(self.codex_dir, codex_core._safe_name(name))
        # 防目录穿越：确保解析后的路径仍在本目录内（防<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌御性深挖，即便 _safe_name 失效）
        try:
            root = os.path.realpath(self.codex_dir)
            real = os.path.realpath(p)
            if os.path.commonpath([root, real]) != root:
                p = os.path.join(root, "_unsafe")
        except Exception:
            pass
        return p


    def _codex_exe_worker(self, name):
        """后台：打包 EXE + 写状态文件"""
        state_file = os.path.join(self._codex_pkg_path(name), "dist", ".exe_build_state.json")
        def set_state(st, msg, extra=None):
            d = {"state": st, "msg": msg}
            if extra:
                d.update(extra)
            # 原子写：前端轮询读取时不会读到写一半的残缺 JSON
            try:
                save_guard.atomic_write_json(state_file, d)
            except Exception:
                pass
        try:
            set_state("building", "正在生成独立播放器…")
            pkg = self._codex_pkg_path(name)
            out_dir = os.path.join(pkg, "dist")
            # 找可用的 python 解释器（优先当前；冻结运行时退回 PATH 里的 python）
            import sys as _sys
            py_cmd = None
            if not getattr(_sys, "frozen", False):
                py_cmd = _sys.executable
            set_state("building", "正在调用 PyInstaller（首次约 1-2 分钟）…")
            exe, counts = codex_core.build_standalone_exe(
                pkg, out_dir, name=name, py_cmd=py_cmd,
                log_cb=lambda m: set_state("building", m))
            set_state("done", "打包完成",
                      {"exe": os.path.basename(exe), "size": os.path.getsize(exe),
                       "counts": counts,
                       "rel": os.path.relpath(exe, pkg).replace("\\", "/")})
        except Exception as e:
            set_state("error", str(e)[:300])


    @staticmethod
    def _player_size_mb(path):
        total = 0
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
        return round(total / 1048576.0, 1)


    def _codex_player_worker(self, name, player, dest, state_file):
        """后台：拷播放器 + 放故事，并写状态文件"""
        def set_state(st, msg, extra=None):
            d = {"state": st, "msg": msg}
            if extra:
                d.update(extra)
            try:
                save_guard.atomic_write_json(state_file, d)
            except Exception:
                pass
        try:
            import shutil
            pkg = self._codex_pkg_path(name)

            set_state("building", "正在复制播放器（约 127 MB，第一次稍慢）…")
            if os.path.isdir(dest):
                # 删不干净通常是播放器还开着（exe 被占用）→ 说人话，别抛 WinError
                try:
                    shutil.rmtree(dest)
                except Exception:
                    locked = []
                    for root, _dirs, files in os.walk(dest):
                        for fn in files:
                            try:
                                os.remove(os.path.join(root, fn))
                            except Exception:
                                locked.append(fn)
                    if locked:
                        set_state("error",
                                  "目标目录里有文件正被占用（多半是播放器还开着）："
                                  + "、".join(sorted(set(locked))[:5])
                                  + " —— 请先关掉 DICK-Narrative.exe 再导出。")
                        return
                    shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(dest, exist_ok=True)
            shutil.copytree(player, dest, dirs_exist_ok=True)

            set_state("building", "正在放入故事与素材…")
            story = os.path.join(dest, "story")
            # 播放器自带一份示例故事，导出时必须清掉，否则会和你的故事打架
            shutil.rmtree(story, ignore_errors=True)
            os.makedirs(story, exist_ok=True)
            shutil.copy2(os.path.join(pkg, "codex.json"),
                         os.path.join(story, "codex.json"))
            counts = {}
            for kind in codex_core.SUBDIRS:
                src = os.path.join(pkg, kind)
                n = 0
                if os.path.isdir(src):
                    dst = os.path.join(story, kind)
                    os.makedirs(dst, exist_ok=True)
                    for fn in sorted(os.listdir(src)):
                        sp = os.path.join(src, fn)
                        if os.path.isfile(sp):
                            shutil.copy2(sp, os.path.join(dst, fn))
                            n += 1
                counts[kind] = n

            readme = os.path.join(dest, "玩这个.txt")
            try:
                with open(readme, "w", encoding="utf-8") as f:
                    f.write(
                        "《%s》\n\n"
                        "双击 DICK-Narrative.exe 就能玩。\n"
                        "整个文件夹要一起拷走（runtime 和 app 是播放器自带的运行环境）。\n\n"
                        "操作：鼠标点任意处推进 / 空格回车推进 / Esc 打开菜单\n"
                        "剧情分支会按好感度、状态、标记自动筛选。\n" % name)
            except Exception:
                pass

            size = self._player_size_mb(dest)
            set_state("done", "导出完成",
                      {"dest": dest, "size": size, "counts": counts,
                       "rel": os.path.basename(dest)})
        except Exception as e:
            set_state("error", str(e)[:300])


    def _codex_release_worker(self, name):
        """后台：发布三件套（HTML → EXE → .codex）"""
        import sys as _sys
        state_file = os.path.join(self._codex_pkg_path(name), "dist", ".exe_build_state.json")
        def set_state(st, msg, extra=None):
            d = {"state": st, "msg": msg}
            if extra:
                d.update(extra)
            # 原子写：前端轮询读取时不会读到写一半的残缺 JSON
            try:
                save_guard.atomic_write_json(state_file, d)
            except Exception:
                pass
        try:
            pkg = self._codex_pkg_path(name)
            out_dir = os.path.join(pkg, "dist")
            os.makedirs(out_dir, exist_ok=True)
            safe = codex_core._safe_name(name)
            set_state("building", "① 生成独立 HTML…")
            ok, path, counts = codex_core.build_standalone_file(pkg, os.path.join(out_dir, safe + ".html"))
            if not ok:
                set_state("error", "HTML 打包失败")
                return
            # ② EXE
            set_state("building", "② 打包 EXE（首次约 1-2 分钟）…")
            py_cmd = None if getattr(_sys, "frozen", False) else _sys.executable
            exe, counts = codex_core.build_standalone_exe(pkg, out_dir, name=name, py_cmd=py_cmd)
            # ③ .codex
            set_state("building", "③ 生成 .codex 包…")
            codex_path = os.path.join(out_dir, safe + ".codex")
            codex_core.export_zip(pkg, codex_path)
            set_state("done", "发布完成：EXE + HTML + .codex",
                      {"exe": os.path.basename(exe),
                       "html": safe + ".html",
                       "codex": safe + ".codex",
                       "size_exe": os.path.getsize(exe),
                       "size_html": os.path.getsize(os.path.join(out_dir, safe + ".html")),
                       "size_codex": os.path.getsize(codex_path),
                       "rel": "dist",
                       "counts": counts})
        except Exception as e:
            set_state("error", str(e)[:300])


