@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Xianyu Login Collector - acc_4

set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=

echo ================================================
echo   Account : acc_4
echo   Step 1 : a browser window will open
echo   Step 2 : scan QR with the account No.4
echo   Step 3 : login state is saved automatically
echo ================================================
echo.
".venv\Scripts\python.exe" login_xianyu.py acc_4

echo.
echo Done. Saved to state\acc_4.json
pause