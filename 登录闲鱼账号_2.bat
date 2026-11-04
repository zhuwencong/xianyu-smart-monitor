@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Xianyu Login Collector - acc_2

set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=

echo ================================================
echo   Account : acc_2  (second account)
echo   Step 1 : a browser window will open
echo   Step 2 : log in with the SECOND xianyu account
echo            (scan QR with the other phone / account)
echo   Step 3 : login state is saved automatically
echo ================================================
echo.
echo   IMPORTANT: make sure the phone you scan with is
echo   logged in to the SECOND account, not the first one.
echo.

".venv\Scripts\python.exe" login_xianyu.py acc_2

echo.
echo Done. Saved to state\acc_2.json
echo Refresh the Accounts page at http://127.0.0.1:8000
pause
