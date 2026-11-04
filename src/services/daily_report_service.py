"""
监控日报服务

背景：PushPlus 此前只推「AI 推荐」商品——像"抢真我手机"这种长期 0 推荐
的任务，收不到任何推送，系统死活完全不知道。日报每天固定推一条：

- 各任务近 24h 新增 / 推荐条数（含历史累计）
- 近 24h 风控拦截次数（从任务日志解析）
- 自动导出一份 Excel 日报到工作区（明细 + 汇总），免得每次现写导出脚本

配置（.env）：
- DAILY_REPORT_ENABLED       默认 true
- DAILY_REPORT_HOUR          每天几点推（默认 21）
- DAILY_REPORT_EXPORT_DIR    Excel 导出目录（默认项目上级目录，即 E:\\闲鱼自动化）
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from src.infrastructure.persistence.storage_names import DEFAULT_DATABASE_PATH

_LOG_LINE_TS_RE = re.compile(r"\[\s*(\d{4}-\d{2}-\d{2}) [\d:]+\]")
_RISK_MARKER = "FAIL_SYS_USER_VALIDATE"


def _db_path() -> str:
    return os.getenv("APP_DATABASE_FILE", DEFAULT_DATABASE_PATH)


def _export_dir() -> Path:
    configured = os.getenv("DAILY_REPORT_EXPORT_DIR", "").strip()
    if configured:
        return Path(configured)
    # 默认：项目目录的上一级（E:\闲鱼自动化），与历史手工导出保持一致
    # parents[3] = 项目根(ai-goofish-monitor) 的上一级
    return Path(__file__).resolve().parents[3]


def _risk_control_counts_today(log_dir: Path, today: str) -> dict[str, int]:
    """按任务统计今天的风控拦截次数。

    风控报错行本身不带时间戳，借用向前最近一条带时间戳的日志行归属日期。
    """
    counts: dict[str, int] = {}
    if not log_dir.is_dir():
        return counts
    for log_file in sorted(log_dir.glob("*.log")):
        last_date = ""
        today_hits = 0
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    match = _LOG_LINE_TS_RE.search(line)
                    if match:
                        last_date = match.group(1)
                    if _RISK_MARKER in line and last_date == today:
                        today_hits += 1
        except OSError:
            continue
        if today_hits:
            counts[log_file.stem] = today_hits
    return counts


def collect_daily_report() -> dict:
    """汇总近 24h 各任务数据，返回结构化结果（不发送、不落盘）。"""
    now = datetime.now()
    since = now - timedelta(hours=24)
    today_str = now.strftime("%Y-%m-%d")

    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        tasks = list(
            conn.execute("SELECT id, task_name, keyword FROM tasks ORDER BY id")
        )
        per_task = []
        for task in tasks:
            name = task["task_name"]
            row = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN is_recommended = 1 THEN 1 ELSE 0 END) AS rec,
                       MAX(crawl_time) AS last_time
                FROM result_items WHERE task_name = ?
                """,
                (name,),
            ).fetchone()
            row24 = conn.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN is_recommended = 1 THEN 1 ELSE 0 END) AS rec
                FROM result_items
                WHERE task_name = ? AND crawl_time >= ?
                """,
                (name, since.isoformat()),
            ).fetchone()
            per_task.append(
                {
                    "task_name": name,
                    "keyword": task["keyword"],
                    "new_24h": int(row24["total"] or 0),
                    "rec_24h": int(row24["rec"] or 0),
                    "total": int(row["total"] or 0),
                    "rec_total": int(row["rec"] or 0),
                    "last_time": row["last_time"] or "",
                }
            )
        recent_items = list(
            conn.execute(
                """
                SELECT task_name, crawl_time, title, price_display, is_recommended, link
                FROM result_items
                WHERE crawl_time >= ?
                ORDER BY task_name, crawl_time DESC
                """,
                (since.isoformat(),),
            )
        )
    finally:
        conn.close()

    risk_counts = _risk_control_counts_today(Path("logs"), today_str)
    items = [
        {
            "task_name": r["task_name"],
            "crawl_time": (r["crawl_time"] or "")[:19].replace("T", " "),
            "title": r["title"] or "",
            "price": r["price_display"] or "",
            "recommended": bool(r["is_recommended"]),
            "link": r["link"] or "",
        }
        for r in recent_items
    ]
    return {
        "date": today_str,
        "per_task": per_task,
        "risk_counts": risk_counts,
        "recent_items": items,
        "new_24h_total": sum(t["new_24h"] for t in per_task),
        "rec_24h_total": sum(t["rec_24h"] for t in per_task),
    }


def _clean_link(link: str) -> str:
    """历史链接可能是 m.goofish.com 长链，统一净化成 item?id= 短链。"""
    match = re.search(r"id=([0-9A-Za-z]+)", link or "")
    return f"https://www.goofish.com/item?id={match.group(1)}" if match else (link or "")


def export_report_xlsx(report: dict) -> Path | None:
    """导出 Excel 日报（汇总 + 24h 明细），返回文件路径。"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("[日报] 未安装 openpyxl，跳过 Excel 导出")
        return None

    export_dir = _export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / f"监控日报_{report['date']}.xlsx"

    wb = Workbook()
    header_fill = PatternFill("solid", fgColor="D9E2F3")
    header_font = Font(bold=True)
    wrap = Alignment(wrap_text=True, vertical="top")

    ws = wb.active
    ws.title = "汇总"
    ws.append(["任务", "关键词", "24h新增", "24h推荐", "累计", "累计推荐", "最后成功"])
    risk_counts = report["risk_counts"]
    for t in report["per_task"]:
        ws.append(
            [
                t["task_name"],
                t["keyword"],
                t["new_24h"],
                t["rec_24h"],
                t["total"],
                t["rec_total"],
                (t["last_time"] or "")[:19].replace("T", " "),
            ]
        )
    ws.append([])
    ws.append(["今日风控拦截（按日志）"])
    for log_name, count in risk_counts.items():
        ws.append([log_name, count])
    if not risk_counts:
        ws.append(["（无）", 0])

    ws2 = wb.create_sheet("24h明细")
    ws2.append(["任务", "抓取时间", "标题", "价格", "AI推荐", "链接"])
    for item in report["recent_items"]:
        ws2.append(
            [
                item["task_name"],
                item["crawl_time"],
                item["title"],
                item["price"],
                "是" if item["recommended"] else "否",
                _clean_link(item["link"]),
            ]
        )

    for sheet in (ws, ws2):
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
        for idx, col in enumerate(sheet.columns, start=1):
            letter = get_column_letter(idx)
            max_len = max((len(str(c.value or "")) for c in col), default=8)
            sheet.column_dimensions[letter].width = min(max(max_len + 2, 8), 60)
            if letter == "C" and sheet.title == "24h明细":
                for c in col:
                    c.alignment = wrap
    ws2.column_dimensions["C"].width = 50

    wb.save(out_path)
    return out_path


