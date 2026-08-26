@echo off
chcp 65001 >nul
title SillyTavern Installer (命令行自动安装 Node)
cd /d "%~dp0"

echo.
echo  ============================================
echo   SillyTavern Installer
echo   Standalone tool - card compatible with DICK
echo   Node 缺失时自动从命令行安装（Linux 式）
echo  ============================================
echo.

rem 准备一个可用 Node（>=18）：优先本地便携 → 系统 → 自动下载便携版
for /f "delims=" %%i in ('powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bootstrap-node.ps1"') do set "NODEBIN=%%i"

if "%NODEBIN%"=="" (
    echo.
    echo [ERR] Node 环境准备失败，请手动安装：https://nodejs.org/ 后重试
    pause
    exit /b 1
)

rem 若用生成的便携 Node 目录，则补进 PATH（生成 start.bat 时也用它）
if exist "%~dp0node\node.exe" set "PATH=%~dp0node;%PATH%"

rem use system CA (fixes GitHub certificate errors)
set NODE_OPTIONS=--use-system-ca

"%NODEBIN%" install.js %*

pause
