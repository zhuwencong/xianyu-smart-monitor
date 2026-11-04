import asyncio
from contextlib import asynccontextmanager
import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.domain.models.task_outcome import ScrapeTaskError, TaskSkippedError


@pytest.mark.parametrize("close_also_fails", [False, True])
def test_unexpected_browser_close_is_failure_and_never_success(monkeypatch, tmp_path, close_also_fails):
    scraper = importlib.import_module("src.scraper")
    monkeypatch.chdir(tmp_path)
    state = tmp_path / "state.json"
    state.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    TargetClosedError = type("TargetClosedError", (Exception,), {})
    page = SimpleNamespace(goto=AsyncMock(side_effect=TargetClosedError("browser closed")))
    context = SimpleNamespace(add_init_script=AsyncMock(), new_page=AsyncMock(return_value=page))
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context), close=AsyncMock(
        side_effect=TargetClosedError("already closed") if close_also_fails else None))
    launch = AsyncMock(return_value=browser)

    @asynccontextmanager
    async def fake_playwright():
        yield SimpleNamespace(chromium=SimpleNamespace(launch=launch))

    guard = SimpleNamespace(
        should_skip_start=Mock(return_value=SimpleNamespace(skip=False)), record_success=Mock())
    notify = AsyncMock()
    monkeypatch.setattr(scraper, "FAILURE_GUARD", guard)
    monkeypatch.setattr(scraper, "load_price_snapshots", lambda _: [])
    monkeypatch.setattr(scraper, "load_processed_link_keys", lambda _: set())
    monkeypatch.setattr(scraper, "async_playwright", fake_playwright)
    monkeypatch.setattr(scraper, "prepare_chromium_launch_args", lambda: [])
    monkeypatch.setattr(scraper, "_notify_task_failure", notify)
    monkeypatch.setattr(scraper, "cleanup_task_images", Mock())
    monkeypatch.setattr(scraper.asyncio, "sleep", AsyncMock())
    with pytest.raises(ScrapeTaskError, match="浏览器意外关闭"):
        asyncio.run(scraper.scrape_xianyu({"keyword": "example", "task_name": "example",
            "account_strategy": "fixed", "account_state_file": str(state)}))
    guard.record_success.assert_not_called()
    notify.assert_awaited_once()
    launch.assert_awaited_once()


@pytest.mark.parametrize("outcome,expected,marker", [
    (ScrapeTaskError("test failure"), 1, "因异常而终止"),
    (TaskSkippedError("cooling"), 0, "已跳过"),
    (0, 0, "正常结束"),
])
def test_cli_preserves_failure_skip_and_empty_success(monkeypatch, tmp_path, capsys, outcome, expected, marker):
    cli = importlib.import_module("spider_v2")
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(json.dumps([{"task_name": "test", "keyword": "test", "enabled": True,
        "decision_mode": "keyword", "keyword_rules": ["test"]}]), encoding="utf-8")

    async def fake_scrape(**kwargs):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(cli, "STATE_FILE", str(state))
    monkeypatch.setattr(cli, "scrape_xianyu", fake_scrape)
    monkeypatch.setattr(cli.sys, "argv", ["spider_v2.py", "--config", str(config)])
    assert asyncio.run(cli.main()) == expected
    output = capsys.readouterr().out
    assert marker in output
    if isinstance(outcome, Exception):
        assert "正常结束" not in output
