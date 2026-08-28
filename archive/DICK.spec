# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('plugins', 'plugins'), ('saves', 'saves'), ('worlds', 'worlds'), ('config.json', '.'),
         ('prompt_presets', 'prompt_presets'), ('personas', 'personas'),
         ('web_fetch.py', '.'), ('stock_analysis.py', '.'), ('workshop.py', '.'), ('doc_layout.py', '.'),
 ('financial_history.json', '.')]
binaries = []
hiddenimports = ['openai', 'customtkinter', 'PIL', 'requests', 'flask', 'openpyxl', 'docx', 'edge_tts', 'pygame',
                'html.parser', 'html', 'urllib.parse', 'asyncio', 'random', 'importlib.util',
                'voice_engine', 'plugins.jp_patch_plugin']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:/Users/seiki/Desktop/dist/Direct‑Interface Cork‑bore Kit.py'],
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
    name='DICK',
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
    name='DICK',
)
