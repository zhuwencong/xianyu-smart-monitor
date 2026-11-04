#!/usr/bin/env python3
"""闲鱼智能监控 · WorkBuddy 技能桥接脚本。

只用标准库，不依赖项目里的 .venv —— 技能被安装到任意目录都能跑。
默认访问 http://127.0.0.1:8000（可用 --base-url 或环境变量
XIANYU_MONITOR_BASE_URL 覆盖）。

默认输出**精简投影**（只保留判断需要用的字段），加 --raw 可拿服务端原始 JSON。
输出统一为 UTF-8，避免 Windows GBK 控制台把中文商品标题打崩。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = os.environ.get("XIANYU_MONITOR_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_TIMEOUT = float(os.environ.get("XIANYU_MONITOR_TIMEOUT", "20"))

# Windows 控制台默认是 GBK，直接 print 中文商品标题会抛 UnicodeEncodeError。
# 统一按 UTF-8 输出；被 agent 以管道读取时这也是唯一正确的选择。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def die(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    raise SystemExit(1)


def request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
):
    url = base_url.rstrip("/") + path
    payload = None
    headers = {"Accept": "application/json", "User-Agent": "workbuddy-xianyu-skill/0.1.0"}
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        try:
            detail = json.loads(detail).get("detail", detail)
        except (ValueError, AttributeError):
            pass
        die(f"监控服务返回 HTTP {exc.code}：{str(detail)[:400]}")
    except urllib.error.URLError as exc:
        die(
            f"连不上监控服务 {base_url}（{exc.reason}）。"
            "请先在本机启动：python -m src.app；若端口不同，用 --base-url 指定。"
        )
    except TimeoutError:
        die(f"请求 {path} 超时（{timeout}s）。可在命令后加 --timeout 调大。")


def split_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace("，", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def clip(value, limit: int):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def clean_link(link: str | None) -> str:
    """去掉闲鱼链接上的追踪参数，只保留 item?id=xxx。"""
    if not link:
        return ""
    parsed = urllib.parse.urlsplit(link)
    item_id = urllib.parse.parse_qs(parsed.query).get("id")
    if item_id:
        return f"https://www.goofish.com/item?id={item_id[0]}"
    return link.split("?", 1)[0]


def compact_candidate(item: dict) -> dict:
    return {
        "item_id": item.get("item_id"),
        "title": clip(item.get("title"), 70),
        "price": item.get("price"),
        "ai_label": item.get("ai_label"),
        "ai_score": item.get("ai_score"),
        "ai_summary": clip(item.get("ai_summary"), 140),
        "missing_checks": item.get("missing_checks") or [],
        "risk_tags": item.get("risk_tags") or [],
        "seller": (item.get("seller") or {}).get("name"),
        "seller_credit": (item.get("seller") or {}).get("credit"),
        "task_name": item.get("task_name"),
        "crawl_label": item.get("crawl_label"),
        "location": item.get("location"),
        "review_status": item.get("review_status"),
        "link": clean_link(item.get("link")),
    }


def compact_task(item: dict) -> dict:
    latest = item.get("latest_run") or {}
    return {
        "task_id": item.get("id"),
        "task_name": item.get("task_name"),
        "status": item.get("status_label"),
        "status_detail": clip(item.get("status_detail"), 80),
        "keyword": item.get("keyword"),
        "budget": item.get("budget"),
        "enabled": item.get("enabled"),
        "is_running": item.get("is_running"),
        "cron": item.get("cron"),
        "next_run": item.get("next_run_label"),
        "latest_run": {
            "status": latest.get("status_label"),
            "started_at": latest.get("started_at"),
            "saved_count": latest.get("saved_count"),
            "summary": clip(latest.get("summary"), 100),
        }
        if latest
        else None,
    }


def compact_run(run: dict) -> dict:
    return {
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "status": run.get("status_label") or run.get("status"),
        "saved_count": run.get("saved_count"),
        "summary": clip(run.get("summary"), 160),
    }


def emit(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xy.py",
        description="闲鱼智能监控 · WorkBuddy 技能桥（查询候选商品、任务与运行记录）",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="监控服务地址")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="单次请求超时（秒）")
    parser.add_argument("--raw", action="store_true", help="输出服务端原始 JSON（字段多、耗 token）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="工作台整体状态与待处理异常")
    sub.add_parser("issues", help="待处理的异常")
    sub.add_parser("tasks", help="任务列表与状态")

    candidates = sub.add_parser("candidates", help="候选商品列表")
    candidates.add_argument("--review-status", default="all", choices=["all", "unseen", "favorite", "handled"])
    candidates.add_argument(
        "--verdict",
        default="all",
        choices=["all", "recommend", "verify", "mismatch", "failed"],
        help="AI 判断筛选",
    )
    candidates.add_argument("--task-id", type=int)
    candidates.add_argument("--query", default="", help="按标题/任务名/卖家搜索")
    candidates.add_argument(
        "--sort",
        default="smart",
        choices=["smart", "score", "newest", "price_asc", "price_desc"],
    )
    candidates.add_argument("--page", type=int, default=1)
    candidates.add_argument("--limit", type=int, default=12)

    runs = sub.add_parser("runs", help="某个任务的最近运行记录")
    runs.add_argument("--task-id", type=int, required=True)
    runs.add_argument("--limit", type=int, default=5)

    mark = sub.add_parser("mark", help="标记候选商品的处理状态")
    mark.add_argument("--item-id", required=True, help="闲鱼商品 ID（候选里的 item_id）")
    mark.add_argument("--status", required=True, choices=["unseen", "favorite", "handled"])

    start = sub.add_parser("start", help="立即运行任务（会真实访问闲鱼）")
    start.add_argument("--task-id", type=int, required=True)

    stop = sub.add_parser("stop", help="停止任务")
    stop.add_argument("--task-id", type=int, required=True)

    create = sub.add_parser("create", help="创建监控任务")
    create.add_argument("--task-name", required=True)
    create.add_argument("--keyword", required=True)
    create.add_argument("--mode", default="keyword", choices=["keyword", "ai"])
    create.add_argument("--description", default="", help="ai 模式下必填：详细需求")
    create.add_argument("--keyword-rules", default="", help="keyword 模式下必填：逗号分隔")
    create.add_argument("--min-price")
    create.add_argument("--max-price")
    create.add_argument("--max-pages", type=int, default=3)
    create.add_argument("--region")
    create.add_argument("--cron")
    create.add_argument("--account-file", default=None, help="例如 acc_1.json")
    create.add_argument("--no-free-shipping", action="store_true", help="不限制包邮")

    job = sub.add_parser("job", help="查询 AI 任务创建进度")
    job.add_argument("--job-id", required=True)

    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    base = args.base_url
    timeout = args.timeout
    raw = args.raw
    command = args.command

    if command == "status":
        data = request(base, "/api/workbench/summary", timeout=timeout)
        if raw:
            emit(data)
            return 0
        emit(
            {
                "task_count": data.get("task_count"),
                "enabled_task_count": data.get("enabled_task_count"),
                "running_count": data.get("running_count"),
                "today_count": data.get("today_count"),
                "pending_count": data.get("pending_count"),
                "account_count": data.get("account_count"),
                "account_alert_count": data.get("account_alert_count"),
                "ai_configured": data.get("ai_configured"),
                "ai_model": data.get("ai_model"),
                "notification_channels": data.get("notification_channels"),
                "daily_report_enabled": data.get("daily_report_enabled"),
                "daily_report_hour": data.get("daily_report_hour"),
                "issues": [
                    {
                        "type": issue.get("type"),
                        "title": issue.get("title"),
                        "detail": clip(issue.get("detail"), 120),
                        "severity": issue.get("severity"),
                    }
                    for issue in (data.get("issues") or [])
                ],
            }
        )
        return 0

    if command == "issues":
        data = request(base, "/api/workbench/issues", timeout=timeout)
        if raw:
            emit(data)
            return 0
        emit(
            {
                "pending_count": data.get("pending_count"),
                "issues": [
                    {
                        "type": issue.get("type"),
                        "title": issue.get("title"),
                        "detail": clip(issue.get("detail"), 140),
                        "severity": issue.get("severity"),
                    }
                    for issue in (data.get("issues") or [])
                ],
            }
        )
        return 0

    if command == "tasks":
        data = request(base, "/api/workbench/tasks", timeout=timeout)
        if raw:
            emit(data)
            return 0
        emit(
            {
                "counts": data.get("counts"),
                "tasks": [compact_task(item) for item in (data.get("items") or [])],
            }
        )
        return 0

    if command == "candidates":
        params = {
            "review_status": args.review_status,
            "ai_verdict": args.verdict,
            "sort": args.sort,
            "page": str(max(1, args.page)),
            "limit": str(min(max(1, args.limit), 60)),
        }
        if args.task_id is not None:
            params["task_id"] = str(args.task_id)
        if args.query:
            params["q"] = args.query
        data = request(base, f"/api/workbench/candidates?{urllib.parse.urlencode(params)}", timeout=timeout)
        if raw:
            emit(data)
            return 0
        emit(
            {
                "total": data.get("total"),
                "page": data.get("page"),
                "limit": data.get("limit"),
                "counts": data.get("counts"),
                "items": [compact_candidate(item) for item in (data.get("items") or [])],
            }
        )
        return 0

    if command == "runs":
        limit = min(max(1, args.limit), 20)
        data = request(base, f"/api/workbench/tasks/{args.task_id}/runs?limit={limit}", timeout=timeout)
        if raw:
            emit(data)
            return 0
        emit(
            {
                "task_id": data.get("task_id"),
                "task_name": data.get("task_name"),
                "runs": [compact_run(run) for run in (data.get("runs") or [])],
            }
        )
        return 0

    if command == "mark":
        emit(
            request(
                base,
                f"/api/workbench/candidates/{urllib.parse.quote(str(args.item_id), safe='')}",
                method="PATCH",
                body={"review_status": args.status},
                timeout=timeout,
            )
        )
        return 0

    if command == "start":
        emit(request(base, f"/api/tasks/start/{args.task_id}", method="POST", timeout=timeout))
        return 0

    if command == "stop":
        emit(request(base, f"/api/tasks/stop/{args.task_id}", method="POST", timeout=timeout))
        return 0

    if command == "job":
        emit(
            request(
                base,
                f"/api/tasks/generate-jobs/{urllib.parse.quote(str(args.job_id), safe='')}",
                timeout=timeout,
            )
        )
        return 0

    if command == "create":
        payload = {
            "task_name": args.task_name,
            "keyword": args.keyword,
            "decision_mode": args.mode,
            "max_pages": args.max_pages,
            "free_shipping": not args.no_free_shipping,
            "min_price": args.min_price,
            "max_price": args.max_price,
            "region": args.region,
            "cron": args.cron,
            "account_state_file": args.account_file,
            "keyword_rules": split_keywords(args.keyword_rules),
            "description": args.description,
        }
        if args.mode == "keyword" and not payload["keyword_rules"]:
            die("--mode keyword 时必须提供 --keyword-rules（逗号分隔）")
        if args.mode == "ai" and not args.description.strip():
            die("--mode ai 时必须提供 --description（详细需求）")
        emit(request(base, "/api/tasks/generate", method="POST", body=payload, timeout=timeout))
        return 0

    die(f"未知命令：{command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
