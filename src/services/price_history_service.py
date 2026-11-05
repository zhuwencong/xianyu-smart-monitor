"""
价格历史记录与聚合服务
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from datetime import datetime
from statistics import median
from typing import Any, Iterable, Optional

from src.domain.scoring.specs import extract_specs, looks_like_gpu_task
from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection

PRICE_HISTORY_DIR = "price_history"
DEFAULT_HISTORY_WINDOW_DAYS = 30

# 同型号样本少于此数时不给均价：宁可说「样本不足」，也不拿别的型号凑数。
MIN_MODEL_SAMPLES = 5


def normalize_keyword_slug(keyword: str) -> str:
    text = "".join(
        char for char in str(keyword or "").lower().replace(" ", "_")
        if char.isalnum() or char in "_-"
    ).rstrip("_")
    return text or "unknown"


def build_price_history_path(keyword: str) -> str:
    return os.path.join(
        PRICE_HISTORY_DIR,
        f"{normalize_keyword_slug(keyword)}_history.jsonl",
    )


def parse_price_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)

    text = str(value).strip().replace("¥", "").replace(",", "")
    if not text or text in {"价格异常", "暂无", "-", "N/A"}:
        return None
    if text.endswith("万"):
        text = str(float(text[:-1]) * 10000)
    try:
        return round(float(text), 2)
    except (TypeError, ValueError):
        return None


def _safe_iso_datetime(value: Optional[str]) -> str:
    if value:
        return value
    return datetime.now().isoformat()


def _to_day(iso_text: str) -> str:
    return iso_text[:10]


def _build_snapshot_record(
    *,
    keyword: str,
    task_name: str,
    item: dict,
    run_id: str,
    snapshot_time: str,
) -> Optional[dict]:
    item_id = str(item.get("商品ID") or "").strip()
    link = str(item.get("商品链接") or "").strip()
    unique_id = item_id or link
    price_value = parse_price_value(item.get("当前售价"))
    if not unique_id or price_value is None:
        return None

    return {
        "snapshot_time": snapshot_time,
        "snapshot_day": _to_day(snapshot_time),
        "run_id": run_id,
        "task_name": task_name,
        "keyword": keyword,
        "item_id": unique_id,
        "title": item.get("商品标题") or "",
        "price": price_value,
        "price_display": item.get("当前售价") or "",
        "tags": item.get("商品标签") or [],
        "region": item.get("发货地区") or "",
        "seller": item.get("卖家昵称") or "",
        "publish_time": item.get("发布时间") or "",
        "link": link,
    }


def record_market_snapshots(
    *,
    keyword: str,
    task_name: str,
    items: Iterable[dict],
    run_id: str,
    snapshot_time: Optional[str] = None,
    seen_item_ids: Optional[set[str]] = None,
) -> list[dict]:
    snapshot_time = _safe_iso_datetime(snapshot_time)
    seen = seen_item_ids if seen_item_ids is not None else set()
    records: list[dict] = []

    for item in items:
        record = _build_snapshot_record(
            keyword=keyword,
            task_name=task_name,
            item=item,
            run_id=run_id,
            snapshot_time=snapshot_time,
        )
        if record is None or record["item_id"] in seen:
            continue
        seen.add(record["item_id"])
        records.append(record)

    if not records:
        return []

    bootstrap_sqlite_storage()
    keyword_slug = normalize_keyword_slug(keyword)
    with sqlite_connection() as conn:
        for record in records:
            conn.execute(
                """
                INSERT OR IGNORE INTO price_snapshots (
                    keyword_slug, keyword, task_name, snapshot_time, snapshot_day,
                    run_id, item_id, title, price, price_display, tags_json, region,
                    seller, publish_time, link
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    keyword_slug,
                    record.get("keyword", keyword),
                    record.get("task_name", task_name),
                    record.get("snapshot_time", snapshot_time),
                    record.get("snapshot_day", _to_day(snapshot_time)),
                    record.get("run_id", run_id),
                    record.get("item_id", ""),
                    record.get("title", ""),
                    record.get("price"),
                    record.get("price_display", ""),
                    json.dumps(record.get("tags") or [], ensure_ascii=False),
                    record.get("region", ""),
                    record.get("seller", ""),
                    record.get("publish_time", ""),
                    record.get("link", ""),
                ),
            )
        conn.commit()
    return records


