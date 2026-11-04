@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Xianyu Login Collector

set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=

echo ================================================
echo   Step 1 : a browser window will open
echo   Step 2 : log in to goofish.com (scan QR with app)
echo   Step 3 : login state is saved automatically
echo ================================================
echo.

".venv\Scripts\python.exe" login_xianyu.py acc_1

echo.
echo Done. You can now refresh the Accounts page at http://127.0.0.1:8000
pause
