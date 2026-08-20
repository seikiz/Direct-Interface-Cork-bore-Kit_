# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('web', 'web'), ('plugins', 'plugins'), ('saves', 'saves'), ('worlds', 'worlds'), ('config.json', '.'),
         ('prompt_presets', 'prompt_presets'), ('personas', 'personas'), ('quick_replies.json', '.'),
         ('web_fetch.py', '.'), ('stock_analysis.py', '.'), ('doc_layout.py', '.'),
         ('i18n.py', '.'), ('app_paths.py', '.'), ('card_compat.py', '.'),
         ('PLUGIN_DEV.md', '.'), ('状态变量说明.md', '.'),
         ('financial_history.json', '.')]
binaries = []
hiddenimports = ['openai', 'customtkinter', 'PIL', 'requests', 'flask', 'openpyxl', 'docx', 'edge_tts', 'pygame',
                 'html.parser', 'html', 'urllib.parse', 'asyncio', 'random', 'importlib.util',
                 'webview', 'webview.platforms.edgechromium', 'webview.platforms.winforms',
                 'clr_loader', 'pythonnet', 'bottle',
                 'voice_engine', 'plugins.jp_patch_plugin']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:/Users/seiki/Desktop/dist/html_app.py'],
    pathex=[],
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
