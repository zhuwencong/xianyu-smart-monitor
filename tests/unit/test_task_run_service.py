"""task_id=0 是合法任务 ID，运行记录必须能正常落库。

历史 bug：start_run 用 `if not task_id` 判断，把 id=0 的首个任务当成非法值直接
返回 0，导致该任务的 task_runs 永远是空的（前端只能靠解析日志文件兜底）。
"""
import pytest

from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.services.task_run_service import TaskRunService


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "app.sqlite3"
    monkeypatch.setattr(
        "src.infrastructure.persistence.sqlite_connection.get_database_path",
        lambda: str(path),
    )
    monkeypatch.setattr(
        "src.infrastructure.persistence.sqlite_bootstrap.LEGACY_CONFIG_FILE", None
    )
    bootstrap_sqlite_storage(str(path), legacy_config_file=None)
    return str(path)


def test_start_run_accepts_task_id_zero(db_path):
    """id=0 的任务必须能写入运行记录。"""
    service = TaskRunService()

    run_id = service.start_run(
        task_id=0,
        task_name="OPPO Find X8 Ultra 16+512",
        keyword="OPPO Find X8 Ultra 512",
        trigger="scheduled",
        log_path="logs/demo_0.log",
    )

    assert run_id > 0, "task_id=0 的运行记录没有被创建"

    runs = service.list_runs(0)
    assert len(runs) == 1
    assert runs[0]["task_id"] == 0
    assert runs[0]["status"] == "running"
    assert runs[0]["task_name"] == "OPPO Find X8 Ultra 16+512"


def test_finish_run_closes_id_zero_record(db_path):
    """id=0 的记录同样要能被正常收尾。"""
    service = TaskRunService()
    run_id = service.start_run(task_id=0, task_name="任务零", keyword="kw")

    finished = service.finish_run(run_id, exit_code=0, saved_count=3)

    assert finished is not None
    assert finished["status"] == "completed"
    assert finished["saved_count"] == 3
    assert finished["finished_at"]


def test_start_run_rejects_invalid_task_id(db_path):
    """None / 负数仍应被视为非法，返回 0 不落库。"""
    service = TaskRunService()

    assert service.start_run(task_id=None, task_name="无 id") == 0
    assert service.start_run(task_id=-1, task_name="负数 id") == 0

    with sqlite_connection(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM task_runs").fetchone()["n"]
    assert total == 0
