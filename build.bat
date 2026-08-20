@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   DICK 便携版打包脚本（Python 3.14）
echo ============================================
echo.
python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo 未检测到 PyInstaller，正在安装...
    python -m pip install pyinstaller
)
python -m PyInstaller DICK.spec --noconfirm
if errorlevel 1 (
    echo.
    echo 打包失败，请检查上方错误信息
    pause
    exit /b 1
)
echo.
echo 打包完成！
echo   输出: dist\DICK\DICK.exe
echo   把整个 dist\DICK 文件夹拷贝到任意位置即可运行，
echo   存档/世界/插件/设置都会跟随 exe 所在目录。
echo.
pause
