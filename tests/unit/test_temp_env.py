import os
import tempfile
import time
from pathlib import Path

import src.core.temp_env as temp_env
from src.core.temp_env import ensure_writable_temp_dir


def test_keeps_writable_temp_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    assert ensure_writable_temp_dir(str(tmp_path / "project")) == str(tmp_path)


def test_falls_back_to_project_tmp_when_temp_is_unusable(tmp_path, monkeypatch):
    # 把一个普通文件当作「目录」的父级，mkdir 必然失败，模拟不可写的 TEMP
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    broken = str(blocker / "sub")
    monkeypatch.setenv("TEMP", broken)
    monkeypatch.setenv("TMP", broken)
    monkeypatch.setattr(tempfile, "tempdir", None)
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    resolved = ensure_writable_temp_dir(str(project_dir))

    assert resolved == str(project_dir / ".tmp")
    assert Path(resolved).is_dir()
    assert os.environ["TEMP"] == resolved
    assert tempfile.tempdir == resolved
    # 新目录必须真的能建临时文件
    handle, name = tempfile.mkstemp(dir=resolved)
    os.close(handle)
    os.remove(name)


def test_probe_timeout_falls_back_instead_of_hanging(tmp_path, monkeypatch):
    """被拦截的目录可能让写入无限挂起，探测必须按时放弃并退回 .tmp。"""

    def _hang(_path):
        time.sleep(5)
        return True

    monkeypatch.setenv("TEMP", str(tmp_path / "slow"))
    monkeypatch.setenv("TMP", str(tmp_path / "slow"))
    monkeypatch.setattr(temp_env, "_probe_once", _hang)

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    started = time.time()
    resolved = ensure_writable_temp_dir(str(project_dir), timeout=0.15)
    elapsed = time.time() - started

    assert elapsed < 1.5, f"探测没有按时放弃，耗时 {elapsed:.2f}s"
    assert resolved == str(project_dir / ".tmp")
    assert Path(resolved).is_dir()
