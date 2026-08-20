@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   DICK-HTML（pywebview）打包脚本
echo   用 utau_env(3.11) 打包：putao/numpy 内嵌，用户零装 UTAU 环境
echo ============================================
echo.
"%~dp0utau_env\Scripts\python.exe" -m PyInstaller DICK_HTML.spec --noconfirm
if errorlevel 1 (
    echo.
    echo 打包失败，请检查上方错误信息
    pause
    exit /b 1
)
echo.
echo 后处理：把酒馆安装脚本/声库说明放到第一级目录（exe 同级）
set B=%~dp0dist\DICK-HTML
if exist "%B%\tavern-installer" rmdir /s /q "%B%\tavern-installer"
copy /y "%~dp0dist\DICK-HTML\_internal\tavern-installer" "%B%\tavern-installer" >nul 2>nul
if not exist "%B%\tavern-installer" xcopy /s /e /i /y "%~dp0dist\DICK-HTML\_internal\tavern-installer" "%B%\tavern-installer" >nul
if exist "%B%\_internal\声库安装说明.txt" copy /y "%B%\_internal\声库安装说明.txt" "%B%\声库安装说明.txt" >nul
echo.
echo 打包完成！
echo   输出: dist\DICK-HTML\DICK-HTML.exe
echo   第一级含: 酒馆安装器(tavern-installer/) + 声库安装说明.txt
echo   整个 dist\DICK-HTML 文件夹拷贝给任何人即可用（酒馆本体由脚本自动下载）
echo.
pause
