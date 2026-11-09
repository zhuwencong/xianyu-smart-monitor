"""重跑历史上 AI 分析失败的商品。

背景：2026-11-05 ~ 11-06 期间服务进程继承了失效的本地代理（127.0.0.1:1097），
所有 AI 调用都以 ``Connection error.`` 失败；代理问题修好后新商品恢复正常，
但库里那批历史结果仍然是失败态，而项目没有“重新分析”入口，只能靠这个脚本刷。

脚本做三件事：
1. 读出 result_items 里 ai_analysis.error 非空的记录（默认全部错误类型）；
2. 按原任务配置重新下载图片 + 调 AI，跑一遍硬门槛；
3. 把新结论写回 SQLite（raw_json 与冗余列同时更新），前端刷新即可看到。

用法：
    # 先看会处理哪些，不动库
    .venv\\Scripts\\python.exe scripts\\reanalyze_failed.py --dry-run

    # 只重跑 5 条试水
    .venv\\Scripts\\python.exe scripts\\reanalyze_failed.py --limit 5

    # 全量重跑（默认并发 2，逐条串行提交 DB）
    .venv\\Scripts\\python.exe scripts\\reanalyze_failed.py

    # 只捞某类错误
    .venv\\Scripts\\python.exe scripts\\reanalyze_failed.py --only-error "Connection error"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
os.chdir(BASE)
sys.path.insert(0, str(BASE))

# 必须早于 src.* 的导入：AI 客户端在 import 阶段就会读代理环境变量。
from src.core.proxy_env import strip_inherited_proxy_env

strip_inherited_proxy_env(label="重分析脚本")

from src.ai_handler import (  # noqa: E402  导入顺序受代理清理约束
    download_all_images,
    get_ai_analysis,
    send_ntfy_notification,
)
from src.services.item_analysis_dispatcher import (  # noqa: E402
    ItemAnalysisDispatcher,
    ItemAnalysisJob,
)

DB_PATH = BASE / "data" / "app.sqlite3"


async def _noop_async(*_args, **_kwargs):
    return None


async def _noop_saver(_record, _keyword):
    return True


def _build_dispatcher(notify) -> ItemAnalysisDispatcher:
    """只借用它的硬门槛逻辑；采集/通知/落盘都由本脚本自己控制。"""
    return ItemAnalysisDispatcher(
        concurrency=1,
        skip_ai_analysis=False,
        seller_loader=_noop_async,
        image_downloader=_noop_async,
        ai_analyzer=_noop_async,
        notifier=notify,
        saver=_noop_saver,
    )


def load_tasks() -> dict[str, dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT task_name, keyword, decision_mode, analyze_images,
               ai_prompt_base_file, ai_prompt_criteria_file,
               min_price, max_price, free_shipping, keyword_rules_json
        FROM tasks
        """
    ).fetchall()
    conn.close()
    return {str(row["task_name"]): dict(row) for row in rows}


def _normalize_name(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def resolve_task(tasks: dict[str, dict], task_name: str, keyword: str) -> dict | None:
    """按任务名找配置，容忍改名/尾空格/按关键词匹配。

    历史结果里的任务名可能是旧名字（例如 "GTX 1070 " 带尾空格），任务被改名或
    重建后就对不上了；这里逐级降级匹配，避免整批记录被跳过。
    """
    if task_name in tasks:
        return tasks[task_name]

    normalized = _normalize_name(task_name)
    for name, task in tasks.items():
        if _normalize_name(name) == normalized:
            return task

    normalized_keyword = _normalize_name(keyword)
    if normalized_keyword:
        for task in tasks.values():
            if _normalize_name(task.get("keyword")) == normalized_keyword:
                return task
    return None


def load_prompt(task: dict) -> str:
    """与 spider_v2 里的拼装方式保持一致。"""
    base_file = str(task.get("ai_prompt_base_file") or "").strip()
    criteria_file = str(task.get("ai_prompt_criteria_file") or "").strip()
    if not base_file or not criteria_file:
        return ""
    try:
        base_text = (BASE / base_file).read_text(encoding="utf-8")
        criteria_text = (BASE / criteria_file).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"   [prompt] 读取失败（任务 {task.get('task_name')}）: {exc}")
        return ""
    return base_text.replace("{{CRITERIA_SECTION}}", criteria_text)


