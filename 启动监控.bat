@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM 清理宿主环境注入的环回代理（如 127.0.0.1:<随机端口>）。
REM 该端口随宿主会话变化，常驻服务继承后会失效，
REM 导致 AI 调用报 Connection error、Playwright 报 ERR_CONNECTION_CLOSED。
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "http_proxy="
set "https_proxy="
set "all_proxy="
set PYTHONUNBUFFERED=1

echo ========================================
echo   闲鱼智能监控 - 启动服务
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 .venv
    echo 请先执行: python -m venv .venv
    pause
    exit /b 1
)

if not exist ".env" (
    echo [提示] 未找到 .env，正在从 .env.example 复制...
    copy ".env.example" ".env" >nul
    echo [提示] 请编辑 .env 填写 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL_NAME
)

if not exist "dist\index.html" (
    echo [提示] 前端产物缺失，正在构建...
    pushd web-ui
    call npm install
    call npm run build
    popd
)

echo 服务地址: http://127.0.0.1:8000
echo 接口文档: http://127.0.0.1:8000/docs
echo 按 Ctrl+C 停止服务
echo.

".venv\Scripts\python.exe" -u -m src.app

pause
