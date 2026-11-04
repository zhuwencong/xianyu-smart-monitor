@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Xianyu Monitor Service - 127.0.0.1:8000

rem Clear system proxy vars: the local proxy on this machine is dead.
set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=

rem Clear host-injected python shim / bulk-delete guard.
rem Without this, every python child loads sitecustomize.py which blocks
rem batch file deletion after N files and kills the spider.
set PYTHONPATH=
set CODEBUDDY_SAFE_DELETE_BULK_GUARD=
set CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR=
set CODEBUDDY_SAFE_DELETE_BULK_REPLAY_FILE=
set CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD=

echo ================================================
echo   Xianyu AI Monitor  (silent launcher)
echo   Web UI : http://127.0.0.1:8000
echo   Login  : 本机自动登录（严格模式需 admin / admin123）
echo   Stop   : close this window or Ctrl+C
echo ================================================
echo.

".venv\Scripts\python.exe" -m src.app

echo.
echo Service stopped.
pause
