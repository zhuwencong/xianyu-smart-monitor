"""评分体系的底层事实层。

这里只做一件事：把商品标题/描述变成**可判定的事实**（型号、显存、卡型、
故障/矿卡征兆、物流方式）。它不调用 AI、不读任务配置、不依赖任何人工标注，
因此上层无论怎么改 prompt、怎么调权重，都改不掉这里抽出来的结论。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

_SEPARATOR_RE = re.compile(r"[^0-9a-z]+")
_SEPARATOR_CJK_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff¥]+")

# GeForce / Radeon 这类「厂商前缀 + 数字型号」的写法
_GPU_MODEL_RE = re.compile(
    r"\b(gtx|rtx|gts|gt|rx|r9|hd)\s?(\d{3,4})(?:\s?(ti|super|xt|gre|x3d))?\b"
)
# Quadro / Tesla 这类「单字母 + 数字」的专业卡写法（P620 / K2200 / M4000 / T400）
_PRO_MODEL_RE = re.compile(r"\b(?:quadro\s?)?([pktm])\s?(\d{3,4})\b")
_VEGA_RE = re.compile(r"\bvega\s?(\d{2})\b")
# 『影驰1060 6G』『索泰1660super』这类省略厂商前缀的写法：
# 只在显卡语境下启用，并且必须命中已知型号号段，避免把价格当年份/型号。
_BARE_MODEL_RE = re.compile(
    r"(?<![\d¥$])(\d{3,4})(?:\s?(ti|super|xt|gre|x3d))?(?![\d])"
    r"(?!\s?(元|块|出|刀|包邮|顺丰|邮))"
)
_VRAM_RE = re.compile(r"(?<!\d)(\d{1,2})\s?g(?:b)?(?!\d)")
_GPU_CONTEXT_TOKENS = ("显卡", "顯卡", "gpu", "显存", "quadro", "geforce", "radeon", "独显")

# 已知桌面显卡型号号段；只认这些数字，宁可漏认也不要瞎认。
_KNOWN_MODEL_NUMBERS = frozenset(
    {
        # NVIDIA
        710, 730, 740, 750, 760, 770, 780, 950, 960, 970, 980,
        1030, 1050, 1060, 1070, 1080, 1630, 1650, 1660,
        2060, 2070, 2080, 3050, 3060, 3070, 3080, 3090,
        4060, 4070, 4080, 4090, 5090,
        # AMD Radeon
        460, 470, 480, 550, 560, 570, 580, 590,
        5500, 5600, 5700, 6400, 6500, 6600, 6650, 6700, 6750, 6800, 6900, 6950,
        7600, 7700, 7800, 7900,
        # Intel Arc
        380, 750, 770,
    }
)

_PROFESSIONAL_TOKENS = (
    "quadro",
    "tesla",
    "rtx a",
    "firepro",
    "radeon pro",
    "专业卡",
    "专业显卡",
    "图形卡",
    "计算卡",
    "加速卡",
)
_MINING_TOKENS = ("矿卡", "挖矿", "矿机", "矿场", "锻炼", "算力卡", "p106", "p104", "p102")
_DEFECT_TOKENS = (
    "点不亮",
    "不点亮",
    "无法点亮",
    "开不了机",
    "花屏",
    "黑屏",
    "无输出",
    "无显示",
    "坏卡",
    "报废",
    "短路",
    "烧毁",
    "掉驱动",
    "缺件",
)
_REPAIR_TOKENS = (
    "维修过",
    "返修",
    "拆修",
    "修过",
    "换过显存",
    "换显存",
    "补焊",
    "飞线",
    "水洗",
    "浸水",
    "翻新",
)
_BULK_DISASSEMBLY_TOKENS = ("网吧拆机", "服务器拆机", "批量拆机", "大量拆机", "批量出")
_PICKUP_ONLY_TOKENS = ("仅限自提", "只出本地", "同城自提", "不邮寄", "不发货", "只能自提")
_SHIPPING_TOKENS = ("包邮", "可邮寄", "发快递", "走顺丰", "顺丰包邮")

# 「没有 / 非 / 不是」这类否定前缀，命中时要反过来读
_NEGATION_PREFIXES = ("非", "无", "不", "没", "未")
# 「矿卡白送」这类反话/强调说法，同样不算命中
_NEGATION_SUFFIXES = ("白送", "免费送", "不要钱", "倒贴")


@dataclass(frozen=True)
class ItemSpecs:
    """一件商品的客观规格事实。"""

    raw_text: str = ""
    model_family: str = ""
    vram_gb: int | None = None
    card_class: str = "unknown"  # consumer / professional / mining / unknown
    is_gpu: bool = False
    defects: tuple[str, ...] = ()
    mining_signals: tuple[str, ...] = ()
    repair_signals: tuple[str, ...] = ()
    bulk_disassembly: bool = False
    pickup_only: bool = False
    ships: bool = False

    @property
    def has_blocking_defect(self) -> bool:
        return bool(self.defects)


def _normalize(text: Iterable[object]) -> str:
    joined = " ".join(str(part or "") for part in text)
    return _SEPARATOR_RE.sub(" ", joined.lower()).strip()


def _normalize_cjk(text: Iterable[object]) -> str:
    """保留中文的归一化文本：用来判断『580元出』这类价格语境。"""
    joined = " ".join(str(part or "") for part in text)
    return _SEPARATOR_CJK_RE.sub(" ", joined.lower()).strip()


def _raw(text: Iterable[object]) -> str:
    return " ".join(str(part or "") for part in text).lower()


def _has_token(raw: str, token: str) -> bool:
    """带否定判断的关键词命中：『非矿卡』『没有修过』不算命中。"""
    if not token:
        return False
    start = raw.find(token)
    while start != -1:
        prefix = raw[max(0, start - 3):start]
        tail = raw[start + len(token): start + len(token) + 2]
        negated = any(neg in prefix for neg in _NEGATION_PREFIXES) or any(
            word in tail for word in _NEGATION_SUFFIXES
        )
        if not negated:
            return True
        start = raw.find(token, start + 1)
    return False


def _matched_tokens(raw: str, tokens: Iterable[str]) -> tuple[str, ...]:
    hits: list[str] = []
    for token in tokens:
        if token in hits:
            continue
        if _has_token(raw, token):
            hits.append(token)
    # 「维修过」已经包含了「修过」，只保留更具体的那个
    return tuple(
        hit for hit in hits if not any(hit != other and hit in other for other in hits)
    )


def _extract_bare_model(norm: str) -> tuple[str, str]:
    """在已知号段里找省略厂商前缀的型号，例如『索泰1660super』『580显卡8g』。

    传入的必须是保留中文的归一化文本，这样『580元出』才能被价格词挡掉。
    """
    for match in _BARE_MODEL_RE.finditer(norm):
        digits = match.group(1)
        if not digits.isdigit():
            continue
        number = int(digits)
        if number not in _KNOWN_MODEL_NUMBERS:
            continue
        suffix = match.group(2) or ""
        card = "mining" if str(number) in {"104", "106", "102"} else "consumer"
        return f"{number}{suffix}", card
    return "", "unknown"


def _extract_model(norm: str, norm_cjk: str, raw: str, gpu_hint: bool) -> tuple[str, str]:
    """返回 (型号族, 卡型)。型号族是归一化后的可比对标识。

    统一只用「数字型号 + 后缀」，不保留厂商前缀，
    这样『GTX1070』『影驰1070』『1070 8G』会落进同一个族。
    """
    match = _GPU_MODEL_RE.search(norm)
    if match:
        number, suffix = match.group(2), (match.group(3) or "")
        card = "mining" if number in {"104", "106", "102"} else "consumer"
        return f"{int(number)}{suffix}", card

    match = _VEGA_RE.search(norm)
    if match:
        return f"vega{match.group(1)}", "consumer"

    match = _PRO_MODEL_RE.search(norm)
    if match:
        letter, number = match.group(1), match.group(2)
        return f"{letter}{number}", "professional"

    # 省略厂商前缀的写法：需要显卡语境（任务本身是显卡任务，或标题里提到显卡）
    has_gpu_context = gpu_hint or any(token in raw for token in _GPU_CONTEXT_TOKENS)
    if has_gpu_context:
        return _extract_bare_model(norm_cjk)

    return "", "unknown"


def looks_like_gpu_task(*texts: object) -> bool:
    """任务/关键词层面判断是不是显卡类任务。"""
    joined = " ".join(str(text or "") for text in texts).lower()
    if any(token in joined for token in _GPU_CONTEXT_TOKENS):
        return True
    return any(
        token in joined for token in ("gtx", "rtx", "quadro", "rx5", "rx6", "rx7", "vega")
    )


def extract_specs(
    title: object = "",
    description: object = "",
    *,
    gpu_hint: bool = False,
) -> ItemSpecs:
    """从标题与描述里抽取客观规格；任何异常都退化成「抽不到」，绝不抛错。"""
    try:
        norm = _normalize((title, description))
        norm_cjk = _normalize_cjk((title, description))
        raw = _raw((title, description))
    except Exception:  # pragma: no cover - 防御性兜底
        return ItemSpecs()

    model_family, card_class = _extract_model(norm, norm_cjk, raw, gpu_hint)

    is_gpu = (
        bool(model_family)
        or gpu_hint
        or any(token in raw for token in _GPU_CONTEXT_TOKENS)
    )

    vram_gb: int | None = None
    if is_gpu:
        vram_match = _VRAM_RE.search(norm)
        if vram_match:
            try:
                value = int(vram_match.group(1))
            except ValueError:
                value = 0
            if 1 <= value <= 64:
                vram_gb = value

    if any(token in raw for token in _PROFESSIONAL_TOKENS):
        card_class = "professional"
    mining = _matched_tokens(raw, _MINING_TOKENS)
    if mining:
        card_class = "mining"

    return ItemSpecs(
        raw_text=raw,
        model_family=model_family,
        vram_gb=vram_gb,
        card_class=card_class,
        is_gpu=is_gpu,
        defects=_matched_tokens(raw, _DEFECT_TOKENS),
        mining_signals=mining,
        repair_signals=_matched_tokens(raw, _REPAIR_TOKENS),
        bulk_disassembly=bool(_matched_tokens(raw, _BULK_DISASSEMBLY_TOKENS)),
        pickup_only=bool(_matched_tokens(raw, _PICKUP_ONLY_TOKENS))
        and not bool(_matched_tokens(raw, _SHIPPING_TOKENS)),
        ships=bool(_matched_tokens(raw, _SHIPPING_TOKENS)),
    )
