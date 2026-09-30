@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   DICK-HTML (pywebview) build script
echo   Uses utau_env(3.11): putao/numpy embedded, zero UTAU install
echo ============================================
echo.
"%~dp0utau_env\Scripts\python.exe" -m PyInstaller DICK_HTML.spec --noconfirm
if errorlevel 1 (
    echo.
    echo BUILD FAILED - check errors above
    pause
    exit /b 1
)
echo.
echo Post-process: move tavern-installer / voice guide to top level
set B=%~dp0dist\DICK-HTML
if exist "%B%\tavern-installer" rmdir /s /q "%B%\tavern-installer"
copy /y "%~dp0dist\DICK-HTML\_internal\tavern-installer" "%B%\tavern-installer" >nul 2>nul
if not exist "%B%\tavern-installer" xcopy /s /e /i /y "%~dp0dist\DICK-HTML\_internal\tavern-installer" "%B%\tavern-installer" >nul
if exist "%B%\_internal\voice_guide.txt" copy /y "%B%\_internal\voice_guide.txt" "%B%\voice_guide.txt" >nul
REM start.bat generated from template (install.j<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌s overwrites with actual version at runtime)
if exist "%B%\tavern-installer\start.bat.template" copy /y "%B%\tavern-installer\start.bat.template" "%B%\tavern-installer\start.bat" >nul
echo.
echo BUILD COMPLETE
echo   Output: dist\DICK-HTML\DICK-HTML.exe
echo   Top level: tavern-installer/ + voice guide
echo   Copy dist\DICK-HTML to anyone (tavern body auto-downloaded by script)
echo.
pause
