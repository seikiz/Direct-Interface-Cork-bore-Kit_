# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('web', 'web'), ('plugins', 'plugins'), ('saves', 'saves'), ('worlds', 'worlds'), ('config.json', '.'),
         ('prompt_presets', 'prompt_presets'), ('personas', 'personas'), ('quick_replies.json', '.'),
         ('web_fetch.py', '.'), ('stock_analysis.py', '.'), ('doc_layout.py', '.'),
         ('i18n.py', '.'), ('app_paths.py', '.'), ('card_compat.py', '.'),
         ('PLUGIN_DEV.md', '.'), ('状态变量说明.md', '.'), ('声库安装说明.txt', '.'),
         ('financial_history.json', '.'),
         # 酒馆安装器（第一级目录，只带脚本，酒馆本体由 install.js 下载）
         ('tavern-installer/install.js', 'tavern-installer'), ('tavern-installer/install.bat', 'tavern-installer'),
         ('tavern-installer/start.bat.template', 'tavern-installer'), ('tavern-installer/package.json', 'tavern-installer'),
         ('tavern-installer/README.md', 'tavern-installer')]
binaries = []
hiddenimports = ['openai', 'customtkinter', 'PIL', 'requests', 'flask', 'openpyxl', 'docx', 'edge_tts', 'pygame',
                 'html.parser', 'html', 'urllib.parse', 'asyncio', 'random', 'importlib.util',
                 'webview', 'webview.platforms.edgechromium', 'webview.platforms.winforms',
                 'clr_loader', 'pythonnet', 'bottle',
                 'voice_engine', 'plugins.jp_patch_plugin', 'voicebank_importer',
                 # UTAU 进程内合成（用户无需安装 utau_env）
                 'putao', 'putao.core', 'putao.utau', 'putao.model', 'putao.exceptions', 'putao.utils',
                 'jaconv', 'mido', 'pykakasi', 'pypinyin', 'pydub', 'numpy', 'plugins.utau_speak']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# UTAU 进程内合成：从 3.11 utau_env 收集 putao 及其依赖（numpy 等编译扩展必须走 binaries）
import os as _os
_UTAU_SP = 'C:/Users/seiki/Desktop/dist/utau_env/Lib/site-packages'
if _os.path.isdir(_UTAU_SP):
    for _pkg in ('putao', 'numpy', 'pykakasi', 'pypinyin', 'pydub', 'jaconv', 'mido'):
        try:
            _tmp = collect_all(_pkg)
            datas += _tmp[0]; binaries += _tmp[1]; hiddenimports += _tmp[2]
        except Exception:
            pass


a = Analysis(
    ['C:/Users/seiki/Desktop/dist/html_app.py'],
    pathex=['C:/Users/seiki/Desktop/dist',
            'C:/Users/seiki/Desktop/dist/utau_env/Lib/site-packages'],  # putao 等从 3.11 utau_env 收集（3.14 无 wheel）
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
