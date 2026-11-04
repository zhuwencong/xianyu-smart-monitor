"""新版工作台 API：候选商品、监控任务、运行记录与管理摘要。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.dependencies import get_scheduler_service, get_task_service
from src.services.task_service import TaskService
from src.services.workbench_service import (
    build_summary,
    list_account_health,
    list_candidates,
    list_task_runs,
    list_task_workbench,
    update_candidate_review,
)


router = APIRouter(prefix="/api/workbench", tags=["workbench"])


class ReviewStatusRequest(BaseModel):
    review_status: str


@router.get("/summary")
async def get_workbench_summary(
    task_service: TaskService = Depends(get_task_service),
    scheduler_service=Depends(get_scheduler_service),
):
    tasks = await task_service.get_all_tasks()
    return await asyncio.to_thread(build_summary, tasks, scheduler_service)


@router.get("/candidates")
async def get_candidates(
    review_status: str = Query("all"),
    ai_verdict: str = Query("all"),
    task_id: int | None = Query(None),
    q: str = Query(""),
    sort: str = Query("smart"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=60),
    task_service: TaskService = Depends(get_task_service),
):
    if review_status not in {"all", "unseen", "favorite", "handled"}:
        raise HTTPException(status_code=400, detail="未知的人工处理状态")
    if ai_verdict not in {"all", "recommend", "verify", "mismatch", "failed"}:
        raise HTTPException(status_code=400, detail="未知的 AI 判断筛选")
    tasks = await task_service.get_all_tasks()
    return await asyncio.to_thread(
        list_candidates,
        tasks,
        review_status=review_status,
        ai_verdict=ai_verdict,
        task_id=task_id,
        query=q,
        sort=sort,
        page=page,
        limit=limit,
    )


@router.patch("/candidates/{item_id}")
async def patch_candidate_review(item_id: str, payload: ReviewStatusRequest):
    try:
        updated = await asyncio.to_thread(
            update_candidate_review, item_id, payload.review_status
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="商品未找到")
    return {"message": "处理状态已更新", "review_status": payload.review_status}


@router.get("/tasks")
async def get_workbench_tasks(
    task_service: TaskService = Depends(get_task_service),
    scheduler_service=Depends(get_scheduler_service),
):
    tasks = await task_service.get_all_tasks()
    return await asyncio.to_thread(list_task_workbench, tasks, scheduler_service)


@router.get("/tasks/{task_id}/runs")
async def get_task_runs(
    task_id: int,
    limit: int = Query(8, ge=1, le=20),
    task_service: TaskService = Depends(get_task_service),
):
    task = await task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")
    runs = await asyncio.to_thread(list_task_runs, task, limit=limit)
    return {"task_id": task.id, "task_name": task.task_name, "runs": runs}


@router.get("/accounts")
async def get_account_health():
    return {"items": await asyncio.to_thread(list_account_health)}


@router.get("/issues")
async def get_workbench_issues(
    task_service: TaskService = Depends(get_task_service),
    scheduler_service=Depends(get_scheduler_service),
):
    tasks = await task_service.get_all_tasks()
    summary = await asyncio.to_thread(build_summary, tasks, scheduler_service)
    return {"issues": summary["issues"], "pending_count": summary["pending_count"]}
