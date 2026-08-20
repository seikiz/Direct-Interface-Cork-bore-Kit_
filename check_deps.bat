@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   utau_env(3.11) 打包依赖检查
echo ============================================
"%~dp0utau_env\Scripts\python.exe" -X utf8 -c "import sys; mods=['openai','requests','flask','bottle','webview','customtkinter','PIL','openpyxl','docx','edge_tts','pygame','putao','numpy','pykakasi','pypinyin','pydub','jaconv','mido','voice_engine','voicebank_importer']; import importlib.util as u; missing=[m for m in mods if u.find_spec(m) is None and m not in ('voice_engine','voicebank_importer')]; print('MISSING:', missing if missing else 'none')"
echo.
echo 若显示 MISSING 有包，先安装：
echo   utau_env\Scripts\python.exe -m pip install ^<包名^>
pause
