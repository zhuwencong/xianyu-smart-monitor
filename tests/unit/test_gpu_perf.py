"""显卡性能维度测试。

核心不变量：性能分的排序必须符合常识。一旦有人调权重把 RTX 3060 排到
RTX 3080 前面，这里必须立刻炸出来。
"""
import pytest

from src.domain.scoring.gpu_perf import estimate_gpu_perf


def _score(model: str, vram=8, raw="") -> int:
    result = estimate_gpu_perf(model, vram, raw)
    assert result is not None, f"{model} 应该能识别"
    return result.score


class TestPerfOrdering:
    """跨档位的性能顺序不能反。"""

    @pytest.mark.parametrize(
        "stronger,weaker",
        [
            ("4090", "3080"),
            ("3080", "3060"),
            ("3060", "2060"),
            ("2060", "1060"),
            ("1060", "1050ti"),
            ("1050ti", "1030"),
            ("1080ti", "980ti"),
            ("5700xt", "580"),
            ("6600", "570"),
        ],
    )
    def test_higher_tier_wins(self, stronger, weaker):
        assert _score(stronger) > _score(weaker), f"{stronger} 应强于 {weaker}"

    def test_3080_beats_3060_despite_less_vram(self):
        """3080 只有 10G、3060 有 12G，但 3080 实际强近一倍。

        这是权重失衡最容易踩的坑：显存权重一高，3060 就会反超。
        """
        assert _score("3080", 10) > _score("3060", 12)


class TestVramVariants:
    """同型号不同显存的真实差异必须体现。"""

    def test_1060_6g_beats_3g(self):
        """3G 版核心也被砍过（少 128 CUDA），不能和 6G 版同分。"""
        assert _score("1060", 6) > _score("1060", 3)

    def test_1060_6g_beats_5g(self):
        assert _score("1060", 6) > _score("1060", 5)

    def test_3060_12g_beats_6g(self):
        assert _score("3060", 12) > _score("3060", 6)


class TestGenerationDetection:
    """世代判断不能把 AMD 的 RX 5700 认成 RTX 5090。"""

    @pytest.mark.parametrize(
        "model,raw,expected",
        [
            ("5700xt", "rx5700xt", "rdna1"),
            ("5700", "rx5700", "rdna1"),
            ("580", "rx580", "polaris"),
            ("1060", "gtx1060", "pascal"),
            ("3060", "rtx3060", "ampere"),
            ("4090", "rtx4090", "ada"),
            ("1660", "gtx1660", "turing"),
            ("a770", "arc a770", "arc"),
            ("p1000", "quadro p1000", "professional_old"),
        ],
    )
    def test_generation(self, model, raw, expected):
        result = estimate_gpu_perf(model, 8, raw)
        assert result is not None
        assert result.generation == expected


class TestUnknownModel:
    """认不出来就不给分，绝不瞎猜。"""

    def test_empty_model_returns_none(self):
        assert estimate_gpu_perf("", 8, "") is None

    def test_unrecognized_model_returns_none(self):
        assert estimate_gpu_perf("9999", 8, "神秘显卡") is None

    def test_score_within_bounds(self):
        for model in ("4090", "1060", "1030", "580", "k80"):
            score = _score(model)
            assert 0 <= score <= 100