def build_report_text(report: dict, xlsx_path: Path | None) -> str:
    lines = [
        f"监控日报 {report['date']}",
        f"近24h新增 {report['new_24h_total']} 条 / 推荐 {report['rec_24h_total']} 条",
        "",
    ]
    for t in report["per_task"]:
        last = (t["last_time"] or "")[:16].replace("T", " ") or "从未"
        lines.append(
            f"■ {t['task_name']}（{t['keyword']}）："
            f"24h新增 {t['new_24h']} / 推荐 {t['rec_24h']}；"
            f"累计 {t['total']} / 推荐 {t['rec_total']}；最后成功 {last}"
        )
    risk_total = sum(report["risk_counts"].values())
    lines.append("")
    if risk_total:
        detail = "，".join(f"{k} {v} 次" for k, v in report["risk_counts"].items())
        lines.append(f"今日风控拦截 {risk_total} 次（{detail}）")
    else:
        lines.append("今日风控拦截 0 次")
    if xlsx_path:
        lines.append("")
        lines.append(f"Excel 日报已导出：{xlsx_path}")
    return "\n".join(lines)


async def send_daily_report() -> dict:
    """收集数据、导出 Excel、推送日报。返回执行结果。"""
    from src.services.notification_service import build_notification_service

    report = collect_daily_report()
    xlsx_path = None
    try:
        xlsx_path = export_report_xlsx(report)
    except Exception as exc:
        print(f"[日报] Excel 导出失败（不影响推送）: {exc}")

    text = build_report_text(report, xlsx_path)
    service = build_notification_service()
    if not service.clients:
        print("[日报] 未配置任何通知渠道，仅导出 Excel")
        return {"sent": False, "reason": "no_channel", "xlsx": str(xlsx_path) if xlsx_path else None, "text": text}

    results = await service.send_notification(
        {
            "商品标题": f"[监控日报] {report['date']} 新增{report['new_24h_total']}/推荐{report['rec_24h_total']}",
            "当前售价": "-",
            "商品链接": "https://www.goofish.com/",
        },
        text,
    )
    sent = any(r.get("success") for r in results.values())
    print(f"[日报] 推送{'成功' if sent else '失败'}: {results}")
    return {
        "sent": sent,
        "results": results,
        "xlsx": str(xlsx_path) if xlsx_path else None,
        "text": text,
    }


def is_daily_report_enabled() -> bool:
    return os.getenv("DAILY_REPORT_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def daily_report_hour() -> int:
    try:
        return min(23, max(0, int(os.getenv("DAILY_REPORT_HOUR", "21"))))
    except ValueError:
        return 21
