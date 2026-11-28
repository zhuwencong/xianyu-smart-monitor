"""底层评分体系：客观规格 → 硬门槛 → 分数。

对外只暴露三样东西：

- ``extract_specs``：从标题/描述抽客观事实；
- ``evaluate_gates``：不可协商的硬门槛；
- ``resolve_verdict`` / ``resolve_overall``：判断与分数合成。

任务级 criteria（客户/AI 视角的参考层）只影响维度分与理由文案，
不能突破这里的任何一条 block。
"""
from src.domain.scoring.engine import (
    AI_REFERENCE_WEIGHT,
    apply_dimension_caps,
    bargain_ratio,
    breakdown_payload,
    benchmark_price,
    evaluate_candidate,
    grade_for,
    price_position,
    price_score,
    push_min_score,
    resolve_overall,
    resolve_verdict,
)
from src.domain.scoring.gates import (
    BLOCK,
    HARD_BLOCK_SCORE_CAP,
    MIN_CONSUMER_VRAM_GB,
    WARN,
    GateHit,
    GateResult,
    evaluate_gates,
    task_allows_professional,
)
from src.domain.scoring.perf import expected_gpu_price, performance_score, value_score
from src.domain.scoring.specs import ItemSpecs, extract_specs

__all__ = [
    "AI_REFERENCE_WEIGHT",
    "BLOCK",
    "HARD_BLOCK_SCORE_CAP",
    "MIN_CONSUMER_VRAM_GB",
    "WARN",
    "GateHit",
    "GateResult",
    "ItemSpecs",
    "apply_dimension_caps",
    "bargain_ratio",
    "benchmark_price",
    "breakdown_payload",
    "evaluate_candidate",
    "evaluate_gates",
    "expected_gpu_price",
    "extract_specs",
    "grade_for",
    "performance_score",
    "price_position",
    "price_score",
    "push_min_score",
    "resolve_overall",
    "resolve_verdict",
    "task_allows_professional",
    "value_score",
]
