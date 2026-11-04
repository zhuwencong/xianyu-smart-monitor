"""任务运行记录的持久化服务。

每次爬虫子进程启动时写一条 running 记录，退出时根据退出码和本轮新增结果
补齐状态、数量与结束时间。它只依赖 SQLite，供 API 与 ProcessService 共用。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.infrastructure.persistence.storage_names import build_result_filename
from src.utils import build_task_log_path


TERMINAL_STATUSES = {"completed", "partial", "failed", "no_new", "stopped"}
STATUS_LABELS = {
    "running": "运行中",
    "completed": "已完成",
    "partial": "部分完成",
    "failed": "异常退出",
    "no_new": "无新增",
    "stopped": "已停止",
}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _row_to_dict(row) -> dict[str, Any]:
    payload = dict(row)
    payload["status_label"] = STATUS_LABELS.get(payload.get("status", ""), "未知")
    payload["duration_seconds"] = _duration_seconds(
        payload.get("started_at"), payload.get("finished_at")
    )
    return payload


def _duration_seconds(started_at: str | None, finished_at: str | None) -> int | None:
    if not started_at or not finished_at:
        return None
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    return max(0, int((end - start).total_seconds()))


class TaskRunService:
    def start_run(
        self,
        *,
        task_id: int | None,
        task_name: str,
        keyword: str | None = None,
        trigger: str = "manual",
        log_path: str | None = None,
    ) -> int:
        if not task_id or int(task_id) <= 0:
            return 0
        bootstrap_sqlite_storage()
        started_at = _now_iso()
        resolved_log_path = log_path or build_task_log_path(int(task_id or 0), task_name)
        with sqlite_connection() as conn:
            # 同一个任务只允许一个活动运行，历史残留先收口，避免 UI 同时出现两个“运行中”。
            conn.execute(
                """
                UPDATE task_runs
                SET status = 'failed', finished_at = ?, error_message = ?
                WHERE task_id = ? AND status = 'running'
                """,
                (started_at, "运行记录被新的启动覆盖，上一轮状态未知。", task_id),
            )
            cursor = conn.execute(
                """
                INSERT INTO task_runs (
                    task_id, task_name, keyword, trigger, status, started_at, log_path
                ) VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (task_id, task_name, keyword, trigger, started_at, resolved_log_path),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int | None,
        *,
        exit_code: int | None = None,
        stopped: bool = False,
        error_message: str | None = None,
        saved_count: int | None = None,
    ) -> dict[str, Any] | None:
        if not run_id:
            return None
        bootstrap_sqlite_storage()
        finished_at = _now_iso()
        with sqlite_connection() as conn:
            row = conn.execute(
                "SELECT * FROM task_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return None
            if row["status"] in TERMINAL_STATUSES:
                return _row_to_dict(row)

            counted = self._count_saved_results(
                conn,
                task_name=str(row["task_name"] or ""),
                keyword=row["keyword"],
                started_at=str(row["started_at"] or ""),
                finished_at=finished_at,
            )
            effective_saved = counted if saved_count is None else max(0, int(saved_count))
            if stopped:
                status = "stopped"
                summary = "任务被手动停止，已保存的结果会保留。"
            elif exit_code == 0 and effective_saved > 0:
                status = "completed"
                summary = f"本轮已完成，新增 {effective_saved} 条结果。"
            elif exit_code == 0:
                status = "no_new"
                summary = "本轮正常结束，未发现新的候选商品。"
            elif effective_saved > 0:
                status = "partial"
                summary = "本轮未完整结束，已有结果已保留。"
            else:
                status = "failed"
                summary = "本轮异常退出，未保存新的候选商品。"

            pending_count = 0 if status in {"completed", "no_new"} else max(effective_saved, 0)
            conn.execute(
                """
                UPDATE task_runs
                SET status = ?, finished_at = ?, exit_code = ?, saved_count = ?,
                    discovered_count = ?, pending_count = ?, error_message = ?, summary = ?
                WHERE id = ?
                """,
                (
                    status,
                    finished_at,
                    exit_code,
                    effective_saved,
                    effective_saved,
                    pending_count,
                    error_message,
                    summary,
                    run_id,
                ),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM task_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return _row_to_dict(updated) if updated else None

    def _count_saved_results(
        self,
        conn,
        *,
        task_name: str,
        keyword: str | None,
        started_at: str,
        finished_at: str,
    ) -> int:
        if not started_at:
            return 0
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM result_items
            WHERE TRIM(task_name) = TRIM(?)
              AND crawl_time >= ? AND crawl_time <= ?
            """,
            (task_name, started_at, finished_at),
        ).fetchone()
        count = int(row["n"] if row else 0)
        if count:
            return count
        if keyword:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM result_items
                WHERE result_filename = ? AND crawl_time >= ? AND crawl_time <= ?
                """,
                (build_result_filename(keyword), started_at, finished_at),
            ).fetchone()
            count = int(row["n"] if row else 0)
        return count

    def list_runs(self, task_id: int, limit: int = 8) -> list[dict[str, Any]]:
        bootstrap_sqlite_storage()
        with sqlite_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM task_runs
                WHERE task_id = ?
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (task_id, max(1, min(limit, 50))),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def latest_run(self, task_id: int) -> dict[str, Any] | None:
        runs = self.list_runs(task_id, limit=1)
        return runs[0] if runs else None

    def mark_stale_runs(self) -> int:
        """服务启动时把上次进程崩溃留下的 running 记录标记为异常退出。"""
        bootstrap_sqlite_storage()
        with sqlite_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE task_runs
                SET status = 'failed', finished_at = ?,
                    error_message = '服务重启，上一轮运行未正常收尾。',
                    summary = '服务重启，上一轮运行未正常收尾。'
                WHERE status = 'running'
                """,
                (_now_iso(),),
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    def log_path_for_run(self, run_id: int) -> str | None:
        bootstrap_sqlite_storage()
        with sqlite_connection() as conn:
            row = conn.execute(
                "SELECT log_path FROM task_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if not row:
            return None
        path = row["log_path"]
        return str(path) if path and os.path.exists(path) else None
