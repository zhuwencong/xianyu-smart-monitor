"""显卡性能维度：把型号变成 0-100 的性能分。

为什么需要这个模块：原先的四个维度（匹配/价格/卖家/凭证）里，显卡**性能**
完全缺席——显存多大、几代架构、什么档位，全被压进「匹配」这一项。结果一张
GTX 1050Ti 和一张 GTX 980Ti 在分数上没有任何区别，看列表根本挑不出哪个是
「被否决但很可惜」的好卡。

这里只做客观换算，不调 AI、不读任务配置。口径分三层：

1. **档位**（perf_index）：以 GTX 1060 6G = 100 为基准的相对游戏性能，
   同型号不同显存（如 1060 3G / 5G / 6G）按实测差异区分。
2. **显存**：本地跑 AI 绘图直接吃显存，6G 是及格线，8G 舒适，12G+ 才谈得上宽裕。
3. **世代**：架构越新，驱动支持越久、能效越好，也更不容易是矿卡重灾区。

三者加权合成最终分。型号不在表里就返回 ``None``，宁可不给分也不要瞎猜——
上层会把这一维剔除并重新分配权重，而不是塞一个假的中位数进去。
"""
from __future__ import annotations

from dataclasses import dataclass

# 相对性能基准：GTX 1060 6G = 100（当年最普及的 1080p 游戏卡，做基准最好理解）
_PERF_INDEX: dict[str, float] = {
    # --- NVIDIA Maxwell ---
    "710": 8, "730": 12, "740": 18, "750": 25, "750ti": 32,
    "760": 35, "770": 42, "780": 50, "780ti": 58,
    "950": 45, "960": 50, "970": 68, "980": 78, "980ti": 92,
    # --- NVIDIA Pascal ---
    "1030": 22, "1050": 45, "1050ti": 52,
    "1060": 100,  # 默认按 6G 版；3G/5G 在 _vram_adjusted_index 里下调
    "1070": 115, "1070ti": 128, "1080": 140, "1080ti": 165,
    # --- NVIDIA Turing ---
    "1630": 55, "1650": 80, "1650super": 105,
    "1660": 110, "1660super": 120, "1660ti": 125,
    "2060": 145, "2060super": 155, "2070": 165, "2070super": 175,
    "2080": 185, "2080super": 195, "2080ti": 215,
    # --- NVIDIA Ampere / Ada / Blackwell ---
    "3050": 130, "3060": 165, "3060ti": 190, "3070": 205,
    "3080": 235, "3090": 260,
    "4060": 200, "4060ti": 220, "4070": 245, "4080": 290, "4090": 340,
    "5090": 400,
    # --- AMD Polaris ---
    "460": 38, "470": 60, "480": 68, "550": 32, "560": 40,
    "570": 65, "580": 72, "590": 80,
    # --- AMD Vega ---
    "vega56": 130, "vega64": 145,
    # --- AMD RDNA1 ---
    "5500": 90, "5600": 125, "5700": 145, "5700xt": 152,
    # --- AMD RDNA2 / RDNA3 ---
    "6400": 75, "6500": 95, "6600": 150, "6600xt": 165, "6650": 175,
    "6700": 185, "6750": 195, "6800": 220, "6800xt": 240, "6900": 255, "6950": 270,
    "7600": 190, "7700": 215, "7800": 240, "7900": 280,
    # --- Intel Arc ---
    "a380": 55, "a750": 105, "a770": 115,
    # --- 专业卡（通常已被硬门槛否决，给分只为呈现「否决得可不可惜」）---
    "p620": 25, "p1000": 45, "p2000": 60, "p4000": 110, "p5000": 140, "p6000": 175,
    "k2200": 40, "k4200": 45, "k5000": 55, "k6000": 65,
    "m4000": 50, "m5000": 60,
    "t400": 55, "t600": 65, "t1000": 85, "t2000": 100,
    "k80": 70, "p40": 110, "p100": 130, "v100": 160,
}

