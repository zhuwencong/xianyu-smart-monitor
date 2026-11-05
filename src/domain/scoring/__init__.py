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
    breakdown_payload,
    benchmark_price,
    price_score,
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
    "benchmark_price",
    "breakdown_payload",
    "evaluate_gates",
    "extract_specs",
    "price_score",
    "resolve_overall",
    "resolve_verdict",
    "task_allows_professional",
]
