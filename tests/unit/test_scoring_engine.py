from src.domain.scoring.engine import (
    apply_dimension_caps,
    breakdown_payload,
    grade_for,
    price_score,
    resolve_overall,
    resolve_verdict,
)
from src.domain.scoring.gates import evaluate_gates
from src.domain.scoring.perf import expected_gpu_price, performance_score, value_score
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


def test_breakdown_payload_keeps_known_dimensions():
    payload = breakdown_payload({"match": 1, "price": 2, "seller": 3, "evidence": 4})
    assert [item["label"] for item in payload] == ["价格", "卖家", "版本", "凭证"]


def test_breakdown_payload_includes_gpu_dimensions():
    payload = breakdown_payload(
        {"match": 1, "price": 2, "value": 3, "seller": 4, "evidence": 5, "performance": 6}
    )
    assert [item["label"] for item in payload] == [
        "价格", "卖家", "版本", "凭证", "性能", "性价比",
    ]


def test_grade_tiers_follow_score():
    assert grade_for(92) == "S"
    assert grade_for(85) == "S"
    assert grade_for(84) == "A"
    assert grade_for(75) == "A"
    assert grade_for(74) == "B"
    assert grade_for(65) == "B"
    assert grade_for(64) == "C"
    assert grade_for(50) == "C"
    assert grade_for(49) == "D"
    assert grade_for(None) is None


def test_big_bargain_without_proof_is_capped():
    # 折价超三成又验不了：便宜不能买断风险
    score, caps = apply_dimension_caps(
        92,
        dimensions={"price": 95, "seller": 80, "match": 85, "condition": 85, "evidence": 30},
        ratio=0.62,
    )
    assert score <= 60
    assert "折价超三成但无法验证" in caps


def test_reseller_and_version_doubt_are_capped():
    reseller, caps_a = apply_dimension_caps(
        90, dimensions={"price": 90, "seller": 30, "match": 85, "condition": 85, "evidence": 80}
    )
    assert reseller <= 65 and "卖家画像不可信" in caps_a
    doubtful, caps_b = apply_dimension_caps(
        90, dimensions={"price": 90, "seller": 85, "match": 30, "condition": 85, "evidence": 80}
    )
    assert doubtful <= 60 and "型号版本存疑" in caps_b


def test_high_score_needs_verifiable_evidence():
    # 85 分以上但凭证缺位，压回 B 级上限 74
    score, caps = apply_dimension_caps(
        88,
        dimensions={"price": 86, "seller": 85, "match": 85, "condition": 85, "evidence": 30},
        ratio=0.90,
    )
    assert score <= 74
    assert "高分但缺少可验证材料" in caps


def test_healthy_candidate_is_not_capped():
    score, caps = apply_dimension_caps(
        88,
        dimensions={"price": 86, "seller": 85, "match": 85, "condition": 85, "evidence": 80},
        ratio=0.90,
    )
    assert score == 88
    assert caps == []


def test_performance_score_ranks_by_model_tier():
    old_card = extract_specs("蓝宝石RX580 8G显卡，包邮", gpu_hint=True)
    modern_card = extract_specs("微星RTX4070 12G显卡，包邮", gpu_hint=True)
    unknown = extract_specs("某型号显卡 8G，包邮", gpu_hint=True)
    assert performance_score(old_card) == 30
    assert performance_score(modern_card) == 80
    assert performance_score(old_card) < performance_score(modern_card)
    # 型号认不出来：不参与加权，而不是瞎给一个分
    assert performance_score(unknown) is None
    # 非显卡品类不给性能分
    assert performance_score(extract_specs("iPhone 15 256G 99新")) is None


def test_value_score_prefers_cheap_for_its_tier():
    rtx4070 = extract_specs("微星RTX4070 12G显卡，包邮", gpu_hint=True)
    cheap = value_score(1800.0, rtx4070)   # 参考价 3800 的一半：捡漏
    expensive = value_score(5500.0, rtx4070)  # 明显高于该档正常价
    assert cheap >= 82
    assert expensive <= 42
    assert cheap > expensive
    # 没有价格就没有性价比
    assert value_score(None, rtx4070) is None


def test_expected_gpu_price_is_monotonic():
    prices = [expected_gpu_price(p) for p in (10, 30, 50, 70, 90)]
    assert prices == sorted(prices)
    assert prices[0] > 0


def test_mismatch_scores_stay_ordered_under_soft_cap():
    # 修复「显卡全是 58 分」：同为不匹配，分高者排前，但都不越过 58
    strong = resolve_overall(
        dimensions={"match": 92, "price": 90, "seller": 80, "evidence": 85, "performance": 80, "value": 85},
        ai_value_score=85,
        verdict="mismatch",
    )
    weak = resolve_overall(
        dimensions={"match": 40, "price": 40, "seller": 50, "evidence": 45, "performance": 30, "value": 35},
        ai_value_score=40,
        verdict="mismatch",
    )
    assert strong > weak
    assert strong <= 58
    assert weak < strong


def test_gpu_dimensions_change_the_ranking():
    # 同价格同判定，4070 和 580 应当靠性能/性价比拉开差距
    base = {"match": 70, "price": 70, "seller": 70, "evidence": 70}
    rtx4070 = dict(base, performance=80, value=72)
    rx580 = dict(base, performance=30, value=82)
    high = resolve_overall(dimensions=rtx4070, ai_value_score=70, verdict="verify")
    low = resolve_overall(dimensions=rx580, ai_value_score=70, verdict="verify")
    assert high > low
    assert high <= 74


def test_gpu_model_label_restores_vendor_prefix():
    from src.domain.scoring.perf import gpu_model_label

    assert gpu_model_label("1070") == "GTX 1070"
    assert gpu_model_label("4070ti") == "RTX 4070 Ti"
    assert gpu_model_label("580") == "RX 580"
    assert gpu_model_label("7600xt") == "RX 7600 XT"
    assert gpu_model_label("vega56") == "Vega 56"
    assert gpu_model_label("p620") == "P620"
    assert gpu_model_label("1030") == "GT 1030"
    assert gpu_model_label("") == ""


def test_gpu_model_label_restores_vendor_prefix():
    from src.domain.scoring.perf import gpu_model_label

    assert gpu_model_label("1070") == "GTX 1070"
    assert gpu_model_label("4070ti") == "RTX 4070 Ti"
    assert gpu_model_label("580") == "RX 580"
    assert gpu_model_label("7600xt") == "RX 7600 XT"
    assert gpu_model_label("vega56") == "Vega 56"
    assert gpu_model_label("p620") == "P620"
    assert gpu_model_label("1030") == "GT 1030"
    assert gpu_model_label("") == ""
