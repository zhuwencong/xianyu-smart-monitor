"""闲鱼监控工作台的数据拼装层。

把散落在 result_items、task_runs、日志和账号文件里的信息整理成新版 UI
需要的候选商品、监控任务、运行记录与异常入口。
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Iterable

from src.domain.scoring import (
    breakdown_payload,
    evaluate_gates,
    extract_specs,
    price_score,
    resolve_overall,
    resolve_verdict,
    task_allows_professional,
)
from src.domain.scoring.specs import looks_like_gpu_task
from src.failure_guard import FailureGuard
from src.infrastructure.config.env_manager import env_manager
from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection
from src.infrastructure.persistence.storage_names import build_result_filename
from src.services.notification_config_service import (
    build_configured_channels,
    load_notification_settings,
)
from src.services.price_history_service import parse_price_value
from src.services.task_run_service import STATUS_LABELS, TaskRunService
from src.utils import resolve_task_log_path


REVIEW_LABELS = {
    "unseen": "未查看",
    "favorite": "已收藏",
    "handled": "已处理",
}
AI_LABELS = {
    "recommend": "建议关注",
    "verify": "需核实",
    "mismatch": "不匹配",
    "failed": "AI分析失败",
}
AI_PRIORITY = {"recommend": 0, "verify": 1, "mismatch": 2, "failed": 3}

CRITERIA_LABELS = {
    "model_chip": "型号与规格",
    "battery_health": "运行测试材料",
    "condition": "外观成色",
    "history": "维修与来源",
    "seller_type": "卖家画像",
    "shipping": "交易与物流",
    "seller_credit": "卖家信用",
    "price": "价格合理度",
    "accessories": "配件完整度",
    "warranty": "保修与凭证",
}

CRITERIA_STATUS_LABELS = {
    "PASS": "符合",
    "FAIL": "不符合",
    "WARNING": "注意",
    "WARN": "注意",
    "NEEDS_MANUAL_CHECK": "待核实",
}

RUN_TIMESTAMP_RE = re.compile(r"\[\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\]")
RUN_SPLIT_RE = re.compile(r"-{3,}\s*开始执行监控任务\s*-{3,}")
SAVED_RE = re.compile(r"本次运行共处理了\s*(\d+)\s*个新商品")


def _now() -> datetime:
    return datetime.now()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    return None


def _iso(value: datetime | None) -> str | None:
    return value.replace(microsecond=0).isoformat() if value else None


def _format_clock(value: Any) -> str:
    parsed = _parse_dt(value)
    if parsed is None:
        return "未排程"
    now = _now()
    if parsed.date() == now.date():
        return f"今天 {parsed:%H:%M}"
    if parsed.date() == (now.date() + timedelta(days=1)):
        return f"明天 {parsed:%H:%M}"
    if parsed.year == now.year:
        return f"{parsed:%m-%d %H:%M}"
    return f"{parsed:%Y-%m-%d %H:%M}"


def _short_time(value: Any, *, relative: bool = True) -> str:
    parsed = _parse_dt(value)
    if parsed is None:
        return "时间未知"
    now = _now()
    if relative and parsed.date() == now.date():
        return f"今天 {parsed:%H:%M}"
    if relative and parsed.date() == (now.date() - timedelta(days=1)):
        return f"昨天 {parsed:%H:%M}"
    if parsed.year == now.year:
        return f"{parsed:%m-%d %H:%M}"
    return f"{parsed:%Y-%m-%d %H:%M}"


def _normalize_task_name(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _strip_text(value: Any, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _criteria_label(key: str) -> str:
    if key in CRITERIA_LABELS:
        return CRITERIA_LABELS[key]
    known = {
        "screen": "屏幕情况",
        "storage": "存储配置",
        "network": "网络与锁",
        "appearance": "外观成色",
        "function": "功能状态",
    }
    if key in known:
        return known[key]
    return {
        "battery": "电池健康",
        "account_lock": "账号锁",
        "imei": "序列号与三码",
    }.get(key, key.replace("_", " ").strip() or "其他依据")


def _criteria_list(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    raw = analysis.get("criteria_analysis")
    if not isinstance(raw, dict):
        return []
    items: list[dict[str, Any]] = []
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        status = str(value.get("status") or "NEEDS_MANUAL_CHECK").upper()
        items.append(
            {
                "key": key,
                "label": _criteria_label(str(key)),
                "status": status,
                "status_label": CRITERIA_STATUS_LABELS.get(status, "待核实"),
                "comment": _strip_text(value.get("comment"), 500),
                "evidence": _strip_text(value.get("evidence"), 300),
                "persona": value.get("persona"),
            }
        )
    return items


def _missing_checks(analysis: dict[str, Any], criteria: list[dict[str, Any]], risk_tags: list[str]) -> list[str]:
    missing = [
        item["label"]
        for item in criteria
        if item["status"] in {"NEEDS_MANUAL_CHECK", "WARNING", "WARN"}
    ]
    if not missing:
        missing = [str(tag) for tag in risk_tags[:2] if str(tag).strip()]
    if not missing:
        missing = ["卖家提供的测试材料"]
    deduped: list[str] = []
    for item in missing:
        if item not in deduped:
            deduped.append(item)
    return deduped[:3]


def _task_lookup(tasks: Iterable[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_filename: dict[str, Any] = {}
    by_name: dict[str, Any] = {}
    for task in tasks:
        try:
            by_filename[build_result_filename(task.keyword)] = task
        except Exception:
            pass
        by_name[_normalize_task_name(task.task_name)] = task
    return by_filename, by_name


def _resolve_task_for_row(
    row: Any,
    by_filename: dict[str, Any],
    by_name: dict[str, Any],
) -> Any | None:
    filename = str(row["result_filename"] or "")
    task = by_filename.get(filename)
    if task is not None:
        return task
    return by_name.get(_normalize_task_name(row["task_name"]))


def _load_candidate_rows(tasks: Iterable[Any]) -> list[Any]:
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, result_filename, keyword, task_name, crawl_time, publish_time,
                   price, price_display, item_id, title, link, seller_nickname,
                   is_recommended, analysis_source, keyword_hit_count, status,
                   review_status, raw_json
            FROM result_items
            ORDER BY crawl_time DESC, id DESC
            """
        ).fetchall()
    return list(rows)