def load_failed_records(
    only_error: str,
    task_filter: str = "",
    force: bool = False,
) -> list[tuple[sqlite3.Row, dict]]:
    """挑出待重分析记录。

    force=True 时不再只看失败记录——改完判据后要把“已分析但结论过期”的
    候选按新口径重打一遍，否则老结论会一直挂在库里。
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, task_name, keyword, crawl_time, raw_json FROM result_items ORDER BY id"
    ).fetchall()
    conn.close()

    picked: list[tuple[sqlite3.Row, dict]] = []
    needle = (only_error or "").strip().lower()
    wanted_task = _normalize_name(task_filter)
    for row in rows:
        if wanted_task and _normalize_name(row["task_name"]) != wanted_task:
            continue
        try:
            record = json.loads(row["raw_json"] or "{}")
        except json.JSONDecodeError:
            continue
        analysis = record.get("ai_analysis") or {}
        error_text = str(analysis.get("error") or "").strip()
        if not error_text and not force:
            continue
        if needle and needle not in error_text.lower():
            continue
        picked.append((row, record))
    return picked


def build_job(row: sqlite3.Row, record: dict, task: dict, prompt: str) -> ItemAnalysisJob:
    seller = record.get("卖家信息") or {}
    return ItemAnalysisJob(
        keyword=str(row["keyword"] or record.get("搜索关键字") or ""),
        task_name=str(task.get("task_name") or row["task_name"] or ""),
        decision_mode="ai",
        analyze_images=bool(task.get("analyze_images")),
        prompt_text=prompt,
        keyword_rules=tuple(json.loads(task.get("keyword_rules_json") or "[]")),
        final_record=record,
        seller_id=None,
        zhima_credit_text=seller.get("卖家芝麻信用"),
        registration_duration_text=str(seller.get("卖家注册时长") or ""),
        budget_min=task.get("min_price") or None,
        budget_max=task.get("max_price") or None,
        require_shipping=bool(task.get("free_shipping")),
    )


async def analyze_one(
    row: sqlite3.Row,
    record: dict,
    task: dict,
    prompt: str,
    *,
    notify: bool,
    write_lock: asyncio.Lock,
) -> tuple[str, str]:
    item = record.get("商品信息") or {}
    item_id = str(item.get("商品ID") or "")
    image_paths: list[str] = []

    if task.get("analyze_images"):
        image_urls = item.get("商品图片列表") or []
        if image_urls:
            try:
                image_paths = await download_all_images(
                    item_id, image_urls, task.get("task_name") or row["task_name"]
                )
            except Exception as exc:  # 图片挂了也继续，文本照样能判
                print(f"   [图片] 商品 {item_id} 下载失败，降级为纯文本分析: {exc}")

    try:
        analysis = await get_ai_analysis(record, image_paths, prompt)
    finally:
        for path in image_paths:
            try:
                os.remove(path)
            except OSError:
                pass

    if not isinstance(analysis, dict) or not analysis:
        return "fail", "AI 返回空结果"

    dispatcher = _build_dispatcher(send_ntfy_notification if notify else _noop_async)
    analysis.setdefault("analysis_source", "ai")
    analysis.setdefault("keyword_hit_count", 0)
    analysis = dispatcher._apply_hard_gates(build_job(row, record, task, prompt), record, analysis)

    record["ai_analysis"] = analysis
    async with write_lock:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        try:
            conn.execute(
                """
                UPDATE result_items
                SET raw_json = ?, is_recommended = ?, analysis_source = ?,
                    keyword_hit_count = ?
                WHERE id = ?
                """,
                (
                    json.dumps(record, ensure_ascii=False),
                    1 if analysis.get("is_recommended") else 0,
                    analysis.get("analysis_source"),
                    int(analysis.get("keyword_hit_count") or 0),
                    row["id"],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    if notify and analysis.get("is_recommended"):
        try:
            await send_ntfy_notification(item, analysis.get("reason") or "无")
        except Exception as exc:
            print(f"   [通知] 推送失败: {exc}")

    verdict = "推荐" if analysis.get("is_recommended") else "不推荐"
    return "ok", verdict


async def run(args) -> int:
    tasks = load_tasks()
    records = load_failed_records(args.only_error, args.task, args.force)
    if args.limit > 0:
        records = records[: args.limit]

    print(
        f"待重分析: {len(records)} 条"
        f"（任务过滤: {args.task or '全部'}；错误过滤: {args.only_error or '全部'}；"
        f"force={args.force}）"
    )
    if not records:
        return 0

    if args.dry_run:
        for row, record in records:
            item = record.get("商品信息") or {}
            error_text = ((record.get("ai_analysis") or {}).get("error") or "")[:40]
            print(
                f"  #{row['id']:<5} {row['task_name']:<18} "
                f" {str(item.get('当前售价') or '-'):<8} {str(item.get('商品标题') or '')[:34]}"
                f"  <- {error_text}"
            )
        return 0

    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    write_lock = asyncio.Lock()
    done = 0
    stats = {"ok": 0, "recommend": 0, "fail": 0, "skip": 0}
    prompts = {name: load_prompt(task) for name, task in tasks.items()}

    async def worker(index: int, row: sqlite3.Row, record: dict) -> None:
        nonlocal done
        task_name = str(row["task_name"] or record.get("任务名称") or "")
        task = resolve_task(tasks, task_name, str(row["keyword"] or ""))
        prompt = prompts.get(str(task.get("task_name")), "") if task else ""

        if task is None or not prompt:
            stats["skip"] += 1
            done += 1
            print(f"[{done}/{len(records)}] 跳过 #{row['id']} {task_name}：任务配置或 prompt 缺失")
            return

        async with semaphore:
            started = asyncio.get_event_loop().time()
            try:
                status, detail = await analyze_one(
                    row, record, task, prompt, notify=args.notify, write_lock=write_lock
                )
            except Exception as exc:
                status, detail = "fail", f"{type(exc).__name__}: {exc}"

            done += 1
            elapsed = asyncio.get_event_loop().time() - started
            stats[status] += 1
            if detail == "推荐":
                stats["recommend"] += 1
            title = str((record.get("商品信息") or {}).get("商品标题") or "")[:30]
            print(f"[{done}/{len(records)}] {'OK ' if status == 'ok' else 'ERR'} "
                  f"#{row['id']} {task_name} {elapsed:4.1f}s {detail} | {title}")
            await asyncio.sleep(args.interval)

    await asyncio.gather(*(worker(i, row, record) for i, (row, record) in enumerate(records)))

    print(
        f"\n完成: 成功 {stats['ok']}（推荐 {stats['recommend']}）/ "
        f"失败 {stats['fail']} / 跳过 {stats['skip']}"
    )
    return 0 if stats["fail"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="重跑历史 AI 分析失败的商品")
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 条（0 = 全部）")
    parser.add_argument("--concurrency", type=int, default=2, help="AI 并发数，默认 2")
    parser.add_argument("--interval", type=float, default=1.0, help="每条之间间隔秒数")
    parser.add_argument("--only-error", default="", help="只处理错误信息包含该子串的记录")
    parser.add_argument("--task", default="", help="只处理指定任务名（容忍尾空格/大小写）")
    parser.add_argument(
        "--force",
        action="store_true",
        help="连没有 error 的历史记录一起重打（改完判据后刷新老结论时用）",
    )
    parser.add_argument("--notify", action="store_true", help="对推荐结果推送通知（默认关闭）")
    parser.add_argument("--dry-run", action="store_true", help="只列出待处理记录，不调用 AI、不写库")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
