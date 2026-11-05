from src.domain.scoring.engine import (
    breakdown_payload,
    price_score,
    resolve_overall,
    resolve_verdict,
)
from src.domain.scoring.gates import evaluate_gates
from src.domain.scoring.specs import extract_specs

P620_TITLE = (
    "NVIDIA Quadro P620专业显卡，2G显存，半高设计，低功耗，包邮。"
)


def _blocked_gates():
    return evaluate_gates(specs=extract_specs(P620_TITLE), price=208.0, budget_max="1000")


def test_price_score_uses_same_model_median():
    insight = {"market_median_price": 200.0, "market_scope": "model", "market_sample_count": 8}
    score, source = price_score(208.0, insight, ai_value_score=88)
    assert source == "model"
    assert 70 <= score <= 80


def test_price_score_ignores_cross_model_average():
    # 这正是 P620 的翻车现场：跨型号均价 526.98，同型号样本不足
    insight = {
        "market_avg_price": 526.98,
        "market_median_price": None,
        "market_scope": "insufficient",
        "market_sample_count": 1,
    }
    score, source = price_score(208.0, insight, ai_value_score=88)
    assert source == "ai_reference"
    assert score == 88


def test_price_score_requires_enough_samples():
    insight = {"market_median_price": 200.0, "market_scope": "model", "market_sample_count": 2}
    _score, source = price_score(208.0, insight, ai_value_score=50)
    assert source == "ai_reference"


def test_verdict_is_mismatch_when_hard_gate_blocks():
    verdict = resolve_verdict(
        ai_recommended=True,
        criteria=[{"key": "model_chip", "status": "PASS"}],
        risk_tags=[],
        gates=_blocked_gates(),
    )
    assert verdict == "mismatch"


def test_verdict_follows_ai_when_gates_pass():
    gates = evaluate_gates(specs=extract_specs("影驰GTX1070 8G显卡，包邮"), price=700.0)
    verdict = resolve_verdict(ai_recommended=True, criteria=[], risk_tags=[], gates=gates)
    assert verdict == "recommend"


def test_overall_is_capped_when_blocked():
    score = resolve_overall(
        dimensions={"match": 92, "price": 95, "seller": 92, "evidence": 88},
        ai_value_score=88,
        verdict="mismatch",
        gates=_blocked_gates(),
    )
    assert score <= 40


def test_ai_value_score_only_nudges_the_ranking():
    dims = {"match": 70, "price": 70, "seller": 70, "evidence": 70}
    low = resolve_overall(dimensions=dims, ai_value_score=0, verdict="recommend")
    high = resolve_overall(dimensions=dims, ai_value_score=100, verdict="recommend")
    # AI 参考值权重 25%，极端值最多拉开 25 分左右
    assert high - low <= 26


def test_verify_and_mismatch_caps():
    dims = {"match": 95, "price": 95, "seller": 95, "evidence": 95}
    assert resolve_overall(dimensions=dims, ai_value_score=95, verdict="verify") <= 74
    assert resolve_overall(dimensions=dims, ai_value_score=95, verdict="mismatch") <= 58


def test_breakdown_payload_keeps_four_dimensions():
    payload = breakdown_payload({"match": 1, "price": 2, "seller": 3, "evidence": 4})
    assert [item["label"] for item in payload] == ["匹配", "价格", "卖家", "凭证"]
