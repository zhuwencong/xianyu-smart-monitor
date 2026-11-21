"""
商品上架状态巡检。

结果列表里排名靠前的商品，可能几分钟前就被人拍走了。这个模块负责定期把
前几条重新打开看一眼，已售出 / 已下架的写回 ``status='expired'``，
避免对着一台早已成交的机器继续纠结。

判定依据是详情接口 ``mtop.taobao.idle.pc.detail`` 返回的 ``itemDO.itemStatus``：
``0`` 在售、``1`` 已售出，其余视为已下架。接口没返回时退回页面文案兜底。

注意：本模块必须用有头浏览器。无头模式几乎必中滑块（FAIL_SYS_USER_VALIDATE），
这一点实测确认过，别改成 headless=True 省事。
"""
from __future__ import annotations

import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.config import DETAIL_API_URL_PATTERN, RUN_HEADLESS
from src.infrastructure.persistence.sqlite_bootstrap import bootstrap_sqlite_storage
from src.infrastructure.persistence.sqlite_connection import sqlite_connection

# 只巡检列表排名最靠前的几个，够用且不烧风控额度。
DEFAULT_CHECK_LIMIT = 6
MAX_CHECK_LIMIT = 20

PAGE_TIMEOUT_MS = 30000
RISK_MARKERS = ("FAIL_SYS_USER_VALIDATE", "RGV587_ERROR")
GONE_TEXT_MARKERS = ("已下架", "已卖出", "宝贝不存在", "商品不存在", "已经卖掉")

# 一旦被风控，12 小时内不再自动巡检。宁可少查几轮，也不能把号打死。
COOLDOWN_PATH = os.path.join("logs", "listing-check-cooldown.json")
COOLDOWN_HOURS = 12

# 与主抓取保持一致：移动端 UA + 触摸设备，避免被识别成异类客户端。
_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
)
_CONTEXT_OPTIONS = {
    "user_agent": _MOBILE_UA,
    "viewport": {"width": 412, "height": 915},
    "device_scale_factor": 2.625,
    "is_mobile": True,
    "has_touch": True,
    "locale": "zh-CN",
    "timezone_id": "Asia/Shanghai",
    "color_scheme": "light",
}

