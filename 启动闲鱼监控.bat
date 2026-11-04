@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Xianyu AI Monitor  -  http://127.0.0.1:8000

rem Clear system proxy vars: the local proxy on this machine is dead and would
rem break AI requests / pip. The app only uses PROXY_URL from .env.
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=

echo ================================================
echo   Xianyu AI Monitor
echo   Web UI : http://127.0.0.1:8000
echo   Login  : admin / admin123
echo   Stop   : close this window or press Ctrl+C
echo ================================================
echo.

start "" http://127.0.0.1:8000

".venv\Scripts\python.exe" -m src.app

echo.
echo Service stopped.
pause
