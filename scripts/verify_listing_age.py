"""验证 AI 是否按「上架时长」字段判定时效，而不是自己算日期。

背景：2026-11-26 那轮实测发现，deepseek-flash 会把「2026-11-26 23:34 发布、
23:45 抓取」（只过 11 分钟）算成「上架已超 3 天」，导致误触发一票否决。
修复方式是本地算好「上架时长」塞进商品 JSON，提示词明确禁止 AI 自行做日期减法。

本脚本用两条同型号、同时效不同的商品对比，确认结论跟着字段走。

用法：
    .venv\\Scripts\\python.exe scripts/verify_listing_age.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
os.chdir(BASE)
sys.path.insert(0, str(BASE))

from src.core.proxy_env import strip_inherited_proxy_env

strip_inherited_proxy_env()

from src.infrastructure.external.ai_client import AIClient  # noqa: E402
from src.services.publish_time_filter import describe_listing_age  # noqa: E402

# 同一张卡、同一价格，唯一变量是上架时长
CASES = [
    ("新鲜（11 分钟）", "2026-11-26 23:34"),
    ("超期（10 天）", "2026-11-16 10:00"),
]


async def main() -> None:
    base = Path("prompts/base_prompt_gpu.txt").read_text(encoding="utf-8")
    crit = Path("prompts/gpu_300_600_criteria.txt").read_text(encoding="utf-8")
    prompt = base.replace("{{CRITERIA_SECTION}}", crit)

    client = AIClient()
    if not client.is_available():
        print("AI 客户端不可用")
        return

    for label, published in CASES:
        age_text = describe_listing_age(published)
        product = {
            "爬取时间": "2026-11-26T23:45:00",
            "任务名称": "显卡捡漏 300-600",
            "商品信息": {
                "商品标题": "七彩虹GTX1660 6G显卡 自用拆机 成色好 无拆无修",
                "当前售价": "520",
                "发布时间": published,
                "上架时长": age_text,
                "商品描述": (
                    "自用拆机卡，GTX1660 6G GDDR6，双风扇，单8pin供电，"
                    "HDMI/DP/DVI齐全，上机正常，无拆无修。个人闲置仅此一张。"
                ),
                "商品标签": ["包邮"],
            },
            "卖家信息": {"卖家昵称": "玩家老张", "信用": "极好"},
        }

        result = await client.analyze(product, [], prompt) or {}
        cond = (result.get("criteria_analysis") or {}).get("condition") or {}
        reason = str(result.get("reason") or "")
        print(f"\n=== {label} | 字段值「{age_text}」发布={published} ===")
        print(f"  is_recommended: {result.get('is_recommended')}")
        print(f"  condition: {str(cond.get('comment'))[:150]}")
        print(f"  reason: {reason[:150]}")
        over = any(k in reason for k in ("超3天", "超出 3 天", "超出3天", "已10天", "已 10 天", "A0"))
        print("  >>> 判定：" + ("AI 认为超期（A0 否决）" if over else "AI 认为在时效内"))


if __name__ == "__main__":
    asyncio.run(main())
