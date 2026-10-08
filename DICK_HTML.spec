# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# 注意：这里【不要】再打包工程根的 config.json。
# 它是开发者本机的配置（含 welcome_shown，将来可能含 API Key）——被当"种子"烘进包后：
#   ① 下载者首启会跳过欢迎页与填 Key 引导（README 承诺的首启流程当场作废）；
#   ② 一旦本机 config.json 里填了 Key，Key 就会进公开发布包。
# 应用缺 config.json 是安全的：self.config 从 {} 起步、relay_url 另有 BUILTIN_RELAY 兜底。
datas = [('web', 'web'), ('plugins', 'plugins'), ('saves', 'saves'), ('worlds', 'worlds'),
         ('prompt_presets', 'prompt_presets'), ('personas', 'personas'), ('quick_replies.json', '.'),
         ('web_fetch.py', '.'), ('stock_analysis.py', '.'), ('doc_layout.py', '.'),
         ('i18n.py', '.'), ('app_paths.py', '.'), ('card_compat.py', '.'),
         # 插件 import 的根模块：PyInstaller 只分析入口脚本，插件是数据文件、
         # 它的 import 不会被跟进 → 这几个漏了就会让插件加载失败
         ('plugin_base.py', '.'), ('host_ui.py', '.'),
         # 函数内部才 import 的根模块（PyInstaller 静态分析看不到 → 打包版会 ImportError）：
         #   jobs.py       模块分道执行（入口/插件都用）
         #   mem_isolate.py 记忆隔离检测（记忆链插件用）
         ('jobs.py', '.'), ('mem_isolate.py', '.'),
         # 围棋规则引擎（主程序 import，显式列出更保险）
         ('go_engine.py', '.'),
         ('text_guard.py', '.'),
         # 树权重/剪枝：DICK_core 和主程序都是【函数内部】才 import，
         # PyInstaller 静态分析看不到 —— 漏了就是本地能打分、打包版报「缺少模块」。
         ('tree_weight.py', '.'),
         # 前瞻展开：主程序在函数内部 import
         ('lookahead.py', '.'),
         # 偏好导出：函数内部 import
         ('preference_export.py', '.'),
         # 价值声明 + 模型判定（便宜版 PRM）：函数内部 import
         ('rubric.py', '.'),
         # 记忆清晰度（有损遗忘）：_fit_budget 里在函数内部 import，
         # 漏了的后果是打包版【完全没有记忆筛选】，而且不报错、只是行为不同 ——
         # 这种静默差异最难查，所以必须显式列在这里。
         ('salience.py', '.'),
         # 软件时间流速（表盘）：DICK_core 的 _time_scale() 里懒加载，
         # 漏了的后果是打包版永远按 1 倍算，表盘怎么调都不生效。
         ('time_scale.py', '.'),
         # 平民化训练（纯 numpy 排序器）：函数内部 import
         ('ranker.py', '.'),
         # 加密备份：crypto_core 在函数内懒加载，PyInstaller 静态分析容易漏；
         # 漏了的后果是本地能备份、打包版直接报「缺少加密模块」。
         ('crypto_core.py', '.'),
         # 独立解密工具：备份能不能救回来不该依赖 DICK 本体，所以它必须随包发出去
         ('dick_backup_tool.py', '.'),
         ('PLUGIN_DEV.md', '.'), ('状态变量说明.md', '.'), ('声库安装说明.txt', '.'),
         ('financial_history.json', '.'),
         # 侧车脚本（独立 python 运行：创工坊/跑团主机），随包分发
         ('net.py', '.'), ('trpg_server.py', '.'), ('trpg_session.py', '.'),
         # 酒馆安装器（第一级目录，只带脚本，酒馆本体由 install.js 下载）
         ('tavern-installer/install.js', 'tavern-installer'), ('tavern-installer/install.bat', 'tavern-installer'),
         ('tavern-installer/start.bat.template', 'tavern-installer'), ('tavern-installer/package.json', 'tavern-installer'),
         ('tavern-installer/README.md', 'tavern-installer'),
          ('tavern-installer/bootstrap-node.ps1', 'tavern-installer')]
binaries = []
hiddenimports = ['openai', 'PIL', 'requests', 'flask', 'openpyxl', 'docx', 'edge_tts', 'pygame',
                 'html.parser', 'html', 'urllib.parse', 'asyncio', 'random', 'importlib.util',
                 'webview', 'webview.platforms.edgechromium', 'webview.platforms.winforms',
                 'clr_loader', 'pythonnet', 'bottle',
                 'voice_engine', 'plugins.jp_patch_plugin', 'voicebank_importer', 'image_gen',
                 # Tk 时代结束（2026-10）：插件要界面改走 host_ui（宿主的 pywebview 对话框/提示）。
                 # 原来这里显式声明 tkinter.* / customtkinter 是为了让三个 Tk 插件能在打包版里加载；
                 # 那三个插件（现代界面/图片上传/世界书编辑器）已连同 ui_root/ui_fonts 一起退役，
                 # 现在改成在 excludes 里【显式排除】Tcl/Tk —— 每次发布省 3.5 MB，也少一类窗口级故障。
                 # UTAU 进程内合成（用户无需安装 utau_env）
                 'putao', 'putao.core', 'putao.utau', 'putao.model', 'putao.exceptions', 'putao.utils',
                 'jaconv', 'mido', 'pykakasi', 'pypinyin', 'pydub', 'numpy', 'plugins.utau_speak',
                 # 加密备份（AES-256-GCM）。同样是在函数内部才 import，
                 # 而且 cryptography 的密码学实现是 Rust 编译的 _rust 扩展 ——
                 # 少收一个 .pyd 就是运行期 ImportError，必须显式声明 + collect_all。
                 'cryptography',
                 'cryptography.hazmat.primitives.ciphers.aead',
                 'cryptography.hazmat.primitives.kdf.pbkdf2',
                 'cryptography.hazmat.bindings._rust']

# UTAU 进程内合成：从 3.11 utau_env 收集 putao 及其依赖（numpy 等编译扩展必须走 binaries）
# 注意：customtkinter 已不再收集（随 Tk 插件一起退役）
import os as _os
_UTAU_SP = 'C:/Users/seiki/Desktop/dist/utau_env/Lib/site-packages'
if _os.path.isdir(_UTAU_SP):
    for _pkg in ('putao', 'numpy', 'pykakasi', 'pypinyin', 'pydub', 'jaconv', 'mido',
                 'cryptography'):
        try:
            _tmp = collect_all(_pkg)
            datas += _tmp[0]; binaries += _tmp[1]; hiddenimports += _tmp[2]
        except Exception:
            pass


a = Analysis(
    ['C:/Users/seiki/Desktop/dist/Direct-Interface Cork-bore Kit.py'],
    pathex=['C:/Users/seiki/Desktop/dist',
            'C:/Users/seiki/Desktop/dist/utau_env/Lib/site-packages'],  # putao 等从 3.11 utau_env 收集（3.14 无 wheel）
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 显式排除 Tcl/Tk：不排除的话，PyInstaller 会因为别处间接引用把
    # tcl86t.dll + tk86t.dll（3.5 MB）继续打进每次发布。
    excludes=['tkinter', '_tkinter', 'customtkinter', 'darkdetect', 'PIL.ImageTk', 'turtle',
              'turtledemo', 'idlelib', 'lib2to3'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DICK-HTML',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DICK-HTML',
)


