"""上架时效预筛。

闲鱼列表页原生带「新发布 3天内」筛选，但 scraper 里对这一步的失败处理是
"请求超时，继续执行"——筛选没生效时会静默放行整页老卡，白开详情页、
白下载图片、白调 AI。这里在本地按「发布时间」再兜一道，行为可预期：

- 只保留上架时长 ≤ ``MAX_AGE_DAYS`` 的商品；
- 发布时间缺失、为「未知时间」或无法解析 → 丢弃（宁可漏判，不可错推）；
- 阈值来自任务配置，未配置时默认 3 天。

与 ``title_filter`` 保持同样的设计取向：规则简单、可解释，且不抛异常。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# 闲鱼列表页解析出的发布时间格式（见 src/parsers.py）。
_PUBLISH_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")

DEFAULT_MAX_AGE_DAYS = 3


def parse_publish_time(raw) -> datetime | None:
    """解析发布时间，失败返回 None。"""
    text = str(raw or "").strip()
    if not text or "未知" in text:
        return None
    for fmt in _PUBLISH_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class PublishTimeFilter:
    max_age_days: int = DEFAULT_MAX_AGE_DAYS

    @property
    def is_empty(self) -> bool:
        return not self.max_age_days or self.max_age_days <= 0

    def check(self, raw_publish_time, now: datetime | None = None) -> tuple[bool, str]:
        """返回 (是否保留, 原因)。原因为空表示通过。"""
        if self.is_empty:
            return True, ""

        published = parse_publish_time(raw_publish_time)
        if published is None:
            return False, "发布时间未知，无法确认是否新发"

        current = now or datetime.now()
        age = current - published
        if age > timedelta(days=self.max_age_days):
            days = age.days
            return False, f"上架已 {days} 天，超出 {self.max_age_days} 天新鲜度门槛"
        return True, ""


def describe_listing_age(raw_publish_time, now: datetime | None = None) -> str:
    """把上架时长算成一句人话，直接塞进给 AI 的 JSON。

    为什么必须本地算：LLM 做日期减法不可靠。实测把「2026-11-26 23:34 发布、
    23:45 抓取」（只过了 11 分钟）算成「上架已超 3 天」，进而误触发一票否决。
    所以时长在这里算死，AI 只负责读结论，不负责算术。
    """
    published = parse_publish_time(raw_publish_time)
    if published is None:
        return "未知时间（无法确认是否新发）"

    current = now or datetime.now()
    delta = current - published
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes < 0:
        return "刚刚发布（时间戳晚于抓取时间，按新发处理）"
    if total_minutes < 60:
        return f"上架 {total_minutes} 分钟"
    hours = total_minutes // 60
    if hours < 24:
        return f"上架 {hours} 小时"
    return f"上架 {hours // 24} 天"


def build_publish_time_filter(max_age_days) -> PublishTimeFilter:
    """按天数构建过滤器。

    ``max_age_days`` 允许直接传任务里的 ``new_publish_option``
    （"1天内" / "3天内" / "7天内" / "14天内"），这样闲鱼原生筛选
    与本地兜底用同一份配置，不会出现一边 3 天一边 7 天。
    传 0 / 空 / "__none__" / "最新" 表示不限制。
    """
    if isinstance(max_age_days, str):
        text = max_age_days.strip()
        if text in {"", "__none__", "最新"}:
            return PublishTimeFilter(max_age_days=0)
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            try:
                return PublishTimeFilter(max_age_days=int(digits))
            except ValueError:
                pass
        return PublishTimeFilter(max_age_days=DEFAULT_MAX_AGE_DAYS)

    # None 表示"任务未配置这一项"，必须放行而不是套默认值——
    # 否则所有没配 new_publish_option 的老任务会被隐式加上 3 天门槛。
    if max_age_days is None:
        return PublishTimeFilter(max_age_days=0)

    try:
        days = int(max_age_days)
    except (TypeError, ValueError):
        days = DEFAULT_MAX_AGE_DAYS
    return PublishTimeFilter(max_age_days=days)
