@echo off
chcp 65001 >nul
setlocal
rem ============================================================
rem  DICK 启动器（放在工程根目录 C:\Users\seiki\Desktop\dist 用）
rem  作用：让模型通道不走那个坏掉的系统代理 127.0.0.1:7890
rem ============================================================

set "NO_PROXY=api.deepseek.com,127.0.0.1,localhost,::1"
set "no_proxy=%NO_PROXY%"
cd /d "%~dp0"

echo [1/2] 启动本地创意工坊服务器 net.py ...
where python >nul 2>nul
if errorlevel 1 (
    echo       跳过：PATH 里没有 python
) else (
    if exist "net.py" (
        start "DICK 工坊" /min python net.py
    ) else (
        echo       跳过：没有 net.py
    )
)

echo [2/2] 启动主程序 ...
if exist "dist\DICK-HTML\DICK-HTML.exe" (
    start "" "dist\DICK-HTML\DICK-HTML.exe"
) else if exist "Direct-Interface Cork-bore Kit.py" (
    start "" pythonw "Direct-Interface Cork-bore Kit.py"
) else (
    echo       错误：没找到 DICK-HTML.exe 或主程序 .py
)

echo.
echo 已启动。若软件仍报网络错误，请检查 API Key 是否已填、Clash 节点是否可用。
timeout /t 6 >nul
REM <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