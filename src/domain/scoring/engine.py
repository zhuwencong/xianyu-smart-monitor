"""评分引擎：把客观门槛、五维表现和 AI 参考值合成最终分与等级。

四条不可违背的规则：

1. 硬门槛优先。命中 ``gates`` 的 block 项，分数封顶 ``HARD_BLOCK_SCORE_CAP``，
   判断强制为「不匹配」，AI 给了多少分都不作数。
2. AI 只做参考。模型的 ``value_score`` 权重被压到 ``AI_REFERENCE_WEIGHT``，
   它只能微调排序，翻不了「能不能买」的结论。
3. 比价必须同型号。只有拿到同型号（或同型号族）中位数时价格维度才计分，
   跨型号均价一律不参与评分。
4. 便宜不能买断风险。折价异常、卖家可疑、版本存疑、状况差、可验证性缺位，
   各自触发封顶，防止「价格分拉满就冲」。
"""
from __future__ import annotations

import os

from src.domain.scoring.gates import HARD_BLOCK_SCORE_CAP, GateResult

# 权重与《手机捡漏打分维度》对齐：价格是主维度，其余按「决定买回来是不是废铁」排。
# 显卡的 performance/value 是品类附加维度，出现时按实际维度归一化，不会挤掉主维度。
DIMENSION_WEIGHTS = {
    "price": 0.30,
    "seller": 0.20,
    "match": 0.15,
    "condition": 0.15,
    "evidence": 0.12,
    "performance": 0.10,
    "value": 0.10,
}

AI_REFERENCE_WEIGHT = 0.25
MISMATCH_CAP = 58
VERIFY_CAP = 74
NEUTRAL_SCORE = 70
# 软封顶时，原本被一刀切平的 (cap, 100] 区间被压缩进 (cap - SPREAD, cap]，
# 保序：同是「不匹配」的卡也能按基础分拉开差距，而不是全部顶格一个数。
CAP_SPREAD = 8

# 封顶规则阈值
BIG_BARGAIN_RATIO = 0.70      # 挂价低于同型号中位数 30% 以上
WEAK_DIMENSION = 40           # 维度分低于此视为“这一项不可接受”
CAP_BARGAIN_UNVERIFIABLE = 60 # 大漏 + 无法验证
CAP_WEAK_SELLER = 65          # 卖家画像不可信
CAP_VERSION_DOUBT = 60        # 版本/型号存疑
CAP_BAD_CONDITION = 65        # 状况差或有拆修
CAP_HIGH_NO_PROOF = 74        # 高分但可验证性缺位，压到 B 级
CAP_NO_DISCOUNT = 74          # 价格不低于行情：不是漏，最多 B 级
NO_DISCOUNT_RATIO = 1.01      # 留 1% 容差，避免基准误差误封

GRADE_TIERS = ((85, "S"), (75, "A"), (65, "B"), (50, "C"))

# 推送最低分：低于这条线不打扰人。可用环境变量覆盖，无需改代码。
PUSH_MIN_SCORE_DEFAULT = 75


def push_min_score() -> int:
    """当前生效的推送门槛。面板要显示它，推送要执行它，必须是同一个来源。"""
    raw = os.getenv("PUSH_MIN_SCORE")
    if raw is None or str(raw).strip() == "":
        return PUSH_MIN_SCORE_DEFAULT
    try:
        return max(0, min(100, int(raw)))
    except (TypeError, ValueError):
        return PUSH_MIN_SCORE_DEFAULT

_COMPARABLE_SCOPES = {"model", "family"}
_MIN_COMPARABLE_SAMPLES = 3
# keyword 口径：同一搜索词下的中位数，能反映大体位置，但会混进不同存储/成色。
# 用它计分但向中性收缩，避免粗糙基准把排序带偏。
KEYWORD_SCOPE = "keyword"
KEYWORD_TRUST = 0.7
_MIN_KEYWORD_SAMPLES = 5

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


def bargain_ratio(price: float | None, insight: dict) -> float | None:
    """挂价 ÷ 同型号行情中位数。没有可比基准时返回 None，绝不拿跨型号均价凑数。

    只认 model/family 口径，专供封顶规则使用——封顶是硬规则，不能建立在粗糙基准上。
    """
    reference, _samples, _scope = benchmark_price(insight)
    if not price or not reference or reference <= 0:
        return None
    return price / reference


