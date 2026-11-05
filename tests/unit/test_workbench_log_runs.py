import src.services.workbench_service as workbench_service


def _write_log(tmp_path, lines: list[str]):
    log_path = tmp_path / "task_1.log"
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path


def test_runtime_failure_exposes_real_error(tmp_path, monkeypatch):
    """浏览器起不来这类失败，运行记录要给出真实原因，而不是「找不到结束标记」。"""
    log_path = _write_log(
        tmp_path,
        [
            "--- 开始执行监控任务 ---",
            "账号轮换：使用登录状态 state\\acc_2.json",
            "[ 2026-11-05 13:12:42] [预筛] 已启用标题过滤：必含 ['1070']",
            "[ 2026-11-05 13:12:43] 本次尝试失败: Error: BrowserType.launch: EPERM: operation not permitted",
            "[ 2026-11-05 13:12:43] 任务 'GTX 1070' 因异常而终止: Error: BrowserType.launch: EPERM",
        ],
    )
    monkeypatch.setattr(
        workbench_service, "resolve_task_log_path", lambda task_id, task_name: str(log_path)
    )

    runs = workbench_service._parse_log_runs(1, "GTX 1070")

    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "failed"
    assert "BrowserType.launch" in run["error_message"]
    assert "结束标记" not in run["error_message"]


def test_login_failure_still_reported_as_login(tmp_path, monkeypatch):
    log_path = _write_log(
        tmp_path,
        [
            "--- 开始执行监控任务 ---",
            "账号轮换：使用登录状态 state\\acc_1.json",
            "[ 2026-11-05 13:12:41] 检测到登录失效/重定向: Login required",
        ],
    )
    monkeypatch.setattr(
        workbench_service, "resolve_task_log_path", lambda task_id, task_name: str(log_path)
    )

    runs = workbench_service._parse_log_runs(1, "GTX 1070")

    assert runs[0]["status"] == "failed"
    assert "登录态失效" in runs[0]["error_message"]


def test_normal_run_is_completed(tmp_path, monkeypatch):
    log_path = _write_log(
        tmp_path,
        [
            "--- 开始执行监控任务 ---",
            "账号轮换：使用登录状态 state\\acc_1.json",
            "[ 2026-11-05 13:12:41] 本次运行共处理了 3 个新商品",
            "[ 2026-11-05 13:18:41] 任务正常结束",
        ],
    )
    monkeypatch.setattr(
        workbench_service, "resolve_task_log_path", lambda task_id, task_name: str(log_path)
    )

    runs = workbench_service._parse_log_runs(1, "GTX 1070")

    assert runs[0]["status"] == "completed"
    assert runs[0]["saved_count"] == 3
    assert not runs[0]["error_message"]
