"""评分引擎：把客观门槛、多维表现和 AI 参考值合成最终分。

三条不可违背的规则：

1. 硬门槛优先。命中 ``gates`` 的 block 项，判断强制为「不匹配」，
   分数按否决严重程度分档封顶（致命 39 / 一般 62），AI 给了多少分都不作数。
2. AI 只做参考。模型的 ``value_score`` 权重被压到 ``AI_REFERENCE_WEIGHT``，
   它只能微调排序，翻不了「能不能买」的结论。
3. 比价必须同型号。只有拿到同型号（或同型号族）中位数时价格维度才计分，
   跨型号均价一律不参与评分。

维度共五个：匹配 / 性能 / 价格 / 卖家 / 凭证。其中「性能」只对显卡类商品
生效（由 ``gpu_perf`` 按型号+显存+世代换算），其它品类会自动剔除并重分配权重。
"""
from __future__ import annotations

from src.domain.scoring.gates import GateResult

DIMENSION_WEIGHTS = {
    "match": 0.22,
    "perf": 0.22,
    "price": 0.26,
    "seller": 0.15,
    "evidence": 0.15,
}

AI_REFERENCE_WEIGHT = 0.25
# AI 判「不匹配」时的分数上限。
#
# 原来这里是 58，结果所有被 AI 否决的商品分数完全一样（实测 37/40 条都是 58），
# 列表上根本看不出「哪张卡被否得可惜」。放宽到 68 之后，好卡（如 GTX1060 6G
# 加权 69.4）会就近显示 68，烂卡（RX580 加权 60.5）显示 60，差异回来了。
#
# 注意这不是「把烂卡放出来」：能不能买仍然由 verdict=gates 决定，
# 分数只表示「这张卡本身有多好」，排序键另有 AI_PRIORITY 把 mismatch 压后。
MISMATCH_CAP = 68
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
    """多维度加权 + AI 参考值微调，再按判断结果封顶。

    **为什么 mismatch 不再一路压到 58**：原先 ``MISMATCH_CAP = 58`` 会把所有
    被否决的商品压成同一个数字，实测 37 条显卡记录里 37 条全是 58 分，完全
    看不出「哪张否决得可惜」。现在改成分档压顶——

    - 严重否决（矿卡/坏卡/维修史/假卡）→ ``SEVERE_BLOCK_SCORE_CAP``：确实不该买，
      分数就该低，但仍保留各维度的相对差异。
    - 一般不匹配（显存差一点、专业卡、超预算）→ ``MISMATCH_CAP`` 附近，仅轻微压制，
      让「好卡但显存 4G」能显示 55-58 而不是和「坏卡」同为 58。

    「能不能买」这件事始终由 verdict 单独表达，分数只负责表示「这卡本身如何」。
    """
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

    if gates is not None and gates.blocked:
        # 区分「致命」和「可惜」：矿卡/坏卡往死里压，其余只做温和封顶。
        if _has_severe_block(gates):
            base = min(base, SEVERE_BLOCK_SCORE_CAP)
        else:
            base = min(base, MILD_BLOCK_SCORE_CAP)
    elif verdict == "verify":
        base = min(base, VERIFY_CAP)
    elif verdict == "mismatch":
        base = min(base, MISMATCH_CAP)

    return max(0, min(100, round(base)))


# 致命否决：这类商品买到就是坑，分数必须明确压到低位。
_SEVERE_BLOCK_KEYS = frozenset(
    {"defect", "mining", "repair", "fake", "professional_card", "accessory"}
)

# 致命否决的上限：40 分以下，与「可惜但还行」拉开明显档位差。
SEVERE_BLOCK_SCORE_CAP = 39

# 一般否决的上限：给到 62，允许好卡在 55-62 区间把差异体现出来。
# 之所以不是 58：58 这个整数一旦封顶，所有被压的记录又变成一排同样的数字。
MILD_BLOCK_SCORE_CAP = 62


def _has_severe_block(gates: GateResult | None) -> bool:
    if gates is None:
        return False
    return any(hit.key in _SEVERE_BLOCK_KEYS for hit in gates.blocks)


def breakdown_payload(dimensions: dict[str, int]) -> list[dict]:
    labels = {
        "match": "匹配",
        "perf": "性能",
        "price": "价格",
        "seller": "卖家",
        "evidence": "凭证",
    }
    return [
        {"key": key, "label": labels[key], "value": max(0, min(100, int(dimensions[key])))}
        for key in ("match", "perf", "price", "seller", "evidence")
        if key in dimensions
    ]
