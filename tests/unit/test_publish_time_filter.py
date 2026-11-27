"""上架时效预筛测试。"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.services.publish_time_filter import (
    describe_listing_age,
    DEFAULT_MAX_AGE_DAYS,
    build_publish_time_filter,
    parse_publish_time,
)


NOW = datetime(2026, 11, 26, 12, 0)


def _ago(**kwargs) -> str:
    return (NOW - timedelta(**kwargs)).strftime("%Y-%m-%d %H:%M")


class TestParsePublishTime:
    def test_parses_standard_format(self):
        assert parse_publish_time("2026-11-25 08:30") == datetime(2026, 11, 25, 8, 30)

    def test_parses_seconds_format(self):
        assert parse_publish_time("2026-11-25 08:30:15") == datetime(2026, 11, 25, 8, 30, 15)

    def test_parses_date_only(self):
        assert parse_publish_time("2026-11-25") == datetime(2026, 11, 25)

    @pytest.mark.parametrize("value", ["", None, "未知时间", "刚刚", "abc", 0])
    def test_returns_none_for_unparseable(self, value):
        assert parse_publish_time(value) is None


class TestPublishTimeFilter:
    def test_keeps_fresh_listing(self):
        keep, reason = build_publish_time_filter(3).check(_ago(days=1), now=NOW)
        assert keep is True and reason == ""

    def test_keeps_listing_exactly_at_boundary(self):
        """正好 3 天（72 小时）仍在门槛内。"""
        keep, _ = build_publish_time_filter(3).check(_ago(hours=71), now=NOW)
        assert keep is True

    def test_drops_listing_just_past_boundary(self):
        keep, reason = build_publish_time_filter(3).check(_ago(hours=73), now=NOW)
        assert keep is False
        assert "3 天" in reason

    def test_drops_old_listing_with_day_count_in_reason(self):
        keep, reason = build_publish_time_filter(3).check(_ago(days=10), now=NOW)
        assert keep is False
        assert "10 天" in reason

    def test_drops_unknown_publish_time(self):
        keep, reason = build_publish_time_filter(3).check("未知时间", now=NOW)
        assert keep is False
        assert "未知" in reason

    def test_drops_missing_publish_time(self):
        keep, _ = build_publish_time_filter(3).check(None, now=NOW)
        assert keep is False


class TestBuildFromTaskOption:
    @pytest.mark.parametrize(
        ("option", "expected"),
        [
            ("1天内", 1),
            ("3天内", 3),
            ("7天内", 7),
            ("14天内", 14),
        ],
    )
    def test_parses_chinese_day_options(self, option, expected):
        """直接复用餐任务的 new_publish_option，避免两处配置打架。"""
        assert build_publish_time_filter(option).max_age_days == expected

    @pytest.mark.parametrize("option", ["", "__none__", "最新", None])
    def test_disabled_options_filter_nothing(self, option):
        f = build_publish_time_filter(option)
        assert f.is_empty is True
        # 关掉后连未知时间也放行
        assert f.check("未知时间", now=NOW) == (True, "")

    def test_accepts_plain_int(self):
        assert build_publish_time_filter(5).max_age_days == 5

    def test_falls_back_to_default_on_garbage(self):
        assert build_publish_time_filter("???").max_age_days == DEFAULT_MAX_AGE_DAYS


class TestDescribeListingAge:
    """给 AI 的上架时长文案。LLM 自己算日期会错，所以必须本地算死。"""

    def test_minutes_for_very_fresh(self):
        assert describe_listing_age(_ago(minutes=11), now=NOW) == "上架 11 分钟"

    def test_hours_for_same_day(self):
        assert describe_listing_age(_ago(hours=5), now=NOW) == "上架 5 小时"

    def test_days_for_old_listing(self):
        assert describe_listing_age(_ago(days=10), now=NOW) == "上架 10 天"

    def test_unknown_publish_time(self):
        assert "未知" in describe_listing_age("未知时间", now=NOW)

    def test_future_timestamp_treated_as_fresh(self):
        """发布时间晚于抓取时间（时区/时钟偏差）不能算成负天数。"""
        future = (NOW + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
        assert "刚刚发布" in describe_listing_age(future, now=NOW)


class TestWorkbenchListingWindow:
    """工作台展示层的同一道门槛。

    抓取侧拦得住新货，但门槛上线前入库的老记录不会自己消失——实测有 60 条
    超 3 天的老卡仍在候选列表里，且因分数高排在前面。这里锁住展示层的行为。
    """

    @staticmethod
    def _task(option):
        return SimpleNamespace(new_publish_option=option)

    @staticmethod
    def _row(publish_time, crawl_time):
        return {"publish_time": publish_time, "crawl_time": crawl_time}

    def test_fresh_item_kept(self):
        from src.services.workbench_service import _within_listing_window

        row = self._row("2026-11-27 13:50", "2026-11-27T14:01:00")
        assert _within_listing_window(row, self._task("3天内")) is True

    def test_stale_item_dropped(self):
        from src.services.workbench_service import _within_listing_window

        row = self._row("2025-09-29 10:20", "2026-11-25T17:29:19")
        assert _within_listing_window(row, self._task("3天内")) is False

    def test_unknown_publish_time_dropped(self):
        from src.services.workbench_service import _within_listing_window

        row = self._row("未知", "2026-11-27T14:00:00")
        assert _within_listing_window(row, self._task("3天内")) is False

    def test_reference_is_crawl_time_not_now(self):
        """基准必须是抓取时间，否则「当时上架 1 小时」的记录隔天看会被判超期。"""
        from src.services.workbench_service import _within_listing_window

        row = self._row("2026-11-20 10:00", "2026-11-20T11:00:00")
        assert _within_listing_window(row, self._task("3天内")) is True

    def test_unconfigured_task_not_filtered(self):
        """未配置 new_publish_option 的老任务不能被隐式套上 3 天门槛。"""
        from src.services.workbench_service import _within_listing_window

        row = self._row("2025-01-01 10:00", "2026-11-27T14:00:00")
        assert _within_listing_window(row, self._task(None)) is True
        assert _within_listing_window(row, self._task("最新")) is True


class TestWorkbenchVisibleWindow:
    """工作台默认「只看近 5 天上架」的展示窗口。

    买家的判断很实在：真有性价比的机器挂出去几小时就被拍走，一条上架一周
    还没成交的记录留在前台只是把新货挤到第二页。所以前台默认不显示，
    但数据库里一条都不删（后台统计、比价样本、导出还要用）。

    与上面的 ``_within_listing_window`` 关键差异：基准是 **now()**。
    老链接会被反复抓到，crawl_time 永远是新的，用它当基准等于没过滤。
    """

    @staticmethod
    def _row(publish_time, crawl_time):
        return {"publish_time": publish_time, "crawl_time": crawl_time}

    def test_stale_item_hidden_even_if_crawled_today(self):
        """今天刚抓到的 10 天前老链接，仍然要藏起来。"""
        from src.services.workbench_service import _within_visible_window

        now = datetime.now()
        published = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
        crawled = now.isoformat()
        assert _within_visible_window(self._row(published, crawled), 5) is False

    def test_fresh_item_kept(self):
        from src.services.workbench_service import _within_visible_window

        now = datetime.now()
        published = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
        assert _within_visible_window(self._row(published, now.isoformat()), 5) is True

    def test_boundary_five_days_still_visible(self):
        """刚好 5 天内的要保留，不能差一分钟就藏。"""
        from src.services.workbench_service import _within_visible_window

        now = datetime.now()
        published = (now - timedelta(days=4, hours=20)).strftime("%Y-%m-%d %H:%M")
        assert _within_visible_window(self._row(published, now.isoformat()), 5) is True

    def test_unknown_publish_time_kept(self):
        """发布时间缺失时保留：这是降噪，不是质量判定。"""
        from src.services.workbench_service import _within_visible_window

        now = datetime.now()
        assert _within_visible_window(self._row("未知", now.isoformat()), 5) is True
        assert _within_visible_window(self._row("", now.isoformat()), 5) is True

    def test_zero_days_means_no_window(self):
        from src.services.workbench_service import _within_visible_window

        now = datetime.now()
        published = (now - timedelta(days=400)).strftime("%Y-%m-%d %H:%M")
        assert _within_visible_window(self._row(published, now.isoformat()), 0) is True