def price_position(price: float | None, insight: dict) -> tuple[float | None, str]:
    """展示用的价格位置：(挂价 ÷ 行情中位数, 口径)。

    没有同型号基准时退到关键词口径（手机任务的常见情况），口径一并返回，
    UI 据此标注「按关键词行情估算」，避免把粗口径当精确值展示。
    """
    reference, _samples, scope = benchmark_price(insight)
    if price and reference and reference > 0:
        return price / reference, scope
    if price:
        keyword_median = _to_float(insight.get("market_median_price"))
        try:
            keyword_samples = int(insight.get("market_sample_count") or 0)
        except (TypeError, ValueError):
            keyword_samples = 0
        if (
            keyword_median
            and keyword_median > 0
            and str(insight.get("market_scope") or "") == KEYWORD_SCOPE
            and keyword_samples >= _MIN_KEYWORD_SAMPLES
        ):
            return price / keyword_median, KEYWORD_SCOPE
    return None, ""


def _ratio_to_score(ratio: float) -> int:
    """折扣率 → 价格分。折价越多分越高，溢价越多分越低。"""
    if ratio <= 0.75:
        return 95
    if ratio <= 0.85:
        return 90
    if ratio <= 0.95:
        return 84
    if ratio <= 1.05:
        return 76
    if ratio <= 1.15:
        return 64
    if ratio <= 1.3:
        return 50
    return 36


def price_score(price: float | None, insight: dict, ai_value_score) -> tuple[int, str]:
    """价格合理度。

    取值优先级：同型号中位数（精确）→ 关键词中位数（收缩计分）→ AI 参考值 → 中性。
    绝不拿跨型号均价凑数——那正是 P620「均价 526 卖 208」翻车的原因。
    """
    reference, _samples, scope = benchmark_price(insight)
    if price and reference and reference > 0:
        return _ratio_to_score(price / reference), scope

    if price:
        keyword_median = _to_float(insight.get("market_median_price"))
        try:
            keyword_samples = int(insight.get("market_sample_count") or 0)
        except (TypeError, ValueError):
            keyword_samples = 0
        if (
            keyword_median
            and keyword_median > 0
            and str(insight.get("market_scope") or "") == KEYWORD_SCOPE
            and keyword_samples >= _MIN_KEYWORD_SAMPLES
        ):
            raw = _ratio_to_score(price / keyword_median)
            return round(NEUTRAL_SCORE + (raw - NEUTRAL_SCORE) * KEYWORD_TRUST), KEYWORD_SCOPE

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


def _soft_cap(value: float, cap: int) -> float:
    """把 (cap, 100] 保序压缩进 (cap - CAP_SPREAD, cap]，不再一刀切平。

    旧行为是 min(value, cap)：所有超限商品顶格同一个数（显卡全是 58 分的根因）。
    压缩后上限不变（不会把「不匹配」顶进「推荐」区间），但保留了排序信息。
    """
    if value <= cap:
        return value
    span = 100 - cap
    return cap - (value - cap) / span * CAP_SPREAD


