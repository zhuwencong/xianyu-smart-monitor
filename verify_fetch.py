"""一次性验证脚本：用已保存的登录态跑一次真实搜索，确认爬虫链路通。"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "acc_1.json"
KEYWORD = "机械键盘"

CTX = {
    "user_agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "viewport": {"width": 412, "height": 915},
    "device_scale_factor": 2.625,
    "is_mobile": True,
    "has_touch": True,
    "locale": "zh-CN",
    "timezone_id": "Asia/Shanghai",
    "color_scheme": "light",
}


async def main() -> int:
    hits = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="msedge")
        context = await browser.new_context(storage_state=str(STATE), **CTX)
        page = await context.new_page()

        def on_response(resp):
            u = resp.url
            if "idlemtopsearch" in u or "mtop.taobao.idle" in u:
                hits.append((resp.status, len(u), u.split("?")[0]))

        page.on("response", on_response)

        await page.goto("https://www.goofish.com/", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2000)
        print("首页 URL:", page.url)

        await page.goto(
            f"https://www.goofish.com/search?q={KEYWORD}",
            wait_until="domcontentloaded",
            timeout=45000,
        )
        await page.wait_for_timeout(6000)
        print("搜索页 URL:", page.url)

        title = await page.title()
        print("页面标题:", title)

        logged_out = "passport" in page.url or "login" in page.url.lower()
        print("被踢到登录页:", logged_out)

        text = await page.inner_text("body")
        print("页面文本长度:", len(text))
        print("含『登录』字样:", "登录" in text)
        snippet = " ".join(text.split())[:150]
        print("正文开头:", snippet)
        print("接口命中:", hits[:6], "共", len(hits))

        await page.screenshot(path=str(ROOT / "verify_search.png"), full_page=False)
        print("截图: verify_search.png")

        await browser.close()
    return 0 if hits and not logged_out else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
