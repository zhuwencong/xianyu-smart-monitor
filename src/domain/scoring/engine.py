"""评分引擎：把客观门槛、四维表现和 AI 参考值合成最终分。

三条不可违背的规则：

1. 硬门槛优先。命中 ``gates`` 的 block 项，分数封顶 ``HARD_BLOCK_SCORE_CAP``，
   判断强制为「不匹配」，AI 给了多少分都不作数。
2. AI 只做参考。模型的 ``value_score`` 权重被压到 ``AI_REFERENCE_WEIGHT``，
   它只能微调排序，翻不了「能不能买」的结论。
3. 比价必须同型号。只有拿到同型号（或同型号族）中位数时价格维度才计分，
   跨型号均价一律不参与评分。
"""
from __future__ import annotations

from src.domain.scoring.gates import HARD_BLOCK_SCORE_CAP, GateResult

DIMENSION_WEIGHTS = {
    "match": 0.32,
    "price": 0.30,
    "seller": 0.18,
    "evidence": 0.20,
}

AI_REFERENCE_WEIGHT = 0.25
MISMATCH_CAP = 58
VERIFY_CAP = 74
NEUTRAL_SCORE = 70

_COMPARABLE_SCOPES = {"model", "family"}
_MIN_COMPARABLE_SAMPLES = 3

_STRONG_RISK_TOKENS = ("矿卡", "商家", "贩子", "翻新", "魔改", "售出不退", "诈骗", "维修")


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def benchmark_price(insight: dict) -> tuple[float | None, int, str]:
    """取出可用于比价的中位数，返回 (中位数, 样本数, 口径)。"""
    median = _to_float(insight.get("market_median_price"))
    scope = str(insight.get("market_scope") or "")
    try:
        samples = int(insight.get("market_sample_count") or 0)
    except (TypeError, ValueError):
        samples = 0
    if median and median > 0 and scope in _COMPARABLE_SCOPES and samples >= _MIN_COMPARABLE_SAMPLES:
        return median, samples, scope
    return None, samples, scope


def price_score(price: float | None, insight: dict, ai_value_score) -> tuple[int, str]:
    """价格合理度。没有同型号基准时退回 AI 参考值，绝不拿跨型号均价凑数。"""
    reference, _samples, scope = benchmark_price(insight)
    if price and reference and reference > 0:
        ratio = price / reference
        if ratio <= 0.75:
            return 95, scope
        if ratio <= 0.85:
            return 90, scope
        if ratio <= 0.95:
            return 84, scope
        if ratio <= 1.05:
            return 76, scope
        if ratio <= 1.15:
            return 64, scope
        if ratio <= 1.3:
            return 50, scope
        return 36, scope
    try:
        if ai_value_score is not None:
            return max(0, min(100, int(ai_value_score))), "ai_reference"
    except (TypeError, ValueError):
        pass
    return NEUTRAL_SCORE, "neutral"


def resolve_verdict(
    *,
    analysis_failed: bool = False,
    ai_recommended: bool = False,
    criteria: list[dict] | None = None,
    risk_tags: list[str] | None = None,
    gates: GateResult | None = None,
) -> str:
    """判断优先级：分析失败 > 硬门槛否决 > AI 推荐 > 明确不符合 > 待核实。"""
    if analysis_failed:
        return "failed"
    if gates is not None and gates.blocked:
        return "mismatch"
    if ai_recommended:
        return "recommend"
    has_fail = any(str(item.get("status", "")).upper() == "FAIL" for item in (criteria or []))
    risk_text = " ".join(str(tag) for tag in (risk_tags or []))
    strong_risk = any(token in risk_text for token in _STRONG_RISK_TOKENS)
    if has_fail or strong_risk:
        return "mismatch"
    return "verify"


def resolve_overall(
    *,
    dimensions: dict[str, int],
    ai_value_score,
    verdict: str,
    gates: GateResult | None = None,
) -> int:
    """四维加权 + AI 参考值微调，再按判断结果封顶。"""
    weighted = 0.0
    total_weight = 0.0
    for key, weight in DIMENSION_WEIGHTS.items():
        if key in dimensions:
            weighted += float(dimensions[key]) * weight
            total_weight += weight
    base = weighted / total_weight if total_weight else float(NEUTRAL_SCORE)

    try:
        ai_value = float(ai_value_score) if ai_value_score is not None else None
    except (TypeError, ValueError):
        ai_value = None
    if ai_value is not None:
        ai_value = max(0.0, min(100.0, ai_value))
        base = base * (1 - AI_REFERENCE_WEIGHT) + ai_value * AI_REFERENCE_WEIGHT

    if verdict == "verify":
        base = min(base, VERIFY_CAP)
    elif verdict == "mismatch":
        base = min(base, MISMATCH_CAP)
    if gates is not None and gates.blocked:
        base = min(base, HARD_BLOCK_SCORE_CAP)

    return max(0, min(100, round(base)))


def breakdown_payload(dimensions: dict[str, int]) -> list[dict]:
    labels = {"match": "匹配", "price": "价格", "seller": "卖家", "evidence": "凭证"}
    return [
        {"key": key, "label": labels[key], "value": max(0, min(100, int(dimensions[key])))}
        for key in ("match", "price", "seller", "evidence")
        if key in dimensions
    ]