def resolve_overall(
    *,
    dimensions: dict[str, int],
    ai_value_score,
    verdict: str,
    gates: GateResult | None = None,
) -> int:
    """多维加权 + AI 参考值微调，再按判断结果封顶。

    没出现的维度（如非显卡商品没有 performance/value）自动跳过，
    权重按实际出现的维度归一化。
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

    if verdict == "verify":
        base = _soft_cap(base, VERIFY_CAP)
    elif verdict == "mismatch":
        base = _soft_cap(base, MISMATCH_CAP)
    if gates is not None and gates.blocked:
        base = min(base, HARD_BLOCK_SCORE_CAP)

    return max(0, min(100, round(base)))


def apply_dimension_caps(
    score: int,
    *,
    dimensions: dict[str, int],
    ratio: float | None = None,
) -> tuple[int, list[str]]:
    """按维度短板封顶。返回 (封顶后分数, 触发的规则说明)。

    顺序按危害程度从大到小，一个商品可以同时命中多条，取最低上限。
    """
    caps: list[str] = []
    evidence = dimensions.get("evidence")
    seller = dimensions.get("seller")
    match = dimensions.get("match")
    condition = dimensions.get("condition")

    if ratio is not None and ratio <= BIG_BARGAIN_RATIO and evidence is not None and evidence <= WEAK_DIMENSION:
        caps.append("折价超三成但无法验证")
        score = min(score, CAP_BARGAIN_UNVERIFIABLE)
    if match is not None and match <= WEAK_DIMENSION:
        caps.append("型号版本存疑")
        score = min(score, CAP_VERSION_DOUBT)
    if seller is not None and seller <= WEAK_DIMENSION:
        caps.append("卖家画像不可信")
        score = min(score, CAP_WEAK_SELLER)
    if condition is not None and condition <= WEAK_DIMENSION:
        caps.append("机器状况差或有拆修")
        score = min(score, CAP_BAD_CONDITION)
    # 高分必须配得上「能验证」：再好看，验不了就压回 B 级。
    if score >= 85 and evidence is not None and evidence <= WEAK_DIMENSION:
        caps.append("高分但缺少可验证材料")
        score = min(score, CAP_HIGH_NO_PROOF)
    # 捡漏的定义是价差：不比行情便宜，其余维度再漂亮也不是漏。
    if ratio is not None and ratio >= NO_DISCOUNT_RATIO:
        caps.append("价格不低于行情，不算捡漏")
        score = min(score, CAP_NO_DISCOUNT)
    return max(0, min(100, score)), caps


def grade_for(score: int | None) -> str | None:
    """分数 → 等级。S 立刻联系 / A 可谈 / B 补证据 / C 观察 / D 放弃。"""
    if score is None:
        return None
    for threshold, grade in GRADE_TIERS:
        if score >= threshold:
            return grade
    return "D"


# 维度分来自 criteria 状态：PASS/WARN/FAIL 三档，缺信息按中性偏低处理。
STATUS_SCORE = {
    "PASS": 92,
    "WARNING": 62,
    "WARN": 62,
    "FAIL": 24,
    "NEEDS_MANUAL_CHECK": 58,
}

MATCH_KEYS = ("model_chip", "model", "storage")
SELLER_KEYS = ("seller_type", "seller_credit")
CONDITION_KEYS = (
    "condition", "history", "battery_health", "battery", "appearance", "function", "screen",
)
EVIDENCE_KEYS = (
    "warranty", "verification", "accessories", "shipping",
    "account_and_codes", "account_lock", "imei", "invoice", "codes",
)


def _status_values(status_by_key: dict[str, str], keys: tuple[str, ...]) -> list[int]:
    return [STATUS_SCORE.get(str(status_by_key[k]).upper(), 65) for k in keys if k in status_by_key]


def _avg(values: list[int], default: int) -> int:
    return round(sum(values) / len(values)) if values else default


def evaluate_candidate(
    *,
    analysis: dict,
    status_by_key: dict[str, str],
    price: float | None,
    insight: dict,
    verdict: str,
    gates: GateResult | None = None,
    performance: int | None = None,
    value: int | None = None,
) -> dict:
    """把一份 AI 分析 + 行情 + 客观门槛算成完整评分结果。

    这是唯一的打分入口：分析阶段（决定推不推）和面板（决定排第几）都调它，
    避免两处各算一遍导致「推送了但面板分低」这种自相矛盾。
    """
    raw_match = _avg(_status_values(status_by_key, MATCH_KEYS), 72)
    match = raw_match
    if verdict == "mismatch":
        match = min(match, 35)
    elif verdict == "verify":
        match = min(match, 70)

    dimensions = {
        "price": price_score(price, insight, analysis.get("value_score"))[0],
        "seller": _avg(_status_values(status_by_key, SELLER_KEYS), 65),
        "match": match,
        "condition": _avg(_status_values(status_by_key, CONDITION_KEYS), 62),
        "evidence": _avg(_status_values(status_by_key, EVIDENCE_KEYS), 60),
    }
    if performance is not None:
        dimensions["performance"] = performance
    if value is not None:
        dimensions["value"] = value

    score = resolve_overall(
        dimensions=dimensions,
        ai_value_score=analysis.get("value_score"),
        verdict=verdict,
        gates=gates,
    )

    price_ratio = bargain_ratio(price, insight)
    gap, gap_scope = price_position(price, insight)
    # 「版本存疑」用原始匹配分：mismatch 的压制是结论，不是型号真的不对。
    cap_dimensions = dict(dimensions)
    cap_dimensions["match"] = raw_match
    score, caps = apply_dimension_caps(score, dimensions=cap_dimensions, ratio=gap)

    return {
        "score": score,
        "grade": grade_for(score),
        "caps": caps,
        "breakdown": breakdown_payload(dimensions),
        "dimensions": dimensions,
        "bargain_ratio": round(price_ratio, 3) if price_ratio is not None else None,
        "price_gap": round(gap, 3) if gap is not None else None,
        "price_gap_scope": gap_scope or None,
    }


def breakdown_payload(dimensions: dict[str, int]) -> list[dict]:
    labels = {
        "price": "价格",
        "seller": "卖家",
        "match": "版本",
        "condition": "状况",
        "evidence": "凭证",
        "performance": "性能",
        "value": "性价比",
    }
    order = ("price", "seller", "match", "condition", "evidence", "performance", "value")
    return [
        {"key": key, "label": labels[key], "value": max(0, min(100, int(dimensions[key])))}
        for key in order
        if key in dimensions
    ]
