import json
import os
from types import SimpleNamespace

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.services.task_run_service import TaskRunService
from src.services.workbench_service import list_account_health, list_candidates, update_candidate_review


def _record(item_id: str = "1097137892689") -> dict:
    return {
        "爬取时间": "2026-11-03T18:24:28",
        "搜索关键字": "GTX1070 8G",
        "任务名称": "GTX 1070",
        "商品信息": {
            "商品标题": "索泰GTX1070 8G X-Gaming OC显卡，个人主机拆机自用",
            "当前售价": "¥715",
            "商品ID": item_id,
            "商品链接": f"https://www.goofish.com/item?id={item_id}",
            "商品主图链接": "https://img.example.com/main.jpg",
            "商品图片列表": ["https://img.example.com/main.jpg", "https://img.example.com/2.jpg"],
            "发货地区": "四川",
            "商品标签": ["包邮", "验货宝"],
            "发布时间": "2026-10-29 21:06",
            "浏览量": 140,
        },
        "卖家信息": {
            "卖家昵称": "数码职业爱好者",
            "卖家信用等级": "卖家信用极好",
            "作为卖家的好评率": "100.00%",
            "卖家注册时长": "来闲鱼11年2个月",
        },
        "ai_analysis": {
            "is_recommended": True,
            "analysis_source": "ai",
            "reason": "卖家为典型的个人数码爱好者，描述详实。",
            "value_score": 75,
            "risk_tags": ["无购买凭证"],
            "criteria_analysis": {
                "model_chip": {"status": "PASS", "comment": "型号明确"},
                "battery_health": {"status": "NEEDS_MANUAL_CHECK", "comment": "缺少烤机图"},
                "seller_type": {"status": "PASS", "comment": "个人卖家"},
            },
        },
        "price_insight": {
            "market_avg_price": 727,
            "min_price": 650,
            "max_price": 800,
            "observation_count": 5,
        },
    }


def _insert_result(item_id: str, crawl_time: str, link_key: str, *, review_status: str = "unseen"):
    record = _record(item_id)
    record["爬取时间"] = crawl_time
    with sqlite_connection() as conn:
        conn.execute(
            """
            INSERT INTO result_items (
                result_filename, keyword, task_name, crawl_time, publish_time, price,
                price_display, item_id, title, link, link_unique_key, seller_nickname,
                is_recommended, analysis_source, keyword_hit_count, status, review_status, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "GTX1070_8G_full_data.jsonl",
                "GTX1070 8G",
                "GTX 1070",
                crawl_time,
                "2026-10-29 21:06",
                715,
                "¥715",
                item_id,
                "索泰GTX1070 8G X-Gaming OC显卡，个人主机拆机自用",
                f"https://www.goofish.com/item?id={item_id}",
                link_key,
                "数码职业爱好者",
                1,
                "ai",
                0,
                "active",
                review_status,
                json.dumps(record, ensure_ascii=False),
            ),
        )
        conn.commit()


def test_candidates_dedupe_and_filters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    bootstrap_sqlite_storage(legacy_config_file=None)
    _insert_result("1097137892689", "2026-11-03T18:24:28", "older")
    _insert_result("1097137892689", "2026-11-03T20:24:28", "newer")
    _insert_result("999", "2026-11-03T19:00:00", "second")

    task = SimpleNamespace(id=2, task_name="GTX 1070", keyword="GTX1070 8G")
    result = list_candidates([task], review_status="all", limit=10)

    assert result["total"] == 2
    assert result["counts"] == {"unseen": 2, "favorite": 0, "handled": 0}
    latest = next(item for item in result["items"] if item["item_id"] == "1097137892689")
    assert latest["ai_verdict"] == "recommend"
    assert latest["missing_checks"] == ["运行测试材料"]
    assert latest["market"]["avg"] == 727
    assert latest["crawl_time"] == "2026-11-03T20:24:28"
    assert latest["ai_score"] is not None
    assert [item["label"] for item in latest["score_breakdown"]] == ["匹配", "价格", "卖家", "凭证"]

    searched = list_candidates([task], review_status="all", query="索泰", limit=10)
    assert searched["total"] == 2


def test_update_candidate_review_and_ai_counts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    bootstrap_sqlite_storage(legacy_config_file=None)
    _insert_result("1097137892689", "2026-11-03T18:24:28", "one")

    task = SimpleNamespace(id=2, task_name="GTX 1070", keyword="GTX1070 8G")
    assert update_candidate_review("1097137892689", "favorite") is True
    favorite = list_candidates([task], review_status="favorite", limit=10)
    assert favorite["total"] == 1
    assert favorite["counts"] == {"unseen": 0, "favorite": 1, "handled": 0}
    assert favorite["ai_counts"]["recommend"] == 1

    unseen = list_candidates([task], review_status="unseen", limit=10)
    assert unseen["total"] == 0


def test_task_run_service_records_completion_and_stale_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    bootstrap_sqlite_storage(legacy_config_file=None)

    service = TaskRunService()
    run_id = service.start_run(task_id=2, task_name="GTX 1070", keyword="GTX1070 8G")
    run = service.finish_run(run_id, exit_code=0)
    assert run is not None
    assert run["status"] == "no_new"
    assert run["saved_count"] == 0

    active_run = service.start_run(task_id=2, task_name="GTX 1070", keyword="GTX1070 8G")
    stale_count = service.mark_stale_runs()
    assert stale_count == 1
    latest = service.latest_run(2)
    assert latest is not None
    assert latest["status"] == "failed"
    assert "服务重启" in (latest["error_message"] or "")

    # finish_run 是幂等的：已经收口的记录不会被第二次覆盖。
    again = service.finish_run(active_run, exit_code=0)
    assert again is not None
    assert again["status"] == "failed"


def test_account_health_uses_login_failure_time(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ACCOUNT_STATE_DIR", "state")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    account_file = state_dir / "acc_1.json"
    account_file.write_text('{"cookie":"demo"}', encoding="utf-8")
    os.utime(account_file, (1793678400, 1793678400))  # 2026-11-03 12:00

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "task_1.log").write_text(
        "\n".join(
            [
                "--- 开始执行监控任务 ---",
                "账号轮换：使用登录状态 state\\acc_1.json",
                "[ 2026-11-04 12:20:00] 步骤 1 - 导航到搜索结果页...",
                "[ 2026-11-04 12:20:39] 检测到登录失效/重定向: Login required",
            ]
        ),
        encoding="utf-8",
    )

    accounts = list_account_health()
    assert len(accounts) == 1
    assert accounts[0]["status"] == "needs_update"
    assert accounts[0]["last_failure_at"] == "2026-11-04T12:20:39"
    assert "12:20" in accounts[0]["reason"]

    # 重新扫码会更新文件 mtime；晚于失效时间后应恢复为可用。
    newer = 1793773200  # 2026-11-04 14:20
    os.utime(account_file, (newer, newer))
    recovered = list_account_health()
    assert recovered[0]["status"] == "ok"
