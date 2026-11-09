"""
新架构的主应用入口
整合所有路由和服务
"""
# 必须放在其它 src 模块之前：AI 客户端 / httpx 在 import 阶段就会读代理环境变量，
# 一旦继承了失效的 HTTP_PROXY，之后整进程的 AI 调用都是 Connection error。
from src.core.proxy_env import strip_inherited_proxy_env

strip_inherited_proxy_env(label="服务启动")

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api.routes import (
    dashboard,
    tasks,
    logs,
    settings,
    prompts,
    results,
    login_state,
    websocket,
    accounts,
    workbench,
)
from src.api.dependencies import (
    set_process_service,
    set_scheduler_service,
    set_task_generation_service,
)
from src.services.task_service import TaskService
from src.services.process_service import ProcessService
from src.services.scheduler_service import SchedulerService
from src.services.task_log_cleanup_service import cleanup_task_logs
from src.services.task_run_service import TaskRunService
from src.services.task_generation_service import TaskGenerationService
from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_task_repository import SqliteTaskRepository
from src.infrastructure.config.settings import settings as app_settings
from src.core.temp_env import ensure_writable_temp_dir
from src.api.web_auth import install_web_auth, validate_web_binding


# 项目根目录（只在启动时用，不能在这里做文件系统探测：import 副作用会让测试
# 收集和嵌入式调用一起变慢，甚至被挂死的 TEMP 拖住）。
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 全局服务实例
process_service = ProcessService()
scheduler_service = SchedulerService(process_service)
task_generation_service = TaskGenerationService()


async def _sync_task_runtime_status(task_id: int, is_running: bool) -> None:
    task_service = TaskService(SqliteTaskRepository())
    task = await task_service.get_task(task_id)
    if not task or task.is_running == is_running:
        return
    await task_service.update_task_status(task_id, is_running)
    await websocket.broadcast_message(
        "task_status_changed",
        {"id": task_id, "is_running": is_running},
    )


async def _sweep_zombie_tasks() -> None:
    """僵死任务自愈巡检。

    实践中多次出现 spider 进程已退出但 DB 里 is_running 仍为 True 的情况：
    状态显示"运行中"永远不结束，手动点开始会被"任务已在运行中"拒绝，
    看板统计也失真。每分钟对账一次：DB 说是运行中、但进程表里没有活进程
    的任务，直接复位为停止。
    """
    try:
        task_service = TaskService(SqliteTaskRepository())
        tasks_list = await task_service.get_all_tasks()
        for task in tasks_list:
            if task.is_running and not process_service.is_running(task.id):
                print(
                    f"[自愈] 任务 '{task.task_name}' (ID:{task.id}) 标记为运行中"
                    "但进程已不存在，复位 is_running。"
                )
                await task_service.update_task_status(task.id, False)
                await websocket.broadcast_message(
                    "task_status_changed",
                    {"id": task.id, "is_running": False},
                )
    except Exception as exc:
        print(f"[自愈] 僵死任务巡检出错（不影响服务）: {exc}")


async def _run_daily_report() -> None:
    """定时推送监控日报。"""
    try:
        from src.services.daily_report_service import send_daily_report

        await send_daily_report()
    except Exception as exc:
        print(f"[日报] 执行失败（不影响服务）: {exc}")


process_service.set_lifecycle_hooks(
    on_started=lambda task_id: _sync_task_runtime_status(task_id, True),
    on_stopped=lambda task_id: _sync_task_runtime_status(task_id, False),
)

