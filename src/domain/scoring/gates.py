"""评分体系的底层硬门槛。

这里的判定是**不可协商**的：它只吃 `specs.ItemSpecs` 抽出来的客观事实和任务
自身的预算/物流配置，不看 AI 的任何输出。任何一条 ``severity="block"`` 命中，
上层都必须把商品压到「不匹配」，并封顶分数——prompt 怎么改、模型怎么说都翻不了案。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from src.domain.scoring.specs import ItemSpecs

# 消费级显卡的显存底线：低于它就是亮机卡，不参与「捡漏」推荐。
MIN_CONSUMER_VRAM_GB = 4

# 一票否决后的分数上限，保证它排不进列表前排。
HARD_BLOCK_SCORE_CAP = 40

BLOCK = "block"
WARN = "warn"

BAD_SELLER_CREDITS = ("卖家信用极差", "卖家信用较差", "信用极差", "信用较差")

# 任务本身就在收专业卡时，不应该被「专业卡一票否决」误伤。
_PROFESSIONAL_TASK_TOKENS = ("专业卡", "专业显卡", "quadro", "tesla", "图形卡", "计算卡", "亮机卡")


@dataclass(frozen=True)
class GateHit:
    """一条硬门槛判定结果。"""

    key: str
    label: str
    detail: str
    severity: str = BLOCK

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class GateResult:
    hits: tuple[GateHit, ...] = ()

    @property
    def blocks(self) -> tuple[GateHit, ...]:
        return tuple(hit for hit in self.hits if hit.severity == BLOCK)

    @property
    def warnings(self) -> tuple[GateHit, ...]:
        return tuple(hit for hit in self.hits if hit.severity == WARN)

    @property
    def blocked(self) -> bool:
        return bool(self.blocks)

    def as_list(self) -> list[dict]:
        return [hit.as_dict() for hit in self.hits]


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("¥", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def task_allows_professional(*texts: object) -> bool:
    """任务描述里明确在收专业卡/亮机卡时，跳过专业卡否决。"""
    joined = " ".join(str(text or "") for text in texts).lower()
    return any(token in joined for token in _PROFESSIONAL_TASK_TOKENS)


def evaluate_gates(
    *,
    specs: ItemSpecs,
    price: float | None = None,
    budget_min=None,
    budget_max=None,
    require_shipping: bool = False,
    allow_professional: bool = False,
    seller_credit: str = "",
) -> GateResult:
    """按客观事实判定硬门槛。纯函数，不读数据库、不调模型。"""
    hits: list[GateHit] = []

    if specs.defects:
        hits.append(
            GateHit(
                key="defect",
                label="功能故障",
                detail="标题/描述明确提到：" + "、".join(specs.defects),
            )
        )

    if specs.mining_signals:
        hits.append(
            GateHit(
                key="mining",
                label="矿卡/矿机",
                detail="命中矿卡相关表述：" + "、".join(specs.mining_signals),
            )
        )

    if specs.repair_signals:
        hits.append(
            GateHit(
                key="repair",
                label="维修史",
                detail="命中维修相关表述：" + "、".join(specs.repair_signals),
            )
        )

    if specs.bulk_disassembly:
        hits.append(
            GateHit(
                key="bulk_disassembly",
                label="批量拆机",
                detail="命中批量/拆机类表述，疑似商家批量货源",
            )
        )

    if specs.is_gpu and not allow_professional and specs.card_class == "professional":
        hits.append(
            GateHit(
                key="professional_card",
                label="专业卡/计算卡",
                detail="识别为专业卡或计算卡，不属于消费级显卡",
            )
        )

    if (
        specs.is_gpu
        and specs.card_class != "professional"
        and specs.vram_gb is not None
        and specs.vram_gb < MIN_CONSUMER_VRAM_GB
    ):
        hits.append(
            GateHit(
                key="vram",
                label="显存不足",
                detail=f"显存 {specs.vram_gb}G，低于 {MIN_CONSUMER_VRAM_GB}G 的消费级底线",
            )
        )

    if require_shipping and specs.pickup_only:
        hits.append(
            GateHit(
                key="pickup_only",
                label="仅限自提",
                detail="任务要求可邮寄，但商品明确仅限自提/面交",
            )
        )

    upper = _to_float(budget_max)
    if price is not None and upper is not None and upper > 0 and price > upper:
        hits.append(
            GateHit(
                key="budget",
                label="超出预算",
                detail=f"售价 ¥{price:g} 超出任务预算上限 ¥{upper:g}",
            )
        )

    lower = _to_float(budget_min)
    if price is not None and lower is not None and lower > 0 and price < lower:
        hits.append(
            GateHit(
                key="budget_low",
                label="低于预算下限",
                detail=f"售价 ¥{price:g} 低于任务预算下限 ¥{lower:g}，可能是配件/瑕疵件",
                severity=WARN,
            )
        )

    credit = str(seller_credit or "")
    if any(token in credit for token in BAD_SELLER_CREDITS):
        hits.append(
            GateHit(
                key="seller_credit",
                label="卖家信用差",
                detail=f"卖家信用等级为「{credit}」",
            )
        )

    if specs.pickup_only:
        hits.append(
            GateHit(
                key="pickup_note",
                label="仅限自提",
                detail="商品明确仅限自提，异地交易存在风险",
                severity=WARN,
            )
        )

    if not specs.ships and not specs.pickup_only:
        hits.append(
            GateHit(
                key="shipping_unknown",
                label="物流未知",
                detail="未识别到包邮/可邮寄信息",
                severity=WARN,
            )
        )

    return GateResult(hits=tuple(hits))
