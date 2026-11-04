from src.domain.models.task import Task, TaskGenerateRequest, TaskUpdate


def test_task_can_start_and_stop():
    task = Task(
        id=1,
        task_name="Sony A7M4",
        enabled=True,
        keyword="sony a7m4",
        description="body",
        max_pages=2,
        personal_only=True,
        min_price=None,
        max_price=None,
        cron=None,
        ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="prompts/sony_a7m4_criteria.txt",
        is_running=False,
    )

    assert task.can_start() is True
    assert task.can_stop() is False

    running = task.model_copy(update={"is_running": True})
    assert running.can_start() is False
    assert running.can_stop() is True


def test_task_apply_update():
    task = Task(
        id=1,
        task_name="Sony A7M4",
        enabled=True,
        keyword="sony a7m4",
        description="body",
        max_pages=2,
        personal_only=True,
        min_price=None,
        max_price=None,
        cron=None,
        ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="prompts/sony_a7m4_criteria.txt",
        is_running=False,
    )

    update = TaskUpdate(enabled=False, max_pages=5)
    updated = task.apply_update(update)

    assert updated.enabled is False
    assert updated.max_pages == 5
    assert updated.task_name == task.task_name


def test_legacy_keyword_groups_are_flattened_to_keyword_rules():
    task = Task(
        id=1,
        task_name="Sony A7M4",
        enabled=True,
        keyword="sony a7m4",
        description="body",
        max_pages=2,
        personal_only=True,
        min_price=None,
        max_price=None,
        cron=None,
        ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="prompts/sony_a7m4_criteria.txt",
        decision_mode="keyword",
        keyword_rule_groups=[
            {"name": "组1", "include_keywords": ["a7m4", "验货宝"], "exclude_keywords": ["瑕疵"]},
            {"name": "组2", "include_keywords": ["全画幅", "a7m4"], "exclude_keywords": ["拆修"]},
        ],
        is_running=False,
    )

    assert task.keyword_rules == ["a7m4", "验货宝", "全画幅"]


def test_generate_request_accepts_legacy_group_payload():
    req = TaskGenerateRequest(
        task_name="legacy",
        keyword="sony a7m4",
        description="",
        decision_mode="keyword",
        keyword_rule_groups=[{"include_keywords": ["a7m4", "验货宝"], "exclude_keywords": ["瑕疵"]}],
    )
    assert req.keyword_rules == ["a7m4", "验货宝"]


def test_generate_request_enables_image_analysis_by_default():
    req = TaskGenerateRequest(
        task_name="Sony A7M4",
        keyword="sony a7m4",
        description="只看机身成色和卖家信用。",
        decision_mode="ai",
    )
    assert req.analyze_images is True


def test_generate_request_infers_fixed_account_strategy_from_state_file():
    req = TaskGenerateRequest(
        task_name="Sony A7M4",
        keyword="sony a7m4",
        description="只看机身成色和卖家信用。",
        decision_mode="ai",
        account_state_file="state/acc_1.json",
    )

    assert req.account_strategy == "fixed"


def test_generate_request_requires_state_file_for_fixed_account_strategy():
    try:
        TaskGenerateRequest(
            task_name="Sony A7M4",
            keyword="sony a7m4",
            description="只看机身成色和卖家信用。",
            decision_mode="ai",
            account_strategy="fixed",
        )
    except ValueError as exc:
        assert "固定账号模式下必须选择账号" in str(exc)
        return

    raise AssertionError("固定账号模式应要求 account_state_file")


def _build_account_task(**overrides):
    payload = dict(
        id=1,
        task_name="Sony A7M4",
        enabled=True,
        keyword="sony a7m4",
        description="body",
        max_pages=2,
        personal_only=True,
        min_price=None,
        max_price=None,
        cron=None,
        ai_prompt_base_file="prompts/base_prompt.txt",
        ai_prompt_criteria_file="prompts/sony_a7m4_criteria.txt",
        account_strategy="rotate",
        account_state_file="state/acc_1.json",
        is_running=False,
    )
    payload.update(overrides)
    return Task(**payload)


def test_partial_update_keeps_account_strategy_and_state_file():
    """start/stop 只传 is_running 时，不能把 rotate/fixed 重置成 auto。"""
    task = _build_account_task()

    update = TaskUpdate(is_running=True)
    updated = task.apply_update(update)

    assert updated.is_running is True
    assert updated.account_strategy == "rotate"
    assert updated.account_state_file == "state/acc_1.json"


def test_partial_update_can_set_account_strategy_explicitly():
    task = _build_account_task()

    updated = task.apply_update(TaskUpdate(account_strategy="auto", account_state_file=None))

    assert updated.account_strategy == "auto"
    assert updated.account_state_file is None


def test_title_filter_fields_are_normalized():
    task = _build_account_task(
        title_include_keywords="GTX 1070, 8G\nGTX1070",
        title_exclude_keywords=["1070 Ti", "矿卡"],
    )

    assert task.title_include_keywords == ["GTX 1070", "8G", "GTX1070"]
    assert task.title_exclude_keywords == ["1070 Ti", "矿卡"]


def test_generate_request_accepts_title_filters():
    req = TaskGenerateRequest(
        task_name="GTX 1070",
        keyword="GTX1070 8G",
        description="只看个人自用。",
        decision_mode="ai",
        title_include_keywords=["1070"],
        title_exclude_keywords=["1070ti"],
    )

    assert req.title_include_keywords == ["1070"]
    assert req.title_exclude_keywords == ["1070ti"]

