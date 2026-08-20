@echo off
chcp 65001 >nul
title SillyTavern 酒馆一键安装器
cd /d "%~dp0"

echo.
echo  ============================================
echo   SillyTavern（酒馆）一键安装器
echo   与 DICK 分离的独立工具 - 卡互通友军
echo  ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装:
    echo   winget install OpenJS.NodeJS
    echo   或 https://nodejs.org/
    pause
    exit /b 1
)

node install.js %*

pause