_ANTI_DETECT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en-US', 'en']});
window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}};
Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
"""


def cooldown_until() -> Optional[datetime]:
    """读取风控冷却到什么时候；没有冷却记录返回 None。"""
    try:
        with open(COOLDOWN_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        return datetime.fromisoformat(str(data["until"]))
    except Exception:
        return None


def cooldown_active() -> bool:
    until = cooldown_until()
    return until is not None and datetime.now() < until


def enter_cooldown(reason: str = "", hours: int = COOLDOWN_HOURS) -> None:
    """命中风控后进入冷却，避免定时任务把账号反复打。"""
    os.makedirs(os.path.dirname(COOLDOWN_PATH) or ".", exist_ok=True)
    until = datetime.now() + timedelta(hours=hours)
    try:
        with open(COOLDOWN_PATH, "w", encoding="utf-8") as handle:
            json.dump(
                {"until": until.isoformat(timespec="seconds"), "reason": reason},
                handle,
                ensure_ascii=False,
            )
    except OSError:
        pass


def _launch_args() -> list[str]:
    """Chromium 启动参数，与 scraper 保持同一套反检测开关。"""
    import tempfile

    dumps = os.path.join(tempfile.gettempdir(), "goofish-listing-check")
    os.makedirs(dumps, exist_ok=True)
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-breakpad",
        "--disable-crash-reporter",
        f"--crash-dumps-dir={dumps}",
    ]


def resolve_cookie_state(state_dir: str = "state") -> Optional[str]:
    """挑一个最新的登录态文件。

    只认 ``acc_<数字>.json``：``.dup`` / ``.stale`` / ``.bak`` 都是废文件，
    拿它们去请求只会白吃一次风控。
    """
    if not os.path.isdir(state_dir):
        return None
    candidates: list[tuple[float, str]] = []
    for name in os.listdir(state_dir):
        if not name.startswith("acc_") or not name.endswith(".json"):
            continue
        stem = name[len("acc_") : -len(".json")]
        if not stem.isdigit():
            continue
        path = os.path.join(state_dir, name)
        try:
            candidates.append((os.path.getmtime(path), path))
        except OSError:
            continue
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def load_top_items(filename: str, limit: int = DEFAULT_CHECK_LIMIT) -> list[dict]:
    """取结果列表里排名最靠前的若干条在售记录。

    排序与面板默认一致：active 优先、按爬取时间倒序。
    """
    limit = max(1, min(int(limit), MAX_CHECK_LIMIT))
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        rows = conn.execute(
            """
            SELECT item_id, title, link
            FROM result_items
            WHERE result_filename = ?
              AND status = 'active'
              AND item_id IS NOT NULL
              AND item_id != ''
            ORDER BY crawl_time DESC, id DESC
            LIMIT ?
            """,
            (filename, limit),
        ).fetchall()
        keyword_row = conn.execute(
            "SELECT keyword FROM result_items WHERE result_filename = ? LIMIT 1",
            (filename,),
        ).fetchone()
    return [
        {"item_id": str(row["item_id"]), "title": row["title"] or "", "link": row["link"] or ""}
        for row in rows
    ], (keyword_row["keyword"] if keyword_row else "")


def save_listing_result(filename: str, item_id: str, state: str) -> None:
    """把巡检结论写回数据库（只处理确认下架的情况）。"""
    if state not in {"sold", "gone"}:
        return
    now = datetime.now().isoformat(timespec="seconds")
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        conn.execute(
            """
            UPDATE result_items
            SET status = 'expired', listing_checked_at = ?
            WHERE result_filename = ? AND item_id = ?
            """,
            (now, filename, item_id),
        )
        conn.commit()


def touch_checked_at(filename: str, item_id: str) -> None:
    """记录一次“看过了但还在售”，方便日后排查巡检有没有真的跑。"""
    now = datetime.now().isoformat(timespec="seconds")
    bootstrap_sqlite_storage()
    with sqlite_connection() as conn:
        conn.execute(
            """
            UPDATE result_items
            SET listing_checked_at = ?
            WHERE result_filename = ? AND item_id = ?
            """,
            (now, filename, item_id),
        )
        conn.commit()


def _classify(ret_text: str, item_do: dict, page_text: str) -> str:
    """把接口返回归类成 on_sale / sold / gone / unknown。"""
    status = item_do.get("itemStatus")
    if status == 0:
        return "on_sale"
    if status == 1:
        return "sold"
    if status is not None:
        return "gone"
    if "NOT_FOUND" in ret_text or "NOT_EXIST" in ret_text:
        return "gone"
    if any(marker in (page_text or "") for marker in GONE_TEXT_MARKERS):
        return "gone"
    return "unknown"


def _search_url(keyword: str) -> str:
    if not keyword:
        return "https://www.goofish.com/"
    return "https://www.goofish.com/search?q=" + quote(keyword)


async def _warmup(page, keyword: str) -> None:
    """先把 session 养热：首页停一会儿，再走一遍搜索页。

    闲鱼对「新开浏览器直奔商品详情」的判定很敏感，直接 goto 详情页几乎必中
    滑块；而主抓取是首页 → 搜索 → 列表 → 详情的完整链路，所以一直相安无事。
    这里照着同一条链路模仿。
    """
    try:
        await page.goto(
            "https://www.goofish.com/", wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS
        )
        await asyncio.sleep(random.uniform(2.5, 4))
    except Exception:
        return
    if not keyword:
        return
    try:
        await page.goto(
            _search_url(keyword), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS
        )
        # 让列表真正渲染出来，产生一次像样的搜索请求
        await asyncio.sleep(random.uniform(5, 8))
    except Exception:
        pass


async def _probe_one(page, link: str, keyword: str = "") -> tuple[str, str]:
    """打开一条商品页，返回 (状态, 备注)。状态里 risk 表示整体该停了。

    必须带 Referer：闲鱼对「无来源直接访问详情页」的拦截明显更严，
    而主抓取是从搜索列表点进去的，所以一直相安无事。
    """
    try:
        async with page.expect_response(
            lambda r: DETAIL_API_URL_PATTERN in r.url and "report" not in r.url,
            timeout=PAGE_TIMEOUT_MS,
        ) as response_info:
            await page.goto(
                link,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
                referer=_search_url(keyword),
            )
        response = await response_info.value
        data = await response.json()
        ret_text = str(data.get("ret") or "")
        if any(marker in ret_text for marker in RISK_MARKERS):
            return "risk", ret_text[:120]
        item_do = (data.get("data") or {}).get("itemDO") or {}
        return _classify(ret_text, item_do, ""), ret_text[:120]
    except PlaywrightTimeoutError:
        # 接口没拦到（下架页可能不发详情请求），退回页面文案判断。
        try:
            page_text = await page.evaluate("document.body.innerText")
        except Exception:
            page_text = ""
        state = _classify("", {}, page_text)
        return state, "timeout"
    except Exception as exc:  # noqa: BLE001 - 单条失败不该打断整批
        return "unknown", f"{type(exc).__name__}: {exc}"[:120]


async def check_listing_status(
    filename: str,
    limit: int = DEFAULT_CHECK_LIMIT,
    *,
    cookie_path: Optional[str] = None,
    headless: Optional[bool] = None,
    force: bool = False,
) -> dict:
    """巡检结果文件里排名前 N 的商品，返回统计结果。

    返回结构::

        {
          "checked": 6, "on_sale": 3, "sold": 1, "gone": 1, "unknown": 1,
          "risk_control": False, "cookie": "state/acc_1.json",
          "items": [{"item_id": ..., "title": ..., "state": ...}, ...]
        }
    """
    items, keyword = load_top_items(filename, limit)
    summary = {
        "checked": len(items),
        "on_sale": 0,
        "sold": 0,
        "gone": 0,
        "unknown": 0,
        "risk_control": False,
        "cookie": None,
        "items": [],
    }
    if not items:
        return summary

    if not force and cooldown_active():
        until = cooldown_until()
        summary["skipped"] = f"风控冷却中，{until.isoformat(timespec='minutes') if until else ''} 之后再试"
        return summary

    cookie = cookie_path or resolve_cookie_state()
    if not cookie or not os.path.exists(cookie):
        summary["error"] = "没有可用的登录态文件（state/acc_N.json）"
        return summary
    summary["cookie"] = cookie

    use_headless = RUN_HEADLESS if headless is None else headless
    # 无头必中滑块，除非显式要求，否则一律有头。
    if headless is None:
        use_headless = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=use_headless, args=_launch_args())
        context = await browser.new_context(storage_state=cookie, **_CONTEXT_OPTIONS)
        await context.add_init_script(_ANTI_DETECT_SCRIPT)
        page = await context.new_page()
        try:
            # 养熟 session：首页 → 搜索页，再去看详情。
            # 实测新 context 直接开详情页几乎必中滑块，而主抓取是从搜索结果点进去的。
            await _warmup(page, keyword)

            for index, item in enumerate(items):
                if index > 0:
                    await asyncio.sleep(random.uniform(3.5, 6.5))
                state, note = await _probe_one(page, item["link"], keyword)
                if state == "risk":
                    summary["risk_control"] = True
                    enter_cooldown(reason=note or "FAIL_SYS_USER_VALIDATE")
                    summary["items"].append(
                        {"item_id": item["item_id"], "title": item["title"], "state": "risk", "note": note}
                    )
                    break
                summary["items"].append(
                    {"item_id": item["item_id"], "title": item["title"], "state": state, "note": note}
                )
                if state in ("sold", "gone"):
                    save_listing_result(filename, item["item_id"], state)
                    summary[state if state == "sold" else "gone"] += 1
                elif state == "on_sale":
                    summary["on_sale"] += 1
                    touch_checked_at(filename, item["item_id"])
                else:
                    summary["unknown"] += 1
        finally:
            await browser.close()

    return summary


async def check_all_result_files(
    limit: int = DEFAULT_CHECK_LIMIT, *, force: bool = False
) -> list[dict]:
    """定时任务入口：对每个结果文件各自巡检前 N 条。"""
    from src.services.result_storage_service import list_result_filenames

    outputs: list[dict] = []
    for filename in await list_result_filenames():
        try:
            result = await check_listing_status(filename, limit, force=force)
            outputs.append({"filename": filename, **result})
        except Exception as exc:  # noqa: BLE001
            outputs.append({"filename": filename, "error": f"{type(exc).__name__}: {exc}"})
    return outputs
