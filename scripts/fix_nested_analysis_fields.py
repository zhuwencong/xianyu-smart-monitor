"""就地修正历史结果里错位嵌套的分析字段。

背景：deepseek-flash 输出长嵌套 JSON 时，会把 shipping / seller_credit
误挂到 criteria_analysis.seller_type 内部（约六成本次显卡结果如此）。
解析侧已修（ai_response_parser.normalize_analysis_schema），但库里那批
历史结果仍是错位结构，前端读不到这两项。

本脚本只做结构搬移，不重新调用 AI、不改任何结论，幂等可重跑。

用法：
    .venv\\Scripts\\python.exe scripts/fix_nested_analysis_fields.py --dry-run
    .venv\\Scripts\\python.exe scripts/fix_nested_analysis_fields.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

DB_PATH = BASE / "data" / "app.sqlite3"
FLAT_KEYS = ("model_chip", "battery_health", "condition", "history", "shipping", "seller_credit")


def fix_analysis(analysis: dict) -> bool:
    """把 seller_type 内错位的扁平字段提回 criteria_analysis 顶层。"""
    seller_type = analysis.get("seller_type")
    if not isinstance(seller_type, dict):
        return False

    moved = False
    for key in FLAT_KEYS:
        if key in analysis:
            continue
        if key in seller_type:
            analysis[key] = seller_type.pop(key)
            moved = True
    return moved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--task-like", default="%显卡%", help="按 task_name 过滤")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, task_name, price, title, raw_json, is_recommended "
        "FROM result_items WHERE task_name LIKE ?",
        (args.task_like,),
    )
    rows = cur.fetchall()

    total = fixed = skipped = 0
    for row in rows:
        total += 1
        try:
            raw = json.loads(row["raw_json"])
        except (TypeError, json.JSONDecodeError):
            skipped += 1
            continue

        analysis = raw.get("ai_analysis")
        if not isinstance(analysis, dict):
            skipped += 1
            continue
        nested = analysis.get("criteria_analysis")
        if not isinstance(nested, dict):
            skipped += 1
            continue

        if not fix_analysis(nested):
            continue

        fixed += 1
        print(f"  修正 #{row['id']} [{row['price']}] {str(row['title'])[:32]}")

        if not args.dry_run:
            cur.execute(
                "UPDATE result_items SET raw_json = ? WHERE id = ?",
                (json.dumps(raw, ensure_ascii=False), row["id"]),
            )

    if not args.dry_run:
        conn.commit()
    conn.close()

    mode = "预览（未写库）" if args.dry_run else "已写回"
    print(f"\n共 {total} 条，需修正 {fixed} 条，跳过 {skipped} 条 —— {mode}")


if __name__ == "__main__":
    main()
