# -*- coding: utf-8 -*-
"""modules/codex/exe.py —— 打包成独立 EXE（pywebview 壳 + PyInstaller）

搬家来源：`codex_core.py` 的 `EXE_SHELL_TEMPLATE` / `build_exe_shell` / `pyinstaller_cmd` /
`build_standalone_exe`，**壳脚本与命令参数一字未改**。

注意两个"不归块管"的东西：
  ① 解释器：`py_cmd` 由调用方给（缺省沿用 `sys.executable`，与搬家前一致）；
  ② 打包动作：真跑 PyInstaller 是**召唤外部程序**，只在用户点"打包 EXE"时发生，
     自检里只验命令构造，绝不真跑（否则一个自检要几分钟，违反"单块自检 <2s"）。
"""

import json
import os

from .pack import _safe_name
from .player import _load_custom_template, render_standalone


EXE_SHELL_TEMPLATE = r'''# -*- coding: utf-8 -*-
"""CODEX 独立播放器壳：加载内嵌的打包 HTML（零后端依赖）"""
import base64
import os
import sys

# PyInstaller windowed 模式无控制台<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌：stdout/stderr 重定向到 exe 旁日志
if sys.stdout is None or sys.stderr is None:
    try:
        _log = open(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "codex_debug.log"),
                    "w", encoding="utf-8", errors="replace")
        if sys.stdout is None:
            sys.stdout = _log
        if sys.stderr is None:
            sys.stderr = _log
    except Exception:
        pass

_HTML_B64 = "__HTML_B64__"
_HTML = base64.b64decode(_HTML_B64).decode("utf-8")
_TITLE = "__TITLE__"

# webview 仅用于把生成脚本渲染成独立播放器窗口；测试/无头环境可能没有可用的
# GTK 后端或根本没装。做成可缺失导入，避免 module import 阶段硬失败（商业化质量：
# 测试服务器不该因为缺 GUI 工具链而整包红）。
try:
    import webview
except Exception:
    webview = None


class _Api:
    def exit(self):
        try:
            for w in webview.windows:
                w.destroy()
        except Exception:
            pass
        return True


def main():
    if webview is None:
        print("无法启动播放器：未安装可用的 webview（pywebview）后端")
        return
    api = _Api()
    window = webview.create_window(
        _TITLE, html=_HTML, js_api=api,
        width=1000, height=720, min_size=(720, 540),
        background_color="#0f1115")
    webview.start()


if __name__ == "__main__":
    main()
'''


def build_exe_shell(html, title="CODEX GALGAME"):
    """生成播放器壳脚本内容（HTML base64 内嵌）。"""
    import base64 as _b64
    b64 = _b64.b64encode(html.encode("utf-8")).decode("ascii")
    return EXE_SHELL_TEMPLATE.replace("__HTML_B64__", b64).replace("__TITLE__", title or "CODEX GALGAME")


def pyinstaller_cmd(shell_path, out_dir, name):
    """构造 PyInstaller 命令：单文件无控制台 EXE，输出到 out_dir/<name>.exe。
    返回 (cmd 列表, 说明)。"""
    hidden = [
        "webview", "webview.platforms.edgechromium", "webview.platforms.winforms",
        "clr_loader", "pythonnet", "urllib.parse",
    ]
    cmd = [
        "python", "-m", "PyInstaller",
        "--noconfirm", "--onefile", "--windowed",
        "--name", name,
        "--distpath", out_dir,
        "--workpath", os.path.join(out_dir, "_build"),
        "--specpath", os.path.join(out_dir, "_build"),
    ]
    for h in hidden:
        cmd += ["--hidden-import", h]
    cmd.append(shell_path)
    return cmd


def build_standalone_exe(pkg_dir, out_dir, name=None, py_cmd=None, log_cb=None,
                         mark=None):
    """完整打包 EXE 流程：生成 HTML → 写壳脚本 → 调 PyInstaller → 返回 EXE 路径。
    py_cmd: 覆盖 python 解释器（默认 sys.executable）；log_cb: 进度回调(str)。"""
    import subprocess
    import sys as _sys
    import shutil
    pkg_dir = os.path.abspath(pkg_dir)
    # 1) 生成单文件 HTML（支持自定义播放器模板）
    tpl = _load_custom_template(pkg_dir)
    html, counts = render_standalone(pkg_dir, tpl, mark=mark)
    with open(os.path.join(pkg_dir, "codex.json"), "r", encoding="utf-8") as f:
        script = json.load(f)
    title = str(script.get("name") or (name or "CODEX GALGAME"))
    safe = _safe_name(name or title or "CODEX-GALGAME")
    # 2) 写壳脚本到 out_dir/_build
    os.makedirs(out_dir, exist_ok=True)
    build_dir = os.path.join(out_dir, "_build")
    os.makedirs(build_dir, exist_ok=True)
    shell_path = os.path.join(build_dir, "codex_shell.py")
    with open(shell_path, "w", encoding="utf-8") as f:
        f.write(build_exe_shell(html, title))
    if log_cb:
        log_cb("壳脚本已生成，正在调用 PyInstaller…")
    # 3) PyInstaller
    if py_cmd is None:
        py_cmd = _sys.executable
    base_cmd = [py_cmd, "-m", "PyInstaller"] if py_cmd else ["python", "-m", "PyInstaller"]
    hidden = [
        "webview", "webview.platforms.edgechromium", "webview.platforms.winforms",
        "clr_loader", "pythonnet", "urllib.parse",
    ]
    cmd = base_cmd + [
        "--noconfirm", "--onefile", "--windowed",
        "--name", safe,
        "--distpath", out_dir,
        "--workpath", build_dir,
        "--specpath", build_dir,
    ]
    for h in hidden:
        cmd += ["--hidden-import", h]
    cmd.append(shell_path)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        tail = (r.stderr or "")[-1200:]
        raise RuntimeError("PyInstaller 失败:\n" + tail)
    exe = os.path.join(out_dir, safe + ".exe")
    if not os.path.isfile(exe):
        raise RuntimeError("打包完成但未找到 EXE: " + exe)
    return exe, counts
