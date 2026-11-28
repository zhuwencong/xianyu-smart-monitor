import asyncio

from src.services.item_analysis_dispatcher import (
    ItemAnalysisDispatcher,
    ItemAnalysisJob,
)


def test_item_analysis_dispatcher_uses_bounded_concurrency():
    active_ai_calls = 0
    max_active_ai_calls = 0
    saved_records = []
    notifications = []

    async def seller_loader(user_id: str):
        await asyncio.sleep(0.005)
        return {"卖家ID": user_id}

    async def image_downloader(product_id: str, image_urls: list[str], task_name: str):
        return []

    async def ai_analyzer(record: dict, image_paths: list[str], prompt_text: str):
        nonlocal active_ai_calls, max_active_ai_calls
        active_ai_calls += 1
        max_active_ai_calls = max(max_active_ai_calls, active_ai_calls)
        await asyncio.sleep(0.03)
        active_ai_calls -= 1
        return {
            "analysis_source": "ai",
            "is_recommended": True,
            "reason": f"推荐 {record['商品信息']['商品ID']}",
            "keyword_hit_count": 0,
        }

    async def notifier(item_data: dict, reason: str):
        notifications.append((item_data["商品ID"], reason))

    async def saver(record: dict, keyword: str):
        saved_records.append((keyword, record))
        return True

    async def run():
        dispatcher = ItemAnalysisDispatcher(
            concurrency=2,
            skip_ai_analysis=False,
            seller_loader=seller_loader,
            image_downloader=image_downloader,
            ai_analyzer=ai_analyzer,
            notifier=notifier,
            saver=saver,
            min_push_score=0,  # 本用例只验证并发与落盘，推送门槛单独测
        )
        for index in range(3):
            dispatcher.submit(
                ItemAnalysisJob(
                    keyword="demo",
                    task_name="Demo",
                    decision_mode="ai",
                    analyze_images=False,
                    prompt_text="prompt",
                    keyword_rules=(),
                    final_record={
                        "商品信息": {"商品ID": str(index), "商品图片列表": []},
                        "卖家信息": {},
                    },
                    seller_id=f"seller-{index}",
                    zhima_credit_text="优秀",
                    registration_duration_text="来闲鱼1年",
                )
            )
        await dispatcher.join()
        return dispatcher

    dispatcher = asyncio.run(run())
    assert dispatcher.completed_count == 3
    assert len(saved_records) == 3
    assert len(notifications) == 3
    assert max_active_ai_calls == 2
    assert saved_records[0][1]["卖家信息"]["卖家ID"].startswith("seller-")


def test_item_analysis_dispatcher_supports_keyword_mode_without_ai():
    saved_records = []

    async def seller_loader(user_id: str):
        return {"卖家标签": "个人闲置"}

    async def image_downloader(product_id: str, image_urls: list[str], task_name: str):
        raise AssertionError("关键词模式不应下载图片")

    async def ai_analyzer(record: dict, image_paths: list[str], prompt_text: str):
        raise AssertionError("关键词模式不应调用 AI")

    async def notifier(item_data: dict, reason: str):
        return None

    async def saver(record: dict, keyword: str):
        saved_records.append(record)
        return True

    async def run():
        dispatcher = ItemAnalysisDispatcher(
            concurrency=1,
            skip_ai_analysis=False,
            seller_loader=seller_loader,
            image_downloader=image_downloader,
            ai_analyzer=ai_analyzer,
            notifier=notifier,
            saver=saver,
        )
        dispatcher.submit(
            ItemAnalysisJob(
                keyword="demo",
                task_name="Demo",
                decision_mode="keyword",
                analyze_images=False,
                prompt_text="",
                keyword_rules=("个人闲置",),
                final_record={
                    "商品信息": {"商品ID": "1", "商品标题": "演示商品"},
                    "卖家信息": {},
                },
                seller_id="seller-1",
                zhima_credit_text="优秀",
                registration_duration_text="来闲鱼1年",
            )
        )
        await dispatcher.join()

    asyncio.run(run())
    assert saved_records[0]["ai_analysis"]["analysis_source"] == "keyword"
    assert saved_records[0]["ai_analysis"]["is_recommended"] is True


