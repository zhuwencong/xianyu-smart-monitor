import json
from types import SimpleNamespace

from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.services.workbench_service import list_candidates

P620_TITLE = (
    "NVIDIA Quadro P620专业显卡，2G显存，4个 miniDP接口，半高设计，低功耗，"
    "无需独立供电，包邮，插上即用"
)


def _record(*, title: str, price: float, insight: dict) -> dict:
    return {
        "爬取时间": "2026-11-02T00:32:51",
        "搜索关键字": "显卡",
        "任务名称": "显卡监控（AI）",
        "商品信息": {
            "商品标题": title,
            "当前售价": f"¥{price:.0f}",
            "商品ID": "1097810856010",
            "商品链接": "https://www.goofish.com/item?id=1097810856010",
            "商品标签": ["包邮"],
            "发货地区": "湖南",
        },
        "卖家信息": {
            "卖家昵称": "强毅中和",
            "卖家信用等级": "卖家信用优秀",
            "作为卖家的好评率": "100.00%",
        },
        "ai_analysis": {
            "is_recommended": True,
            "analysis_source": "ai",
            "reason": "商品为半高专业卡，价格极具性价比。",
            "value_summary": "当前售价208元，远低于市场均价526.98元，性价比极高。",
            "value_score": 88,
            "risk_tags": ["显存仅2GB"],
            "criteria_analysis": {
                "model_chip": {"status": "PASS", "comment": "半高专业卡"},
                "seller_type": {"status": "PASS", "comment": "个人玩家"},
            },
        },
        "price_insight": insight,
    }


def _insert(item_id: str, record: dict) -> None:
    item = record["商品信息"]
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
                "显卡_full_data.jsonl",
                "显卡",
                "显卡监控（AI）",
                record["爬取时间"],
                "2026-11-01 20:00",
                item["当前售价"].replace("¥", ""),
                item["当前售价"],
                item_id,
                item["商品标题"],
                item["商品链接"],
                item["商品链接"].split("&")[0] + f"&{item_id}",
                "强毅中和",
                1,
                "ai",
                0,
                "active",
                "unseen",
                json.dumps(record, ensure_ascii=False),
            ),
        )
        conn.commit()


def _setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_DATABASE_FILE", str(tmp_path / "app.sqlite3"))
    bootstrap_sqlite_storage(legacy_config_file=None)


TASK = SimpleNamespace(
    id=1,
    task_name="显卡监控（AI）",
    keyword="显卡",
    min_price=None,
    max_price=None,
    free_shipping=False,
)


def test_professional_card_cannot_be_recommended(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _insert(
        "1097810856010",
        _record(
            title=P620_TITLE,
            price=208.0,
            insight={
                # 旧数据里被跨型号均价污染的字段
                "market_avg_price": 526.98,
                "observation_count": 1,
                "min_price": 208.0,
                "max_price": 208.0,
            },
        ),
    )

    result = list_candidates([TASK], review_status="all", limit=10)
    candidate = result["items"][0]

    assert candidate["ai_verdict"] == "mismatch"
    assert candidate["ai_label"] == "不匹配"
    assert candidate["recommended"] is False
    assert candidate["hard_blocked"] is True
    assert candidate["ai_score"] <= 40
    assert candidate["hard_gates"][0]["key"] == "professional_card"
    # 判断依据必须先说清楚硬门槛，而不是继续吹「远低于均价」
    assert candidate["ai_summary"].startswith("底层硬门槛否决")
    # 型号可识别但没有同型号样本时，不给跨型号「市场价」
    assert candidate["market"]["avg"] is None
    assert candidate["market"]["comparable"] is False


def test_same_model_benchmark_is_shown_as_market_price(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _insert(
        "1097810856011",
        _record(
            title="影驰GTX1070 8G显卡，包邮，功能正常",
            price=650.0,
            insight={
                "market_avg_price": 734.56,
                "market_median_price": 740.0,
                "market_low_price": 690.0,
                "market_high_price": 800.0,
                "market_sample_count": 9,
                "market_scope": "model",
                "market_model_key": "1070_8g",
                "observation_count": 2,
            },
        ),
    )

    result = list_candidates([TASK], review_status="all", limit=10)
    candidate = result["items"][0]

    assert candidate["ai_verdict"] == "recommend"
    assert candidate["hard_blocked"] is False
    assert candidate["market"]["comparable"] is True
    assert candidate["market"]["avg"] == 740.0
    assert candidate["market"]["samples"] == 9