# 世代分：架构新旧（关系到驱动支持年限、能效、以及是否属于矿卡重灾区）
_GENERATION_SCORE: dict[str, int] = {
    "maxwell": 30,
    "pascal": 50,
    "turing": 62,
    "ampere": 80,
    "ada": 95,
    "blackwell": 100,
    "polaris": 35,
    "vega": 42,
    "rdna1": 60,
    "rdna2": 80,
    "rdna3": 95,
    "arc": 65,
    "professional_old": 35,
    "professional_new": 70,
}

# 显存分：本地 AI 绘图对显存敏感，6G 及格 / 8G 舒适 / 12G+ 宽裕
_VRAM_SCORE: dict[int, int] = {
    2: 12, 3: 20, 4: 32, 5: 40, 6: 62, 7: 70,
    8: 80, 10: 85, 11: 88, 12: 93, 16: 97, 20: 99, 24: 100,
}

# 三层的权重。
#
# 档位必须是绝对主导（0.70）：实测 0.55/0.30/0.15 时 RTX 3060 12G（95）
# 会反超 RTX 3080 10G（92）——因为 3080 显存更小，而显存权重给得太高。
# 这是荒谬的：3080 打游戏比 3060 强近一倍。显存只在「同一性能档」内做区分，
# 不能跨档位翻盘。所以档位 0.70、显存 0.20、世代 0.10。
_W_INDEX = 0.70
_W_VRAM = 0.20
_W_GEN = 0.10


@dataclass(frozen=True)
class GpuPerf:
    """显卡性能评估结果。"""

    score: int
    perf_index: float
    generation: str
    vram_gb: int | None

    def label(self) -> str:
        """一句话说明，给详情页用。"""
        parts = [f"性能指数 {self.perf_index:g}（1060 6G=100）"]
        if self.vram_gb:
            parts.append(f"{self.vram_gb}G 显存")
        gen_cn = _GENERATION_CN.get(self.generation, self.generation)
        if gen_cn:
            parts.append(gen_cn)
        return "，".join(parts)

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "perf_index": self.perf_index,
            "generation": self.generation,
            "vram_gb": self.vram_gb,
            "label": self.label(),
        }


_GENERATION_CN = {
    "maxwell": "Maxwell 架构",
    "pascal": "Pascal 架构",
    "turing": "Turing 架构",
    "ampere": "Ampere 架构",
    "ada": "Ada 架构",
    "blackwell": "Blackwell 架构",
    "polaris": "Polaris 架构",
    "vega": "Vega 架构",
    "rdna1": "RDNA1 架构",
    "rdna2": "RDNA2 架构",
    "rdna3": "RDNA3 架构",
    "arc": "Arc 架构",
    "professional_old": "老专业卡",
    "professional_new": "新专业卡",
    "unknown": "未知架构",
}


