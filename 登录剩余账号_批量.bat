@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Xianyu Batch Login (acc_3 -> acc_6)

set HTTP_PROXY=
set HTTPS_PROXY=
set http_proxy=
set https_proxy=
set ALL_PROXY=
set all_proxy=

echo ============================================================
echo   Batch login: acc_3, acc_4, acc_5, acc_6
echo ------------------------------------------------------------
echo   For each account a browser window opens.
echo   Scan the QR code with the xianyu App logged in as THAT account.
echo   After saving, the window closes and the next one opens.
echo ------------------------------------------------------------
echo   Close the browser window at any time to abort the batch.
echo ============================================================
echo.
pause

for %%a in (acc_3 acc_4 acc_5 acc_6) do (
  echo.
  echo ################  NOW LOGGING IN: %%a  ################
  echo.
  ".venv\Scripts\python.exe" login_xianyu.py %%a
  if errorlevel 1 (
    echo.
    echo [STOP] %%a failed or aborted. Batch stopped.
    echo        Fix the problem, then run this bat again.
    pause
    exit /b 1
  )
)

echo.
echo ============================================================
echo   ALL DONE. Saved accounts:
dir /b state\acc_*.json
echo ============================================================
pause