def load_price_snapshots(keyword: str) -> list[dict]:
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM price_snapshots
            WHERE keyword_slug = ?
            ORDER BY snapshot_time ASC, id ASC
            """,
            (normalize_keyword_slug(keyword),),
        ).fetchall()
    snapshots: list[dict] = []
    for row in rows:
        snapshots.append(
            {
                "snapshot_time": row["snapshot_time"],
                "snapshot_day": row["snapshot_day"],
                "run_id": row["run_id"],
                "task_name": row["task_name"],
                "keyword": row["keyword"],
                "item_id": row["item_id"],
                "title": row["title"],
                "price": row["price"],
                "price_display": row["price_display"],
                "tags": json.loads(row["tags_json"] or "[]"),
                "region": row["region"],
                "seller": row["seller"],
                "publish_time": row["publish_time"],
                "link": row["link"],
            }
        )
    return snapshots


def delete_price_snapshots(keyword: str) -> int:
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM price_snapshots WHERE keyword_slug = ?",
            (normalize_keyword_slug(keyword),),
        )
        conn.commit()
    return int(cursor.rowcount or 0)


def _dedupe_latest(records: Iterable[dict], group_key: str) -> list[dict]:
    latest_by_key: dict[str, dict] = {}
    for record in records:
        key = str(record.get(group_key) or "").strip()
        if not key:
            continue
        latest_by_key[key] = record
    return list(latest_by_key.values())


def _summarize_prices(records: Iterable[dict]) -> dict:
    entries = [record for record in records if parse_price_value(record.get("price")) is not None]
    prices = [float(record["price"]) for record in entries]
    if not prices:
        return {
            "sample_count": 0,
            "avg_price": None,
            "median_price": None,
            "min_price": None,
            "max_price": None,
        }

    return {
        "sample_count": len(prices),
        "avg_price": round(sum(prices) / len(prices), 2),
        "median_price": round(float(median(prices)), 2),
        "min_price": round(min(prices), 2),
        "max_price": round(max(prices), 2),
    }


def _percentile(ordered: list[float], pct: float) -> float:
    """线性插值分位数，输入必须是已排序列表。"""
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[int(position)])
    low_value = float(ordered[lower])
    high_value = float(ordered[upper])
    return low_value + (high_value - low_value) * (position - lower)


def _trim_outliers(prices: list[float]) -> list[float]:
    """按 1.5×IQR 去掉极端值，避免一条挂高价的商品把均价整体拉偏。"""
    if len(prices) < 5:
        return list(prices)
    ordered = sorted(prices)
    q1 = _percentile(ordered, 25)
    q3 = _percentile(ordered, 75)
    spread = q3 - q1
    if spread <= 0:
        return ordered
    low = q1 - 1.5 * spread
    high = q3 + 1.5 * spread
    trimmed = [price for price in ordered if low <= price <= high]
    return trimmed or ordered


def _benchmark_stats(prices: list[float], *, scope: str, model_key: str) -> dict:
    ordered = sorted(prices)
    trimmed = _trim_outliers(prices)
    return {
        "scope": scope,
        "model_key": model_key,
        "sample_count": len(prices),
        "median_price": round(_percentile(ordered, 50), 2),
        "low_price": round(_percentile(ordered, 25), 2),
        "high_price": round(_percentile(ordered, 75), 2),
        "avg_price": round(sum(trimmed) / len(trimmed), 2),
        "min_price": round(ordered[0], 2),
        "max_price": round(ordered[-1], 2),
    }


def _insufficient_benchmark(model_key: str, sample_count: int) -> dict:
    return {
        "scope": "insufficient",
        "model_key": model_key,
        "sample_count": sample_count,
        "median_price": None,
        "low_price": None,
        "high_price": None,
        "avg_price": None,
        "min_price": None,
        "max_price": None,
    }


def build_market_benchmark(
    market_records: Iterable[dict],
    title: str | None = None,
    *,
    gpu_hint: bool = False,
) -> Optional[dict]:
    """算「同型号」价格基准。

    优先用同型号（型号 + 显存）的中位数；同型号样本不够时退到同型号族；
    都不够就明确返回 ``scope="insufficient"``，绝不跨型号平均。
    抽不出型号时（手机/笔记本等）才退回关键词口径，保持原行为。
    """
    records = [
        (str(record.get("title") or ""), float(record["price"]))
        for record in market_records
        if record.get("price") is not None
    ]
    if not records:
        return None

    specs = extract_specs(title or "", gpu_hint=gpu_hint)
    family = specs.model_family
    if not family:
        if gpu_hint:
            # 显卡任务里认不出型号，就不能拿「显卡」全类的中位数去比价。
            return _insufficient_benchmark("", len(records))
        return _benchmark_stats([price for _title, price in records], scope="keyword", model_key="")

    exact: list[float] = []
    same_family: list[float] = []
    for record_title, price in records:
        record_specs = extract_specs(record_title, gpu_hint=gpu_hint)
        if not record_specs.model_family or record_specs.model_family != family:
            continue
        same_family.append(price)
        if specs.vram_gb and record_specs.vram_gb == specs.vram_gb:
            exact.append(price)

    exact_key = f"{family}_{specs.vram_gb}g" if specs.vram_gb else family
    if len(exact) >= MIN_MODEL_SAMPLES:
        return _benchmark_stats(exact, scope="model", model_key=exact_key)
    if len(same_family) >= MIN_MODEL_SAMPLES:
        return _benchmark_stats(same_family, scope="family", model_key=family)
    return _insufficient_benchmark(exact_key, len(same_family))


def _build_daily_trend(snapshots: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[str(snapshot.get("snapshot_day") or "")].append(snapshot)

    points: list[dict] = []
    for day in sorted(grouped.keys()):
        day_records = _dedupe_latest(grouped[day], "item_id")
        summary = _summarize_prices(day_records)
        summary["day"] = day
        points.append(summary)
    return points


def _recent_window_snapshots(snapshots: list[dict], window_days: int) -> list[dict]:
    if not snapshots:
        return []
    latest_time = max(str(record.get("snapshot_time") or "") for record in snapshots)
    latest_dt = datetime.fromisoformat(latest_time)
    filtered = []
    for record in snapshots:
        current_time = datetime.fromisoformat(str(record.get("snapshot_time") or latest_time))
        if (latest_dt - current_time).days <= max(0, window_days):
            filtered.append(record)
    return filtered


def _resolve_deal_label(score: int) -> str:
    if score >= 65:
        return "高性价比"
    if score >= 50:
        return "值得关注"
    if score >= 40:
        return "价格正常"
    return "价格偏高"


def build_item_price_context(
    snapshots: list[dict],
    *,
    item_id: str,
    current_price: Optional[float],
    market_snapshots: Optional[list[dict]] = None,
    title: Optional[str] = None,
    gpu_hint: bool = False,
) -> dict:
    if not item_id:
        return {"observation_count": 0, "deal_score": None, "deal_label": "暂无数据"}

    item_snapshots = [record for record in snapshots if str(record.get("item_id")) == str(item_id)]
    if not item_snapshots:
        return {"observation_count": 0, "deal_score": None, "deal_label": "暂无数据"}

    latest_item_snapshot = item_snapshots[-1]
    price_now = current_price if current_price is not None else parse_price_value(latest_item_snapshot.get("price"))
    historical_prices = [float(record["price"]) for record in item_snapshots if parse_price_value(record.get("price")) is not None]
    source_snapshots = market_snapshots if market_snapshots is not None else snapshots
    latest_run_id = str(source_snapshots[-1].get("run_id") or "") if source_snapshots else ""
    latest_market = _dedupe_latest(
        [record for record in source_snapshots if str(record.get("run_id") or "") == latest_run_id],
        "item_id",
    )
    item_title = title or str(latest_item_snapshot.get("title") or "")
    benchmark = build_market_benchmark(latest_market, item_title, gpu_hint=gpu_hint) or {}
    market_avg = benchmark.get("avg_price")
    # 比价一律用中位数：它不会被单条挂高价的商品带偏。
    market_reference = benchmark.get("median_price")
    insufficient = benchmark.get("scope") == "insufficient"

    score = 50
    if price_now is not None and market_reference:
        score += int(((market_reference - price_now) / market_reference) * 60)
    if price_now is not None and historical_prices:
        historical_max = max(historical_prices)
        if historical_max > 0:
            score += int(((historical_max - price_now) / historical_max) * 20)
        if math.isclose(price_now, min(historical_prices), rel_tol=0.001):
            score += 8
    score = max(0, min(100, score))

    previous_price = historical_prices[-2] if len(historical_prices) >= 2 else None
    change_amount = None if previous_price is None or price_now is None else round(price_now - previous_price, 2)
    change_percent = None
    if change_amount is not None and previous_price:
        change_percent = round(change_amount / previous_price * 100, 2)

    deal_label = "样本不足" if insufficient else _resolve_deal_label(score)

    return {
        "observation_count": len(historical_prices),
        "current_price": price_now,
        "avg_price": round(sum(historical_prices) / len(historical_prices), 2),
        "median_price": round(float(median(historical_prices)), 2),
        "min_price": round(min(historical_prices), 2),
        "max_price": round(max(historical_prices), 2),
        "first_seen_at": item_snapshots[0].get("snapshot_time"),
        "last_seen_at": latest_item_snapshot.get("snapshot_time"),
        "market_avg_price": market_avg,
        "market_median_price": market_reference,
        "market_low_price": benchmark.get("low_price"),
        "market_high_price": benchmark.get("high_price"),
        "market_sample_count": benchmark.get("sample_count"),
        "market_scope": benchmark.get("scope"),
        "market_model_key": benchmark.get("model_key") or "",
        "market_note": (
            "同型号样本不足，不做比价" if insufficient else ""
        ),
        "price_change_amount": change_amount,
        "price_change_percent": change_percent,
        "deal_score": score,
        "deal_label": deal_label,
    }


def build_market_reference(
    *,
    keyword: str,
    item: dict,
    current_market_items: list[dict],
    historical_snapshots: list[dict],
    gpu_hint: Optional[bool] = None,
) -> dict:
    item_title = str(item.get("商品标题") or "")
    if gpu_hint is None:
        gpu_hint = looks_like_gpu_task(keyword)
    current_market_records = []
    for market_item in current_market_items:
        price = parse_price_value(market_item.get("当前售价"))
        if price is None:
            continue
        current_market_records.append(
            {"price": price, "title": str(market_item.get("商品标题") or "")}
        )

    market_benchmark = (
        build_market_benchmark(current_market_records, item_title, gpu_hint=gpu_hint)
        or _insufficient_benchmark("", 0)
    )
    history_summary = _summarize_prices(_dedupe_latest(historical_snapshots, "item_id"))
    item_context = build_item_price_context(
        historical_snapshots,
        item_id=str(item.get("商品ID") or ""),
        current_price=parse_price_value(item.get("当前售价")),
        title=item_title,
        gpu_hint=gpu_hint,
    )
    return {
        "当前搜索样本": {
            "sample_count": market_benchmark.get("sample_count"),
            "avg_price": market_benchmark.get("avg_price"),
            "median_price": market_benchmark.get("median_price"),
            "min_price": market_benchmark.get("min_price"),
            "max_price": market_benchmark.get("max_price"),
            "scope": market_benchmark.get("scope"),
            "model_key": market_benchmark.get("model_key") or "",
            "comparable": market_benchmark.get("scope") in {"model", "family"},
        },
        "历史价格概览": history_summary,
        "本商品价格位置": item_context,
        "关键词": keyword,
    }


def build_price_history_insights(
    keyword: str,
    *,
    window_days: int = DEFAULT_HISTORY_WINDOW_DAYS,
    visible_item_ids: Optional[set[str]] = None,
) -> dict:
    snapshots = load_price_snapshots(keyword)
    if visible_item_ids is not None:
        snapshots = [
            snapshot
            for snapshot in snapshots
            if str(snapshot.get("item_id") or "") in visible_item_ids
        ]
    if not snapshots:
        return {
            "market_summary": _summarize_prices([]),
            "history_summary": {"unique_items": 0, **_summarize_prices([])},
            "daily_trend": [],
            "latest_snapshot_at": None,
        }

    recent_snapshots = _recent_window_snapshots(snapshots, window_days)
    latest_run_id = str(snapshots[-1].get("run_id") or "")
    latest_run_snapshots = _dedupe_latest(
        [record for record in snapshots if str(record.get("run_id") or "") == latest_run_id],
        "item_id",
    )
    latest_records_by_item = _dedupe_latest(recent_snapshots, "item_id")

    return {
        "market_summary": {
            **_summarize_prices(latest_run_snapshots),
            "snapshot_time": snapshots[-1].get("snapshot_time"),
        },
        "history_summary": {
            "unique_items": len(latest_records_by_item),
            **_summarize_prices(latest_records_by_item),
        },
        "daily_trend": _build_daily_trend(recent_snapshots),
        "latest_snapshot_at": snapshots[-1].get("snapshot_time"),
    }
