"""显卡性能与性价比维度的事实基准。

- ``performance_score``：按型号族给出 0-100 的相对性能分（跨厂商可比，
  以 RTX 5090 = 100 为锚）。型号认不出来时返回 None，上层直接不参与加权。
- ``value_score``：性价比 = 售价相对「该性能档的二手参考价」的合理度。
  参考价由性能分经分段线性曲线推出，只需要维护一条曲线，不用维护几百个型号价。

表里的数字是**排序用的相对值**，不是跑分；目的只有一个：让 580 和 4070
在同一次浏览里能拉开差距。数字偏保守，宁可低估新卡。
"""
from __future__ import annotations

import re

from src.domain.scoring.specs import ItemSpecs

# 型号族（specs 归一化后的 key）→ 相对性能分 0-100。
# 锚点：5090=100；4090=96；3080=75；3060=52；580=30；1060=33。
_PERF_TABLE: dict[str, int] = {
    # NVIDIA GeForce
    "5090": 100, "4090": 96,
    "4080": 90, "4080super": 92,
    "4070ti": 84, "4070": 80,
    "4060ti": 62, "4060": 60,
    "3090ti": 82, "3090": 80,
    "3080ti": 78, "3080": 75,
    "3070ti": 68, "3070": 66,
    "3060ti": 58, "3060": 52,
    "3050": 42,
    "2080ti": 72, "2080super": 66, "2080": 65,
    "2070super": 60, "2070": 58,
    "2060super": 52, "2060": 50,
    "1660ti": 42, "1660super": 40, "1660": 38,
    "1650super": 30, "1650": 28,
    "1080ti": 66, "1080": 58,
    "1070ti": 50, "1070": 48,
    "1060": 33, "1050ti": 22, "1050": 18, "1030": 8,
    "980ti": 52, "980": 48, "970": 38, "960": 28, "950": 20,
    "780": 30, "770": 24, "760": 20, "750ti": 14, "750": 12,
    "740": 8, "730": 6, "710": 4,
    # AMD Radeon
    "7900xtx": 88, "7900xt": 84, "7900gre": 78,
    "7800xt": 76, "7700xt": 70, "7700": 64,
    "7600xt": 58, "7600": 54,
    "6950xt": 78, "6900xt": 76, "6800xt": 74, "6800": 68,
    "6750xt": 64, "6700xt": 62, "6700": 56,
    "6650xt": 52, "6650": 48, "6600xt": 50, "6600": 46,
    "6500xt": 30, "6400": 24,
    "5700xt": 48, "5700": 45, "5600xt": 42, "5500xt": 32,
    "590": 34, "580": 30, "570": 24, "480": 22, "470": 20, "460": 14,
    "vega64": 48, "vega56": 44,
    # NVIDIA 专业卡（按图形性能折算，计算场景另说）
    "p620": 5, "p1000": 12, "p2000": 20, "p2200": 24,
    "p4000": 35, "p5000": 48, "p6000": 60,
    "k620": 6, "k2200": 12, "m2000": 18, "m4000": 32,
    "t400": 7, "t600": 10, "t1000": 16, "t2000": 28, "t4000": 40,
    # 矿卡（p106≈1060、p104≈1070、p102≈1080 级核心）
    "106": 30, "104": 44, "102": 56,
}

# 性能分 → 二手参考价（¥）的分段线性锚点。
# 语义：这一档的卡在二手市场「正常的成交价位」大概在哪。
_PRICE_ANCHORS: tuple[tuple[int, int], ...] = (
    (0, 50), (5, 80), (10, 120), (20, 200), (30, 320),
    (40, 600), (50, 1100), (60, 1800), (70, 2600),
    (80, 3800), (90, 5500), (100, 8000),
)

# 性价比档位：售价 / 参考价 → 分数。
_VALUE_TIERS: tuple[tuple[float, int], ...] = (
    (0.60, 95), (0.75, 90), (0.90, 82),
    (1.05, 72), (1.20, 58), (1.40, 42),
)
_VALUE_FLOOR = 28


def performance_score(specs: ItemSpecs) -> int | None:
    """型号认得出来才打分；认不出返回 None（上层跳过该维度）。"""
    if not specs or not specs.is_gpu:
        return None
    family = str(specs.model_family or "").strip().lower()
    if not family:
        return None
    score = _PERF_TABLE.get(family)
    if score is None:
        return None
    return max(0, min(100, int(score)))


def expected_gpu_price(perf: int) -> float:
    """性能分 → 该档二手参考价（¥），分段线性插值。"""
    points = list(_PRICE_ANCHORS)
    value = max(0, min(100, int(perf)))
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            if x1 == x0:
                return float(y1)
            return float(y0 + (y1 - y0) * (value - x0) / (x1 - x0))
    return float(points[-1][1])


def value_score(price: float | None, specs: ItemSpecs) -> int | None:
    """性价比：性能档参考价 vs 售价。缺价或缺性能档都返回 None。"""
    perf = performance_score(specs)
    if perf is None:
        return None
    if price is None or price <= 0:
        return None
    reference = expected_gpu_price(perf)
    if reference <= 0:
        return None
    ratio = float(price) / reference
    for upper, score in _VALUE_TIERS:
        if ratio <= upper:
            return score
    return _VALUE_FLOOR


# 型号族 → 展示名用的号段归属（只影响 UI 文案，不参与打分）
_NVIDIA_4DIGIT = frozenset(
    {1030, 1050, 1060, 1070, 1080, 1630, 1650, 1660,
     2060, 2070, 2080, 3050, 3060, 3070, 3080, 3090,
     4060, 4070, 4080, 4090, 5090}
)
_AMD_3DIGIT = frozenset({460, 470, 480, 550, 560, 570, 580, 590})
_AMD_4DIGIT = frozenset(
    {5500, 5600, 5700, 6400, 6500, 6600, 6650, 6700, 6750,
     6800, 6900, 6950, 7600, 7700, 7800, 7900}
)
_NVIDIA_3DIGIT = frozenset({710, 730, 740, 750, 760, 770, 780, 950, 960, 970, 980})
_GT_PREFIX = frozenset({710, 730, 740, 1030})

_SUFFIX_LABEL = {"ti": " Ti", "super": " Super", "xt": " XT", "gre": " GRE"}


def gpu_model_label(family: str) -> str:
    """把归一化型号族（'1070' / 'p620' / 'vega56'）还原成人看的展示名。"""
    text = str(family or "").strip().lower()
    if not text:
        return ""
    if text.startswith("vega"):
        return f"Vega {text[4:]}"
    match = re.fullmatch(r"([pktm])(\d{3,4})", text)
    if match:
        return f"{match.group(1).upper()}{match.group(2)}"
    match = re.fullmatch(r"(\d{3,4})(ti|super|xt|gre)?", text)
    if not match:
        return text.upper()
    number, suffix = int(match.group(1)), (match.group(2) or "")
    if number in _GT_PREFIX:
        prefix = "GT"
    elif number in _NVIDIA_4DIGIT or number in _NVIDIA_3DIGIT:
        prefix = "RTX" if number >= 2060 or number == 5090 else "GTX"
    elif number in _AMD_3DIGIT or number in _AMD_4DIGIT:
        prefix = "RX"
    elif number in {106, 104, 102}:
        return f"P{number}"
    else:
        prefix = "GTX" if number < 2000 else "RTX"
    return f"{prefix} {number}{_SUFFIX_LABEL.get(suffix, '')}"