# 设置全局 ProcessService 实例供依赖注入使用
set_process_service(process_service)
set_scheduler_service(scheduler_service)
set_task_generation_service(task_generation_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 服务与它派生的爬虫子进程共用同一份环境：临时目录不可写会让 Playwright 直接 EPERM。
    # 放在启动阶段而不是 import 阶段，探测超时也只会拖慢启动，不会卡住测试收集。
    ensure_writable_temp_dir(_PROJECT_DIR)
    validate_web_binding(app_settings)
    # 启动时
    print("正在启动应用...")
    bootstrap_sqlite_storage()
    stale_runs = TaskRunService().mark_stale_runs()
    if stale_runs:
        print(f"已收口 {stale_runs} 条异常中断的运行记录")
    cleanup_task_logs(keep_days=app_settings.task_log_retention_days)

    # 重置所有任务状态为停止
    task_repo = SqliteTaskRepository()
    task_service = TaskService(task_repo)
    tasks_list = await task_service.get_all_tasks()

    for task in tasks_list:
        if task.is_running:
            await task_service.update_task_status(task.id, False)

    # 加载定时任务
    await scheduler_service.reload_jobs(tasks_list)
    scheduler_service.start()

    # 僵死任务自愈巡检：每分钟对账一次 is_running 与真实进程
    scheduler_service.scheduler.add_job(
        _sweep_zombie_tasks,
        "interval",
        seconds=60,
        id="zombie_task_sweeper",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    print("僵死任务自愈巡检已启动（每 60 秒一次）")

    # 每日监控日报（PushPlus 等渠道）+ Excel 自动导出
    try:
        from src.services.daily_report_service import (
            daily_report_hour,
            is_daily_report_enabled,
        )

        if is_daily_report_enabled():
            scheduler_service.scheduler.add_job(
                _run_daily_report,
                "cron",
                hour=daily_report_hour(),
                minute=5,
                id="daily_report",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            print(f"每日监控日报已排程（每天 {daily_report_hour()}:05）")
    except Exception as exc:
        print(f"日报任务排程失败（不影响服务）: {exc}")

    print("应用启动完成")

    yield

    # 关闭时
    print("正在关闭应用...")
    scheduler_service.stop()
    await process_service.stop_all()
    print("应用已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="闲鱼智能监控机器人",
    description="基于AI的闲鱼商品监控系统",
    version="2.0.0",
    lifespan=lifespan
)
web_auth = install_web_auth(app, lambda: app_settings)

# 注册路由
app.include_router(tasks.router)
app.include_router(dashboard.router)
app.include_router(logs.router)
app.include_router(settings.router)
app.include_router(prompts.router)
app.include_router(results.router)
app.include_router(login_state.router)
app.include_router(websocket.router)
app.include_router(accounts.router)
app.include_router(workbench.router)

# 挂载静态文件
# 旧的静态文件目录（用于截图等）
app.mount("/static", StaticFiles(directory="static"), name="static")

# 挂载 Vue 3 前端构建产物
# 注意：需要在所有 API 路由之后挂载，以避免覆盖 API 路由
import os
if os.path.exists("dist"):
    app.mount("/assets", StaticFiles(directory="dist/assets"), name="assets")


# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查（无需认证）"""
    return {"status": "healthy", "message": "服务正常运行"}


# 页面请求类型
from fastapi import Request
from fastapi.responses import FileResponse


# 主页路由 - 服务 Vue 3 SPA
from fastapi.responses import JSONResponse

@app.get("/")
async def read_root(request: Request):
    """提供 Vue 3 SPA 的主页面"""
    if os.path.exists("dist/index.html"):
        return FileResponse("dist/index.html")
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "前端构建产物不存在，请先运行 cd web-ui && npm run build"}
        )


@app.get("/favicon.png")
@app.get("/favicon.ico")
async def serve_favicon():
    favicon_path = "dist/favicon.png"
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/png")
    return Response(status_code=204)


# Catch-all 路由 - 处理所有前端路由（必须放在最后）
@app.get("/{full_path:path}")
async def serve_spa(request: Request, full_path: str):
    """
    Catch-all 路由，将所有非 API 请求重定向到 index.html
    这样可以支持 Vue Router 的 HTML5 History 模式
    """
    # 如果请求的是静态资源（如 favicon.ico），返回 404
    if full_path.endswith(('.ico', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.css', '.js', '.json')):
        return JSONResponse(status_code=404, content={"error": "资源未找到"})

    # 其他所有路径都返回 index.html，让前端路由处理
    if os.path.exists("dist/index.html"):
        return FileResponse("dist/index.html")
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "前端构建产物不存在，请先运行 cd web-ui && npm run build"}
        )


if __name__ == "__main__":
    import uvicorn
    from src.infrastructure.config.settings import settings

    print(f"启动新架构应用，端口: {app_settings.server_port}")
    validate_web_binding(app_settings)
    uvicorn.run(app, host=app_settings.server_host, port=app_settings.server_port)
