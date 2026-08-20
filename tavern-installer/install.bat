@echo off
chcp 65001 >nul
title SillyTavern Installer
cd /d "%~dp0"

echo.
echo  ============================================
echo   SillyTavern Installer
echo   Standalone tool - card compatible with DICK
echo  ============================================
echo.

where node >nul 2>nul
if errorlevel 1 (
    echo [ERR] Node.js not found. Install first:
    echo   winget install OpenJS.NodeJS
    echo   or https://nodejs.org/
    pause
    exit /b 1
)

rem use system CA (fixes GitHub certificate errors)
set NODE_OPTIONS=--use-system-ca

node install.js %*

pause