def test_dispatcher_hard_gates_override_ai_recommendation():
    """模型说能买，硬门槛说不行 —— 落盘和通知都必须以硬门槛为准。"""
    saved_records = []
    notifications = []

    async def seller_loader(user_id: str):
        return {"卖家信用等级": "卖家信用优秀"}

    async def image_downloader(product_id: str, image_urls: list[str], task_name: str):
        return []

    async def ai_analyzer(record: dict, image_paths: list[str], prompt_text: str):
        return {
            "analysis_source": "ai",
            "is_recommended": True,
            "reason": "商品为半高专业卡，价格极具性价比",
            "value_score": 88,
            "risk_tags": ["显存仅2GB"],
            "keyword_hit_count": 0,
        }

    async def notifier(item_data: dict, reason: str):
        notifications.append(reason)

    async def saver(record: dict, keyword: str):
        saved_records.append(record)
        return True

    async def run():
        dispatcher = ItemAnalysisDispatcher(
            concurrency=1,
            skip_ai_analysis=False,
            seller_loader=seller_loader,
            image_downloader=image_downloader,
            ai_analyzer=ai_analyzer,
            notifier=notifier,
            saver=saver,
        )
        dispatcher.submit(
            ItemAnalysisJob(
                keyword="显卡",
                task_name="显卡监控（AI）",
                decision_mode="ai",
                analyze_images=False,
                prompt_text="prompt",
                keyword_rules=(),
                final_record={
                    "商品信息": {
                        "商品ID": "1097810856010",
                        "商品标题": "NVIDIA Quadro P620专业显卡，2G显存，半高设计，包邮",
                        "当前售价": "¥208",
                    },
                    "卖家信息": {},
                },
                seller_id="seller-1",
                zhima_credit_text="优秀",
                registration_duration_text="来闲鱼1年",
                budget_max="1000",
            )
        )
        await dispatcher.join()

    asyncio.run(run())

    analysis = saved_records[0]["ai_analysis"]
    assert analysis["is_recommended"] is False
    assert analysis["hard_blocked"] is True
    assert analysis["reason"].startswith("[硬门槛否决]")
    assert "专业卡/计算卡" in analysis["risk_tags"]
    assert notifications == []


def _run_push_case(criteria_status: str, price: str, market_median: float):
    """跑一条商品，返回 (推送列表, 落盘分数)。"""
    notifications = []
    saved = []

    async def seller_loader(user_id: str):
        return {"卖家信用等级": "卖家信用极好"}

    async def image_downloader(product_id: str, image_urls: list[str], task_name: str):
        return []

    async def ai_analyzer(record: dict, image_paths: list[str], prompt_text: str):
        keys = ("model_chip", "storage", "seller_type", "condition", "battery_health", "warranty")
        return {
            "analysis_source": "ai",
            "is_recommended": True,
            "reason": "卖家资料完整，价格低于同型号行情",
            "value_score": 80,
            "keyword_hit_count": 0,
            "criteria_analysis": {key: {"status": criteria_status} for key in keys},
        }

    async def notifier(item_data: dict, reason: str):
        notifications.append(reason)

    async def saver(record: dict, keyword: str):
        saved.append(record["ai_analysis"])
        return True

    async def run():
        dispatcher = ItemAnalysisDispatcher(
            concurrency=1,
            skip_ai_analysis=False,
            seller_loader=seller_loader,
            image_downloader=image_downloader,
            ai_analyzer=ai_analyzer,
            notifier=notifier,
            saver=saver,
        )
        dispatcher.submit(
            ItemAnalysisJob(
                keyword="Find X8 Ultra",
                task_name="OPPO Find X8 Ultra 16+1TB",
                decision_mode="ai",
                analyze_images=False,
                prompt_text="prompt",
                keyword_rules=(),
                final_record={
                    "商品信息": {
                        "商品ID": "1",
                        "商品标题": "OPPO Find X8 Ultra 16+1TB 国行 无拆修",
                        "当前售价": price,
                    },
                    "卖家信息": {},
                    "price_insight": {
                        "market_median_price": market_median,
                        "market_scope": "keyword",
                        "market_sample_count": 12,
                    },
                },
                seller_id="seller-1",
                zhima_credit_text="极好",
                registration_duration_text="来闲鱼3年",
                budget_min="3800",
                budget_max="5400",
            )
        )
        await dispatcher.join()

    asyncio.run(run())
    return notifications, saved[0]


def test_push_only_when_score_reaches_threshold():
    """AI 说「推荐」只是入场券，分数够了才值得打扰人。"""
    high_notifications, high_analysis = _run_push_case("PASS", "¥3500", 4200.0)
    low_notifications, low_analysis = _run_push_case("FAIL", "¥3500", 4200.0)

    assert high_analysis["score_total"] >= 75
    assert len(high_notifications) == 1
    assert high_notifications[0].startswith("[A级") or high_notifications[0].startswith("[S级")

    assert low_analysis["score_total"] < 75
    assert low_notifications == []


def test_score_is_written_to_analysis_for_panel_reuse():
    """分数落进 ai_analysis，面板直接读，避免推送与展示两套算法打架。"""
    _notifications, analysis = _run_push_case("PASS", "¥3500", 4200.0)
    assert isinstance(analysis["score_total"], int)
    assert analysis["score_grade"] in {"S", "A", "B", "C", "D"}
    assert isinstance(analysis["score_dims"], list) and analysis["score_dims"]
    assert analysis["score_gap"] is not None
    assert analysis["score_gap_scope"] == "keyword"

