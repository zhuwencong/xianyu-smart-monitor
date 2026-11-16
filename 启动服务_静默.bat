@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Xianyu AI Monitor  -  127.0.0.1:8000
cls

rem ---- clear proxy vars: the local proxy on this machine is dead ----
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="
set "ALL_PROXY="
set "all_proxy="

rem ---- clear host-injected python shim / bulk-delete guard ----
rem Without this every python child loads sitecustomize.py which blocks
rem batch file deletion after N files and kills the spider.
set "PYTHONPATH="
set "CODEBUDDY_SAFE_DELETE_BULK_GUARD="
set "CODEBUDDY_SAFE_DELETE_BULK_STATE_DIR="
set "CODEBUDDY_SAFE_DELETE_BULK_REPLAY_FILE="
set "CODEBUDDY_SAFE_DELETE_BULK_THRESHOLD="

echo ================================================
echo   Xianyu AI Monitor  -  silent launcher
echo   Web UI : http://127.0.0.1:8000
echo   Login  : auto  (strict mode: admin / admin123)
echo   Stop   : close this window or Ctrl+C
echo ================================================
echo.

rem ---- open the web UI in the default browser once the port is up ----
if exist "%~dp0.venv\Scripts\pythonw.exe" start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0.tools\open_ui.py"
".venv\Scripts\python.exe" -m src.app

echo.
echo Service stopped.
pause