def _dedupe_rows(rows: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for row in rows:
        key = str(row["item_id"] or "").strip()
        if not key:
            key = str(row["link"] or "").split("&", 1)[0] or f"row-{row['id']}"
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _parse_analysis(row: Any) -> dict[str, Any]:
    try:
        raw = json.loads(row["raw_json"] or "{}")
    except (TypeError, ValueError):
        raw = {}
    analysis = raw.get("ai_analysis") or {}
    if not isinstance(analysis, dict):
        analysis = {}
    return {"raw": raw, "analysis": analysis}


def _status_score(status: str) -> int:
    return {
        "PASS": 92,
        "WARNING": 62,
        "WARN": 62,
        "FAIL": 24,
        "NEEDS_MANUAL_CHECK": 58,
    }.get(status.upper(), 65)


def _average(values: list[int], default: int) -> int:
    return round(sum(values) / len(values)) if values else default


def _build_gates(
    *,
    task: Any | None,
    keyword: str,
    product: dict[str, Any],
    seller: dict[str, Any],
    price: float | None,
):
    """按任务配置 + 商品客观事实算硬门槛。任务配置只提供参数，判定逻辑在底层。"""
    title = str(product.get("商品标题") or "")
    description = str(product.get("商品描述") or "")
    gpu_hint = looks_like_gpu_task(getattr(task, "keyword", ""), keyword, title)
    specs = extract_specs(title, description, gpu_hint=gpu_hint)
    gates = evaluate_gates(
        specs=specs,
        price=price,
        budget_min=getattr(task, "min_price", None),
        budget_max=getattr(task, "max_price", None),
        require_shipping=bool(getattr(task, "free_shipping", False)),
        allow_professional=task_allows_professional(
            getattr(task, "keyword", ""),
            getattr(task, "description", ""),
            keyword,
        ),
        seller_credit=str(seller.get("卖家信用等级") or ""),
    )
    return specs, gates


def _score_breakdown(
    analysis: dict[str, Any],
    criteria: list[dict[str, Any]],
    *,
    price: float | None,
    insight: dict[str, Any],
    verdict: str,
    gates=None,
) -> tuple[int | None, list[dict[str, Any]]]:
    if analysis.get("error") or not analysis:
        return None, []
    by_key = {item["key"]: item for item in criteria}

    def score_for(keys: tuple[str, ...], default: int) -> int:
        values = [_status_score(by_key[key]["status"]) for key in keys if key in by_key]
        return _average(values, default)

    match = score_for(("model_chip", "model", "storage", "screen"), 72)
    if verdict == "mismatch":
        match = min(match, 35)
    elif verdict == "verify":
        match = min(match, 70)
    seller = score_for(("seller_type", "seller_credit"), 65)
    evidence = score_for(
        ("history", "battery_health", "warranty", "accessories", "condition", "shipping"),
        60,
    )
    price_dimension, _price_source = price_score(price, insight, analysis.get("value_score"))
    dimensions = {
        "match": match,
        "price": price_dimension,
        "seller": seller,
        "evidence": evidence,
    }
    overall = resolve_overall(
        dimensions=dimensions,
        ai_value_score=analysis.get("value_score"),
        verdict=verdict,
        gates=gates,
    )
    return overall, breakdown_payload(dimensions)


def _decorate_candidate(row: Any, task: Any | None) -> dict[str, Any]:
    parsed = _parse_analysis(row)
    raw = parsed["raw"]
    analysis = parsed["analysis"]
    product = raw.get("商品信息") or {}
    seller = raw.get("卖家信息") or {}
    insight = raw.get("price_insight") or {}
    criteria = _criteria_list(analysis)
    risk_tags = [str(tag) for tag in (analysis.get("risk_tags") or []) if str(tag).strip()]
    analysis_source = str(row["analysis_source"] or analysis.get("analysis_source") or "")
    price_value = float(row["price"]) if row["price"] is not None else None
    specs, gates = _build_gates(
        task=task,
        keyword=str(row["keyword"] or ""),
        product=product,
        seller=seller,
        price=price_value,
    )
    analysis_failed = bool(analysis.get("error")) or (
        not analysis and analysis_source != "keyword"
    )
    verdict = resolve_verdict(
        analysis_failed=analysis_failed,
        ai_recommended=analysis.get("is_recommended") is True,
        criteria=criteria,
        risk_tags=risk_tags,
        gates=gates,
    )
    images = [str(url) for url in (product.get("商品图片列表") or []) if str(url).strip()]
    main_image = str(product.get("商品主图链接") or (images[0] if images else ""))
    if main_image and main_image not in images:
        images.insert(0, main_image)

    if analysis_source == "keyword":
        evidence = f"命中关键词规则：{row['keyword'] or '—'}。"
    else:
        evidence = _strip_text(
            analysis.get("value_summary") or analysis.get("reason") or "",
            220,
        )
    if gates.blocked:
        # 硬门槛否决时，AI 的溢美之词不能占满「判断依据」，必须先说清楚为什么被否。
        blocked_text = "；".join(f"{hit.label}：{hit.detail}" for hit in gates.blocks)
        evidence = _strip_text(
            f"底层硬门槛否决：{blocked_text}。{('原判断：' + evidence) if evidence else ''}",
            220,
        )
    if not evidence:
        evidence = "AI 尚未给出完整判断，可打开详情查看原始依据。"

    score = analysis.get("value_score")
    try:
        score = int(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    overall_score, score_breakdown = _score_breakdown(
        analysis,
        criteria,
        price=price_value,
        insight=insight,
        verdict=verdict,
        gates=gates,
    )

    review_status = str(row["review_status"] or "unseen")
    if review_status not in REVIEW_LABELS:
        review_status = "unseen"

    market_median = insight.get("market_median_price")
    market_scope = insight.get("market_scope")
    comparable = market_scope in {"model", "family"}
    if comparable:
        market_block = {
            "avg": market_median,
            "low": insight.get("market_low_price"),
            "high": insight.get("market_high_price"),
            "samples": insight.get("market_sample_count"),
            "label": insight.get("deal_label"),
        }
    elif market_scope == "insufficient" or specs.model_family:
        # 型号认得出来、或后端已明确判定「同型号样本不足」：宁可空缺，
        # 也不把跨型号均价摆出来当「市场价」。
        market_block = {
            "avg": None,
            "low": None,
            "high": None,
            "samples": insight.get("market_sample_count"),
            "label": insight.get("market_note") or "同型号样本不足",
        }
    else:
        # 手机/笔记本这类抽不出型号的品类，保留原有的关键词口径。
        market_block = {
            "avg": insight.get("market_avg_price") or insight.get("avg_price"),
            "low": insight.get("min_price"),
            "high": insight.get("max_price"),
            "samples": insight.get("observation_count"),
            "label": insight.get("deal_label"),
        }
    market_block["scope"] = market_scope
    market_block["comparable"] = comparable
    task_id = getattr(task, "id", None)
    task_name = getattr(task, "task_name", None) or _normalize_task_name(row["task_name"])
    return {
        "id": int(row["id"]),
        "item_id": str(row["item_id"] or ""),
        "title": _strip_text(row["title"], 160),
        "price": price_value,
        "price_display": row["price_display"] or (
            f"¥{price_value:.0f}" if price_value is not None else "价格未知"
        ),
        "image": main_image,
        "images": images[:9],
        "task_id": task_id,
        "task_name": task_name,
        "keyword": row["keyword"] or "",
        "crawl_time": row["crawl_time"],
        "crawl_label": _short_time(row["crawl_time"]),
        "publish_time": row["publish_time"],
        "publish_label": _short_time(row["publish_time"]) if row["publish_time"] else None,
        "location": product.get("发货地区") or "",
        "tags": [str(tag) for tag in (product.get("商品标签") or []) if str(tag).strip()],
        "views": product.get("浏览量"),
        "wants": product.get("“想要”人数"),
        "link": row["link"] or product.get("商品链接") or "",
        "seller": {
            "name": seller.get("卖家昵称") or row["seller_nickname"] or "匿名卖家",
            "credit": seller.get("卖家信用等级") or "暂无",
            "rating": seller.get("作为卖家的好评率") or "",
            "registered": seller.get("卖家注册时长") or "",
            "location": seller.get("卖家地区") or product.get("发货地区") or "",
            "signature": _strip_text(seller.get("卖家个性签名"), 80),
        },
        "review_status": review_status,
        "review_label": REVIEW_LABELS.get(review_status, "未查看"),
        "ai_verdict": verdict,
        "ai_label": AI_LABELS[verdict],
        "ai_reason": _strip_text(analysis.get("reason"), 500),
        "ai_summary": evidence,
        "ai_score": overall_score,
        "ai_value_score": score,
        "score_breakdown": score_breakdown,
        "risk_tags": risk_tags,
        "missing_checks": _missing_checks(analysis, criteria, risk_tags),
        "criteria": criteria,
        "recommended": analysis.get("is_recommended") is True and not gates.blocked,
        "analysis_source": analysis_source,
        "ai_failed": verdict == "failed",
        "hard_blocked": gates.blocked,
        "hard_gates": gates.as_list(),
        "specs": {
            "model": specs.model_family,
            "vram_gb": specs.vram_gb,
            "card_class": specs.card_class,
        },
        "market": market_block,
    }


def _matches_search(candidate: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        [
            candidate.get("title", ""),
            candidate.get("task_name", ""),
            candidate.get("keyword", ""),
            candidate.get("seller", {}).get("name", ""),
            candidate.get("ai_summary", ""),
            " ".join(candidate.get("risk_tags", [])),
        ]
    ).lower()
    return query.lower() in haystack


def _timestamp(value: Any) -> float:
    parsed = _parse_dt(value)
    try:
        return parsed.timestamp() if parsed else 0.0
    except (OSError, OverflowError, ValueError):
        return 0.0


def list_candidates(
    tasks: Iterable[Any],
    *,
    review_status: str = "all",
    ai_verdict: str = "all",
    task_id: int | None = None,
    query: str = "",
    sort: str = "smart",
    page: int = 1,
    limit: int = 12,
) -> dict[str, Any]:
    tasks = list(tasks)
    by_filename, by_name = _task_lookup(tasks)
    rows = _dedupe_rows(_load_candidate_rows(tasks))
    candidates: list[dict[str, Any]] = []
    for row in rows:
        task = _resolve_task_for_row(row, by_filename, by_name)
        candidate = _decorate_candidate(row, task)
        if task_id is not None and candidate.get("task_id") != task_id:
            continue
        if not _matches_search(candidate, query.strip()):
            continue
        candidates.append(candidate)

    counts = {
        "unseen": sum(1 for item in candidates if item["review_status"] == "unseen"),
        "favorite": sum(1 for item in candidates if item["review_status"] == "favorite"),
        "handled": sum(1 for item in candidates if item["review_status"] == "handled"),
    }
    ai_counts = {
        "all": len(candidates),
        "recommend": sum(1 for item in candidates if item["ai_verdict"] == "recommend"),
        "verify": sum(1 for item in candidates if item["ai_verdict"] == "verify"),
        "mismatch": sum(1 for item in candidates if item["ai_verdict"] == "mismatch"),
        "failed": sum(1 for item in candidates if item["ai_verdict"] == "failed"),
    }
    task_counts: dict[str, int] = {}
    for item in candidates:
        key = str(item.get("task_id") or "")
        task_counts[key] = task_counts.get(key, 0) + 1

    filtered = [
        item
        for item in candidates
        if (review_status == "all" or item["review_status"] == review_status)
        and (ai_verdict == "all" or item["ai_verdict"] == ai_verdict)
    ]

    if sort == "price_asc":
        filtered.sort(key=lambda item: (item["price"] is None, item["price"] or 0))
    elif sort == "price_desc":
        filtered.sort(key=lambda item: (item["price"] is None, -(item["price"] or 0)))
    elif sort == "newest":
        filtered.sort(key=lambda item: item.get("crawl_time") or "", reverse=True)
    elif sort == "score":
        filtered.sort(
            key=lambda item: (
                item.get("ai_score") is None,
                -(item.get("ai_score") or 0),
                AI_PRIORITY.get(item["ai_verdict"], 4),
                -_timestamp(item.get("crawl_time")),
            )
        )
    else:
        filtered.sort(
            key=lambda item: (
                item.get("ai_score") is None,
                -(item.get("ai_score") or 0),
                AI_PRIORITY.get(item["ai_verdict"], 4),
                -_timestamp(item.get("crawl_time")),
            )
        )

    total = len(filtered)
    start = max(0, (page - 1) * limit)
    items = filtered[start: start + limit]
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items,
        "counts": counts,
        "ai_counts": ai_counts,
        "task_counts": task_counts,
        "review_labels": REVIEW_LABELS,
        "ai_labels": AI_LABELS,
    }


def update_candidate_review(item_id: str, review_status: str) -> bool:
    valid = set(REVIEW_LABELS)
    if review_status not in valid:
        raise ValueError("review_status must be one of unseen, favorite, handled")
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        cursor = conn.execute(
            "UPDATE result_items SET review_status = ? WHERE item_id = ?",
            (review_status, item_id),
        )
        conn.commit()
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# 运行记录
# ---------------------------------------------------------------------------


def _parse_log_runs(task_id: int, task_name: str, *, is_running: bool = False) -> list[dict[str, Any]]:
    path = resolve_task_log_path(task_id, task_name)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return []

    chunks = RUN_SPLIT_RE.split(text)
    runs: list[dict[str, Any]] = []
    for chunk in chunks[1:]:
        if not chunk.strip():
            continue
        timestamps = RUN_TIMESTAMP_RE.findall(chunk)
        started = _parse_dt(timestamps[0]) if timestamps else None
        finished = _parse_dt(timestamps[-1]) if timestamps else None
        saved_match = SAVED_RE.search(chunk)
        saved = int(saved_match.group(1)) if saved_match else 0
        login_failed = ("登录失效/重定向" in chunk) or ("Login required" in chunk)
        browser_closed = ("浏览器意外关闭" in chunk) or ("异常退出" in chunk)
        normal_end = "正常结束" in chunk
        runtime_failure = ""
        for line in chunk.splitlines():
            if any(marker in line for marker in RUNTIME_FAILURE_MARKERS):
                runtime_failure = RUN_TIMESTAMP_RE.sub("", line).strip()

        if login_failed:
            status = "failed"
            error = "登录态失效，任务被重定向到登录页。"
        elif browser_closed:
            status = "partial" if saved else "failed"
            error = "浏览器意外关闭，运行未完整结束。"
        elif runtime_failure:
            # 例如 BrowserType.launch: EPERM（临时目录不可写）——把真实原因带出来，
            # 不要只说「日志中没有找到完整的结束标记」。
            status = "partial" if saved else "failed"
            error = _strip_text(runtime_failure, 200)
        elif normal_end:
            status = "completed" if saved else "no_new"
            error = None
        else:
            status = "running" if is_running else "failed"
            error = None if is_running else "日志中没有找到完整的结束标记。"
            if not is_running and saved:
                status = "partial"

        if is_running and chunk == chunks[-1] and not normal_end:
            status = "running"
            finished = None

        timeline = []
        for line in chunk.splitlines():
            match = RUN_TIMESTAMP_RE.search(line)
            if not match:
                continue
            body = line[match.end():].strip()
            if not body:
                continue
            if any(
                token in body
                for token in ("步骤", "筛选", "解析", "新商品", "通知", "结束", "失败", "登录", "异常", "保存")
            ):
                timeline.append({"time": match.group(1), "text": _strip_text(body, 120)})
        timeline = timeline[-5:]
        if error:
            timeline.append(
                {
                    "time": finished.strftime("%Y-%m-%d %H:%M:%S") if finished else "",
                    "text": error,
                }
            )

        started_iso = _iso(started)
        finished_iso = _iso(finished)
        runs.append(
            {
                "id": f"log-{task_id}-{len(runs) + 1}",
                "task_id": task_id,
                "task_name": task_name,
                "trigger": "scheduled",
                "status": status,
                "status_label": STATUS_LABELS.get(status, "未知"),
                "started_at": started_iso,
                "finished_at": finished_iso,
                "started_label": _short_time(started_iso),
                "finished_label": _short_time(finished_iso) if finished_iso else "",
                "duration_seconds": (
                    max(0, int((finished - started).total_seconds()))
                    if started and finished
                    else None
                ),
                "saved_count": saved,
                "discovered_count": saved,
                "pending_count": 0 if status in {"completed", "no_new"} else saved,
                "error_message": error,
                "summary": (
                    error
                    or ("本轮已完成，新增 %d 条结果。" % saved if saved else "本轮正常结束，未发现新的候选商品。")
                ),
                "timeline": timeline,
            }
        )
    return runs[-8:]


def _run_sort_key(run: dict[str, Any]) -> str:
    return str(run.get("started_at") or "")


def list_task_runs(
    task: Any,
    *,
    limit: int = 8,
    is_running: bool | None = None,
) -> list[dict[str, Any]]:
    run_service = TaskRunService()
    persisted = run_service.list_runs(int(task.id or 0), limit=limit)
    parsed = _parse_log_runs(
        int(task.id or 0),
        task.task_name,
        is_running=bool(task.is_running if is_running is None else is_running),
    )
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    parsed_by_start = {
        str(run.get("started_at") or ""): run for run in parsed if run.get("started_at")
    }
    for run in persisted:
        key = str(run.get("started_at") or "")
        seen.add(key)
        parsed_run = parsed_by_start.get(key) or {}
        merged.append(
            {
                **run,
                "started_label": _short_time(run.get("started_at")),
                "finished_label": _short_time(run.get("finished_at")) if run.get("finished_at") else "",
                "timeline": parsed_run.get("timeline") or [],
            }
        )
    for run in parsed:
        if str(run.get("started_at") or "") in seen:
            continue
        merged.append(run)
    merged.sort(key=_run_sort_key, reverse=True)
    return merged[:limit]


def _task_status(
    task: Any,
    *,
    paused_until: datetime | None,
    next_run_at: str | None,
) -> tuple[str, str, str]:
    if task.is_running:
        return "running", "运行中", "本轮正在执行"
    if not task.enabled:
        return "paused", "已暂停", "不会自动运行"
    if paused_until and paused_until > _now():
        return "cooldown", "冷却中", f"恢复 {paused_until:%H:%M}"
    return "waiting", "等待中", "按计划等待"


def list_task_workbench(tasks: Iterable[Any], scheduler: Any) -> dict[str, Any]:
    guard = FailureGuard()
    try:
        guard_state = guard._load().get("tasks", {})  # noqa: SLF001 - 只读熔断状态
    except Exception:
        guard_state = {}
    items: list[dict[str, Any]] = []
    counts = {"all": 0, "running": 0, "waiting": 0, "cooldown": 0, "paused": 0}

    for task in tasks:
        next_run = None
        try:
            next_run = _iso(scheduler.get_next_run_time(task.id)) if scheduler else None
        except Exception:
            next_run = None
        entry = guard_state.get(task.task_name) or {}
        paused_until = _parse_dt(entry.get("paused_until")) if isinstance(entry, dict) else None
        status, status_label, status_detail = _task_status(
            task,
            paused_until=paused_until,
            next_run_at=next_run,
        )
        runs = list_task_runs(task, limit=5)
        latest = runs[0] if runs else None
        if task.is_running:
            latest = {
                "id": "active",
                "status": "running",
                "status_label": "运行中",
                "started_at": latest.get("started_at") if latest else None,
                "saved_count": 0,
                "summary": "本轮正在抓取与分析。",
                "timeline": [],
            }
        counts["all"] += 1
        counts[status] = counts.get(status, 0) + 1
        items.append(
            {
                "id": task.id,
                "task_name": task.task_name,
                "keyword": task.keyword,
                "min_price": task.min_price,
                "max_price": task.max_price,
                "budget": _budget_label(task.min_price, task.max_price),
                "enabled": task.enabled,
                "is_running": task.is_running,
                "cron": task.cron,
                "next_run_at": next_run,
                "next_run_label": _format_clock(next_run) if next_run else "未排程",
                "status": status,
                "status_label": status_label,
                "status_detail": status_detail,
                "paused_until": _iso(paused_until),
                "latest_run": latest,
                "recent_runs": runs,
                "decision_mode": task.decision_mode,
                "account_strategy": task.account_strategy,
                "account_state_file": task.account_state_file,
                "description": _strip_text(task.description, 400),
                "title_include_keywords": task.title_include_keywords,
                "title_exclude_keywords": task.title_exclude_keywords,
            }
        )
    items.sort(key=lambda item: (item["status"] != "running", item["id"] or 0))
    return {"items": items, "counts": counts}


def _budget_label(min_price: Any, max_price: Any) -> str:
    low = str(min_price).strip() if min_price not in (None, "") else ""
    high = str(max_price).strip() if max_price not in (None, "") else ""
    if low and high:
        return f"¥{low}–{high}"
    if high:
        return f"≤¥{high}"
    if low:
        return f"≥¥{low}"
    return "不限预算"


# ---------------------------------------------------------------------------
# 账号 / 异常 / 汇总
# ---------------------------------------------------------------------------


def _state_dir() -> str:
    raw = env_manager.get_value("ACCOUNT_STATE_DIR", "state") or "state"
    return raw.strip().strip("\"'")


ACCOUNT_PATH_RE = re.compile(r"使用登录状态\s+([^\s\r\n]+\.json)", re.IGNORECASE)

# 登录态失效：只有这一类才需要「重新扫码」
LOGIN_FAILURE_MARKERS = (
    "登录失效/重定向",
    "Login required",
    "跳转到登录页",
    "登录状态文件不存在",
    "未找到可用的登录状态文件",
)
# 其它运行失败：登录态可能没问题，失败原因在别处（浏览器起不来、风控、磁盘等）
RUNTIME_FAILURE_MARKERS = (
    "本次尝试失败",
    "因异常而终止",
    "已暂停重试",
    "FAIL_SYS_USER_VALIDATE",
    "BrowserType.launch",
    "net::ERR_",
)

EVENT_OK = "ok"
EVENT_LOGIN = "login"
EVENT_RUNTIME = "runtime"


def _account_name_from_path(path: str) -> str:
    return os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]