def _generation_of(model: str, raw_text: str) -> str:
    """从型号族 + 原文判断世代。原文用于消歧（如 750 可能是 GTX 750 或 Arc A750）。"""
    m = model.lower()
    raw = raw_text.lower()

    # Intel Arc：『a750』『arc a770』，避免和 GTX 750 / GTX 770 混淆
    if m.startswith("a") and m[1:].isdigit():
        return "arc"
    if "arc" in raw and m in {"380", "750", "770"}:
        return "arc"

    if not m:
        return "unknown"
    if m.startswith(("p", "k", "m", "t")) and m[1:].isdigit():
        # 专业卡：T 系列 / P 系列较新，K/M 较老
        letter = m[0]
        if letter == "t" or (letter != "k" and letter != "m" and m.startswith("p") and int(m[1:]) >= 2000):
            return "professional_new"
        return "professional_old"

    if m.startswith("vega"):
        return "vega"

    digits = "".join(ch for ch in m if ch.isdigit())
    if not digits:
        return "unknown"
    number = int(digits[:4] if len(digits) >= 4 else digits)

    # NVIDIA
    if number in {710, 730, 740, 750, 760, 770, 780}:
        return "maxwell"
    if 900 <= number <= 990:
        return "maxwell"
    if 1000 <= number <= 1090:
        return "pascal"
    if 1600 <= number <= 1670:
        return "turing"
    if 2000 <= number <= 2090:
        return "turing"
    if 3000 <= number <= 3090:
        return "ampere"
    if 4000 <= number <= 4090:
        return "ada"
    # AMD 必须先于 NVIDIA 的 5000 段判断：RX 5700 是 RDNA1，
    # 不是 RTX 5090。靠型号是否带『xt』和数字段位区分。
    if 5500 <= number <= 5790 or m in {"5700", "5700xt"}:
        return "rdna1"
    if 6300 <= number <= 6990:
        return "rdna2"
    if 7300 <= number <= 7990:
        return "rdna3"
    # Blackwell 目前只有 5090，单独点名，避免误伤 AMD 5000 系
    if number == 5090:
        return "blackwell"
    # AMD 老型号最后兜底
    if 440 <= number <= 590:
        return "polaris"
    return "unknown"


def _vram_adjusted_index(model: str, base: float, vram_gb: int | None) -> float:
    """同型号不同显存版本的实际性能差异。

    GTX 1060 的 3G 版不只是显存少，核心也被砍过（少 128 个 CUDA），
    实测约是 6G 版的 75%；5G 版是网吧特供，约 88%。不区分就等于把
    最烂的 3G 版和最保值的 6G 版算成同一张卡。
    """
    if model == "1060" and vram_gb is not None:
        if vram_gb <= 3:
            return base * 0.75
        if vram_gb == 5:
            return base * 0.88
    if model == "960" and vram_gb is not None and vram_gb >= 4:
        return base * 1.10  # 4G 版位宽是 128bit，比 2G 版强一截
    return base


def estimate_gpu_perf(
    model_family: str,
    vram_gb: int | None = None,
    raw_text: str = "",
) -> GpuPerf | None:
    """估一张卡的性能分。型号不认识时返回 ``None``（不猜）。"""
    model = str(model_family or "").strip().lower()
    if not model:
        return None

    base = _PERF_INDEX.get(model)
    if base is None:
        # 允许「1660s」这类简写折算到 1660super
        alias = {"1660s": "1660super", "1650s": "1650super", "1080t": "1080ti",
                 "980t": "980ti", "2060s": "2060super", "2070s": "2070super",
                 "2080s": "2080super", "3060t": "3060ti", "4060t": "4060ti",
                 "5700x": "5700xt", "6600x": "6600xt", "6800x": "6800xt"}
        base = _PERF_INDEX.get(alias.get(model, ""))
    if base is None:
        return None

    index = _vram_adjusted_index(model, float(base), vram_gb)
    generation = _generation_of(model, raw_text)

    # 档位分不用线性缩放。线性会让 index≥172 的卡全部撞上 100 的天花板，
    # 于是 RTX 3060(165→95.7)、3080(235→100)、4090(340→100) 挤成一团。
    # 改用开方压缩：低端拉开差距，高端平滑收敛，且不需要调天花板。
    #   1060 6G (100) → 66.6     3060 (165) → 85.6
    #   3080 (235)    → 100      4090 (340) → 100（靠显存/世代再区分）
    index_score = min(100.0, (index ** 0.72) * 2.15)
    vram_score = _VRAM_SCORE.get(vram_gb, 40 if vram_gb is None else 45)
    gen_score = _GENERATION_SCORE.get(generation, 45)

    composite = index_score * _W_INDEX + vram_score * _W_VRAM + gen_score * _W_GEN
    return GpuPerf(
        score=max(0, min(100, round(composite))),
        perf_index=round(index, 1),
        generation=generation,
        vram_gb=vram_gb,
    )
