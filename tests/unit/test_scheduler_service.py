import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.services.scheduler_service import SchedulerService


def test_reload_preserves_system_jobs_and_removes_disabled_tasks():
    service = SchedulerService(SimpleNamespace(start_task=AsyncMock()))
    system = {}
    for name in ("daily_report", "zombie_task_sweeper", "task_cleanup"):
        system[name] = service.scheduler.add_job(lambda: None, "interval", hours=1, id=name)
    service.scheduler.add_job(lambda: None, "interval", hours=1, id="task_8")
    task = SimpleNamespace(id=1, task_name="example", enabled=True, cron="0 */6 * * *")
    asyncio.run(service.reload_jobs([task]))
    assert {job.id for job in service.scheduler.get_jobs()} == set(system) | {"task_1"}
    for name, original in system.items():
        assert service.scheduler.get_job(name) is original
    task.enabled = False
    asyncio.run(service.reload_jobs([task]))
    assert {job.id for job in service.scheduler.get_jobs()} == set(system)


def test_repeated_reload_updates_schedule_without_duplicates():
    service = SchedulerService(SimpleNamespace(start_task=AsyncMock()))
    task = SimpleNamespace(id=2, task_name="example", enabled=True, cron="20 */6 * * *")
    asyncio.run(service.reload_jobs([task]))
    task.cron = "7 */2 * * *"
    asyncio.run(service.reload_jobs([task]))
    assert [job.id for job in service.scheduler.get_jobs()] == ["task_2"]
    assert service.scheduler.get_job("task_2").trigger.fields[-2].__str__() == "7"