def _classify_failure_line(line: str) -> str | None:
    if any(marker in line for marker in LOGIN_FAILURE_MARKERS):
        return EVENT_LOGIN
    if any(marker in line for marker in RUNTIME_FAILURE_MARKERS):
        return EVENT_RUNTIME
    return None


def _collect_account_events_from_logs() -> dict[str, dict[str, Any]]:
    """从历史运行日志恢复每个账号最近一次运行事件。

    按行跟踪「当前生效账号」：轮换重试时一个 chunk 里会依次出现 acc_1、acc_2，
    谁那条线上失败就记在谁头上，成功的那次也不会被前面的失败盖掉。
    """
    events: dict[str, dict[str, Any]] = {}
    log_paths = glob.glob(os.path.join("logs", "*.log"))
    for log_path in log_paths:
        try:
            if os.path.getsize(log_path) > 12 * 1024 * 1024:
                continue
            with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        for chunk in RUN_SPLIT_RE.split(text)[1:]:
            timestamps = [_parse_dt(value) for value in RUN_TIMESTAMP_RE.findall(chunk)]
            timestamps = [value for value in timestamps if value]
            if not timestamps:
                continue
            started = timestamps[0]
            finished = timestamps[-1]

            current_account: str | None = None
            failures: dict[str, dict[str, Any]] = {}
            seen_accounts: list[str] = []
            for line in chunk.splitlines():
                account_match = ACCOUNT_PATH_RE.search(line)
                if account_match:
                    current_account = _account_name_from_path(account_match.group(1))
                    if current_account not in seen_accounts:
                        seen_accounts.append(current_account)
                    continue
                kind = _classify_failure_line(line)
                if kind is None or not current_account:
                    continue
                stamp = RUN_TIMESTAMP_RE.search(line)
                at = _parse_dt(stamp.group(1)) if stamp else finished
                failures[current_account] = {
                    "name": current_account,
                    "kind": kind,
                    "status": "failed",
                    "at": at or finished,
                    "started_at": started,
                    "reason": _strip_text(line, 180),
                    "log_file": os.path.basename(log_path),
                }

            if not seen_accounts:
                continue
            for name in seen_accounts:
                event = failures.get(name) or {
                    "name": name,
                    "kind": EVENT_OK,
                    "status": "ok",
                    "at": finished,
                    "started_at": started,
                    "reason": "",
                    "log_file": os.path.basename(log_path),
                }
                current = events.get(name)
                if current is None or event["at"] > current["at"]:
                    events[name] = event
    return events


