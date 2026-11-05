"""重算历史记录的「市场价 / 硬门槛」结论。

背景：旧版本用「任务关键词」全类的算术平均当市场价，导致一块 208 元的
Quadro P620 被拿去和一堆 500~700 的消费级显卡比，算出「市场均价 526.98」。
同时没有任何代码层的硬门槛，模型说推荐就推荐。

这个脚本做两件事（都可以先 --dry-run 看）：
1. 用新的「同型号中位数」口径重算每条记录的 price_insight / 价格参考；
2. 用底层硬门槛复核 is_recommended，被否决的改成不推荐并写明原因。

用法：
    python scripts/backfill_price_insight.py --dry-run
    python scripts/backfill_price_insight.py --apply
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.scoring import evaluate_gates, extract_specs, task_allows_professional
from src.domain.scoring.specs import looks_like_gpu_task
from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import get_database_path, sqlite_connection
from src.services.price_history_service import (
    build_market_reference,
    load_price_snapshots,
    parse_price_value,
)

HARD_GATE_PREFIX = "[硬门槛否决]"
INSIGHT_KEYS = ("price_insight", "价格参考")


def _load_tasks(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, task_name, keyword, description, min_price, max_price, free_shipping
        FROM tasks
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _pick_task(task_rows: list[dict], keyword: str, task_name: str) -> dict | None:
    for task in task_rows:
        if (task.get("keyword") or "") == keyword and (task.get("task_name") or "") == task_name:
            return task
    for task in task_rows:
        if (task.get("task_name") or "") == task_name:
            return task
    for task in task_rows:
        if (task.get("keyword") or "") == keyword:
            return task
    return None


def _pick_run_id(snapshots: list[dict], item_id: str, crawl_time: str) -> str | None:
    candidates = [s for s in snapshots if str(s.get("item_id") or "") == str(item_id)]
    if not candidates:
        return None
    crawl_day = str(crawl_time or "")[:10]

    def score(snapshot: dict) -> tuple[int, str]:
        same_day = 0 if str(snapshot.get("snapshot_day") or "") == crawl_day else 1
        return (same_day, str(snapshot.get("snapshot_time") or ""))

    return str(sorted(candidates, key=score)[0].get("run_id") or "")


def _ordered_snapshots(snapshots: list[dict], run_id: str) -> list[dict]:
    run_part = [s for s in snapshots if str(s.get("run_id") or "") == run_id]
    other = [s for s in snapshots if str(s.get("run_id") or "") != run_id]
    return other + run_part


def _recompute_insight(keyword: str, item: dict, snapshots: list[dict], run_id: str) -> dict | None:
    run_snapshots = [s for s in snapshots if str(s.get("run_id") or "") == run_id]
    if not run_snapshots:
        return None
    reference = build_market_reference(
        keyword=keyword,
        item=item,
        current_market_items=[
            {
                "当前售价": snapshot.get("price_display") or snapshot.get("price"),
                "商品标题": snapshot.get("title") or "",
            }
            for snapshot in run_snapshots
        ],
        historical_snapshots=_ordered_snapshots(snapshots, run_id),
        gpu_hint=looks_like_gpu_task(keyword),
    )
    return reference


def _apply_hard_gate(raw: dict, task: dict | None, price: float | None) -> bool:
    """返回是否发生了改变。"""
    analysis = raw.get("ai_analysis") or {}
    if not isinstance(analysis, dict) or analysis.get("error"):
        return False
    if str(analysis.get("analysis_source") or "") == "keyword":
        return False
    if "hard_gates" in analysis:
        return False

    product = raw.get("商品信息") or {}
    seller = raw.get("卖家信息") or {}
    gates = evaluate_gates(
        specs=extract_specs(
            product.get("商品标题"),
            product.get("商品描述"),
            gpu_hint=looks_like_gpu_task(
                (task or {}).get("keyword"),
                raw.get("搜索关键字"),
                product.get("商品标题"),
            ),
        ),
        price=price,
        budget_min=(task or {}).get("min_price"),
        budget_max=(task or {}).get("max_price"),
        require_shipping=bool((task or {}).get("free_shipping")),
        allow_professional=task_allows_professional(
            (task or {}).get("keyword"),
            (task or {}).get("description"),
        ),
        seller_credit=str(seller.get("卖家信用等级") or ""),
    )
    analysis["hard_gates"] = gates.as_list()
    if not gates.blocked:
        return True

    analysis["is_recommended"] = False
    analysis["hard_blocked"] = True
    labels = "、".join(hit.label for hit in gates.blocks)
    reason = str(analysis.get("reason") or "").strip()
    if not reason.startswith(HARD_GATE_PREFIX):
        analysis["reason"] = f"{HARD_GATE_PREFIX}{labels}。" + reason
    risk_tags = list(analysis.get("risk_tags") or [])
    for hit in gates.blocks:
        if hit.label not in risk_tags:
            risk_tags.append(hit.label)
    analysis["risk_tags"] = risk_tags
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="重算历史市场价与硬门槛")
    parser.add_argument("--apply", action="store_true", help="真正写回数据库")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 条，0 表示全部")
    parser.add_argument(
        "--reset-from",
        default="",
        help="先用这个备份库的 raw_json 覆盖当前记录，再重新计算（用于修正误判后重跑）",
    )
    args = parser.parse_args()

    bootstrap_sqlite_storage()
    print(f"数据库: {Path(get_database_path()).resolve()}")

    reset_records: dict[int, str] = {}
    if args.reset_from:
        backup_path = Path(args.reset_from)
        if not backup_path.exists():
            print(f"备份库不存在: {backup_path}")
            return 2
        backup_conn = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
        backup_conn.row_factory = sqlite3.Row
        for row in backup_conn.execute("SELECT id, raw_json FROM result_items"):
            reset_records[int(row["id"])] = row["raw_json"]
        backup_conn.close()
        print(f"从备份恢复 ai_analysis 基线: {len(reset_records)} 条")

    snapshot_cache: dict[str, list[dict]] = {}
    changed_insight = 0
    changed_gate = 0

    with sqlite_connection() as conn:
        tasks = _load_tasks(conn)
        rows = conn.execute(
            """
            SELECT id, keyword, task_name, crawl_time, price, item_id, title, raw_json
            FROM result_items
            ORDER BY id ASC
            """
        ).fetchall()
        if args.limit:
            rows = rows[: args.limit]

        for row in rows:
            base_json = reset_records.get(int(row["id"]), row["raw_json"])
            try:
                raw = json.loads(base_json or "{}")
            except (TypeError, ValueError):
                continue
            product = raw.get("商品信息") or {}
            item_id = str(row["item_id"] or product.get("商品ID") or "")
            keyword = str(row["keyword"] or "")
            if not item_id or not keyword:
                continue

            if keyword not in snapshot_cache:
                snapshot_cache[keyword] = load_price_snapshots(keyword)
            snapshots = snapshot_cache[keyword]

            run_id = _pick_run_id(snapshots, item_id, str(row["crawl_time"] or ""))
            reference = _recompute_insight(keyword, product, snapshots, run_id) if run_id else None
            insight_changed = False
            if reference:
                old_insight = raw.get("price_insight") or {}
                new_insight = reference.get("本商品价格位置") or {}
                if (
                    old_insight.get("market_scope") != new_insight.get("market_scope")
                    or old_insight.get("market_median_price") != new_insight.get("market_median_price")
                    or old_insight.get("market_sample_count") != new_insight.get("market_sample_count")
                ):
                    insight_changed = True
                raw["price_insight"] = new_insight
                raw["价格参考"] = reference

            price = row["price"] if row["price"] is not None else parse_price_value(product.get("当前售价"))
            gate_changed = _apply_hard_gate(raw, _pick_task(tasks, keyword, str(row["task_name"] or "")), price)

            if not (insight_changed or gate_changed):
                continue

            if insight_changed:
                changed_insight += 1
            if gate_changed:
                changed_gate += 1

            analysis = raw.get("ai_analysis") or {}
            print(
                f"#{row['id']:>4} {keyword[:10]:<10} ¥{price if price is not None else '-':<8} "
                f"scope={raw.get('price_insight', {}).get('market_scope')} "
                f"median={raw.get('price_insight', {}).get('market_median_price')} "
                f"rec={analysis.get('is_recommended')} "
                f"gates={[hit['key'] for hit in (analysis.get('hard_gates') or []) if hit['severity'] == 'block']}"
            )

            if args.apply:
                conn.execute(
                    "UPDATE result_items SET raw_json = ?, is_recommended = ? WHERE id = ?",
                    (
                        json.dumps(raw, ensure_ascii=False),
                        1 if analysis.get("is_recommended") is True else 0,
                        row["id"],
                    ),
                )
        if args.apply:
            conn.commit()

    mode = "已写回" if args.apply else "dry-run（未写回，加 --apply 生效）"
    print(f"\n{mode}：价格参考更新 {changed_insight} 条，硬门槛复核 {changed_gate} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
