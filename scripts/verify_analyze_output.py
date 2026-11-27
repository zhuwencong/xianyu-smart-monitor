"""验证 AI 分析输出的完整性（临时校验脚本）。

用途：确认 ``ai_client.analyze()`` 的 max_output_tokens 提到 8192 后，
返回的 JSON 是否还包含 shipping / seller_credit 两个尾部字段。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
os.chdir(BASE)
sys.path.insert(0, str(BASE))

from src.core.proxy_env import strip_inherited_proxy_env

strip_inherited_proxy_env()

from src.infrastructure.external.ai_client import AIClient  # noqa: E402


async def main() -> None:
    base = Path("prompts/base_prompt_gpu.txt").read_text(encoding="utf-8")
    crit = Path("prompts/gpu_300_600_criteria.txt").read_text(encoding="utf-8")
    prompt = base.replace("{{CRITERIA_SECTION}}", crit)

    product = {
        "title": "七彩虹GTX1060 6G显卡 单风扇 6pin供电 已上机实测 自用",
        "price": "520",
        "description": (
            "自用拆机卡，GTX1060 6GD5 GAMING，GDDR5 6G，6pin供电，"
            "HDMI/DP/DVI 接口齐全，上机正常，跑分如图，无拆无修。"
            "个人闲置，仅此一张，支持同城面交验机。"
        ),
        "seller": {"nickname": "玩家小李", "credit": "极好"},
    }

    client = AIClient()
    if not client.is_available():
        print("AI 客户端不可用")
        return

    result = await client.analyze(product, [], prompt)
    if not result:
        print("analyze 返回 None")
        return

    ca = result.get("criteria_analysis") or {}
    want = ["model_chip", "battery_health", "condition", "history",
            "seller_type", "shipping", "seller_credit"]
    print("is_recommended:", result.get("is_recommended"))
    print("reason:", str(result.get("reason"))[:200])
    print("--- 字段完整性 ---")
    ok = True
    for key in want:
        node = ca.get(key)
        filled = bool(node) and bool((node or {}).get("status"))
        print(f"  {key}: {'OK' if filled else 'MISSING'}")
        ok = ok and filled
    print("--- 结论 ---")
    print("输出完整" if ok else "仍有截断")


if __name__ == "__main__":
    asyncio.run(main())