def list_account_health() -> list[dict[str, Any]]:
    state_dir = _state_dir()
    if not os.path.isdir(state_dir):
        return []
    events = _collect_account_events_from_logs()
    accounts: list[dict[str, Any]] = []
    now = _now()
    for filename in sorted(os.listdir(state_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(state_dir, filename)
        try:
            stat = os.stat(path)
        except OSError:
            continue
        modified = datetime.fromtimestamp(stat.st_mtime)
        age_days = max(0, (now - modified).days)
        valid = True
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            valid = bool(payload)
        except Exception:
            valid = False
        name = filename[:-5]
        event = events.get(name)
        stale = age_days > 14
        needs_update = (not valid) or stale
        reason = ""
        last_failure_at = None
        last_success_at = None
        last_run_status = "none"
        last_run_at = None
        last_run_reason = ""
        run_failed = False
        if event:
            kind = event.get("kind") or (
                EVENT_OK if event.get("status") == "ok" else EVENT_LOGIN
            )
            last_run_at = _iso(event["at"])
            if kind == EVENT_OK:
                last_run_status = "ok"
                last_success_at = last_run_at
            elif kind == EVENT_LOGIN:
                last_failure_at = last_run_at
                last_run_status = "failed"
                last_run_reason = event.get("reason") or "登录失效"
                # 扫码/重新导入登录态会更新文件 mtime；之后视为已自动恢复。
                if modified.timestamp() > event["at"].timestamp() + 120:
                    last_failure_at = None
                    last_success_at = _iso(modified)
                    last_run_status = "ok"
                    last_run_reason = ""
                else:
                    needs_update = True
                    reason = f"{_short_time(last_failure_at)} 检测到登录失效，请重新扫码登录。"
            else:
                # 非登录原因的失败：登录态可能没问题，但绝不能显示成「运行正常」。
                last_run_status = "failed"
                last_run_reason = event.get("reason") or "运行异常"
                run_failed = True
        if not valid:
            needs_update = True
            reason = "登录态文件无法读取，请重新扫码登录。"
        elif stale and not last_failure_at:
            needs_update = True
            reason = f"登录态已 {age_days} 天未更新，请确认是否仍有效。"

        if needs_update:
            status = "needs_update"
            status_label = "需要更新"
        elif run_failed:
            status = "warning"
            status_label = "上次运行失败"
            reason = f"{_short_time(last_run_at)} 运行失败（不是登录问题）：{_strip_text(last_run_reason, 120)}"
        else:
            status = "ok"
            status_label = "可用"

        accounts.append(
            {
                "name": name,
                "file": filename,
                "updated_at": modified.replace(microsecond=0).isoformat(),
                "updated_label": _short_time(modified.isoformat()),
                "age_days": age_days,
                "status": status,
                "status_label": status_label,
                "reason": reason,
                "last_failure_at": last_failure_at,
                "last_failure_label": _short_time(last_failure_at) if last_failure_at else "",
                "last_success_at": last_success_at,
                "last_success_label": _short_time(last_success_at) if last_success_at else "",
                "last_run_status": last_run_status,
                "last_run_at": last_run_at,
                "last_run_label": _short_time(last_run_at) if last_run_at else "",
                "last_run_reason": _strip_text(last_run_reason, 220),
            }
        )
    # 需要重扫的排最前，其次上次运行失败的，最后正常的。
    status_rank = {"needs_update": 0, "warning": 1, "ok": 2}
    accounts.sort(
        key=lambda item: (
            status_rank.get(item["status"], 3),
            -_timestamp(item.get("last_failure_at") or item.get("last_run_at")),
            item["name"],
        )
    )
    return accounts


def _ai_failure_count(candidates: list[dict[str, Any]]) -> int:
    return sum(1 for item in candidates if item["ai_verdict"] == "failed")


def build_issues(
    *,
    tasks_payload: dict[str, Any],
    accounts: list[dict[str, Any]],
    ai_failures: int,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for task in tasks_payload.get("items", []):
        if task["status"] == "paused":
            continue
        latest = task.get("latest_run") or {}
        if task["status"] == "cooldown":
            issues.append(
                {
                    "id": f"task-cooldown-{task['id']}",
                    "type": "task",
                    "title": f"{task['task_name']} 正在冷却",
                    "detail": task.get("status_detail") or "任务暂停等待恢复。",
                    "action_label": "查看任务",
                    "action_route": f"/tasks?task={task['id']}",
                    "severity": "warning",
                }
            )
        elif latest.get("status") == "failed":
            issues.append(
                {
                    "id": f"task-failed-{task['id']}",
                    "type": "task",
                    "title": f"{task['task_name']} 上一轮未完成",
                    "detail": latest.get("error_message") or latest.get("summary") or "需要检查登录态或日志。",
                    "action_label": "查看任务",
                    "action_route": f"/tasks?task={task['id']}",
                    "severity": "warning",
                }
            )
        elif latest.get("status") == "partial":
            issues.append(
                {
                    "id": f"task-partial-{task['id']}",
                    "type": "task",
                    "title": f"{task['task_name']} 上一轮部分完成",
                    "detail": latest.get("summary") or "已有结果已保留，可查看运行记录。",
                    "action_label": "查看任务",
                    "action_route": f"/tasks?task={task['id']}",
                    "severity": "warning",
                }
            )
    for account in accounts:
        if account["status"] == "needs_update":
            issues.append(
                {
                    "id": f"account-{account['name']}",
                    "type": "account",
                    "title": (
                        f"账号 {account['name']} 登录失效"
                        if account.get("last_failure_at")
                        else f"账号 {account['name']} 需要更新登录信息"
                    ),
                    "detail": account.get("reason") or "建议重新扫码登录闲鱼账号。",
                    "action_label": "重新扫码",
                    "action_route": "/accounts?action=scan",
                    "severity": "warning",
                }
            )
        elif account["status"] == "warning":
            # 登录态没问题，但上一轮实际跑失败了：不能悄悄当成正常。
            issues.append(
                {
                    "id": f"account-run-{account['name']}",
                    "type": "account",
                    "title": f"账号 {account['name']} 上次运行失败",
                    "detail": account.get("reason") or account.get("last_run_reason") or "请查看任务日志。",
                    "action_label": "查看任务",
                    "action_route": "/tasks",
                    "severity": "info",
                }
            )
    if ai_failures:
        issues.append(
            {
                "id": "ai-analysis-failures",
                "type": "ai",
                "title": f"{ai_failures} 条商品 AI 分析失败",
                "detail": "分析失败不会把商品判为不合格，可单独筛选后重新查看。",
                "action_label": "查看记录",
                "action_route": "/results?ai=failed",
                "severity": "info",
            }
        )
    return issues


def build_summary(
    tasks: Iterable[Any],
    scheduler: Any,
    *,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tasks = list(tasks)
    tasks_payload = list_task_workbench(tasks, scheduler)
    accounts = list_account_health()
    if candidates is None:
        candidates = list_candidates(tasks, page=1, limit=100000)["items"]
    ai_failures = _ai_failure_count(candidates)
    issues = build_issues(
        tasks_payload=tasks_payload,
        accounts=accounts,
        ai_failures=ai_failures,
    )
    today = _now().date().isoformat()
    today_count = 0
    try:
        with sqlite_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM result_items WHERE substr(crawl_time, 1, 10) = ?",
                (today,),
            ).fetchone()
            today_count = int(row["n"] if row else 0)
    except Exception:
        today_count = 0

    try:
        notification_settings = load_notification_settings()
        channels = build_configured_channels(notification_settings)
    except Exception:
        channels = []
    try:
        from src.services.daily_report_service import daily_report_hour, is_daily_report_enabled

        report_enabled = bool(is_daily_report_enabled())
        report_hour = daily_report_hour()
    except Exception:
        report_enabled = False
        report_hour = None

    ai_configured = bool(env_manager.get_value("OPENAI_API_KEY", ""))
    ai_model = env_manager.get_value("OPENAI_MODEL_NAME", "")
    return {
        "task_count": len(tasks),
        "enabled_task_count": sum(1 for task in tasks if task.enabled),
        "running_count": sum(1 for task in tasks if task.is_running),
        "today_count": today_count,
        "pending_count": len(issues),
        "issues": issues,
        "accounts": accounts,
        "account_count": len(accounts),
        "account_alert_count": sum(1 for account in accounts if account["status"] != "ok"),
        "ai_configured": ai_configured,
        "ai_model": ai_model,
        "notification_channels": channels,
        "notification_configured": bool(channels),
        "daily_report_enabled": report_enabled,
        "daily_report_hour": report_hour,
        "last_updated": _iso(_now()),
    }
