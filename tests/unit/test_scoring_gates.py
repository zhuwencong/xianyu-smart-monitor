from src.domain.scoring.gates import evaluate_gates, task_allows_professional
from src.domain.scoring.specs import extract_specs

P620_TITLE = (
    "NVIDIA Quadro P620专业显卡，2G显存，4个 miniDP接口，半高设计，低功耗，"
    "无需独立供电，可用于多屏炒股，同时也是最佳亮机卡。包邮。"
)


def _gates(title: str, **kwargs):
    return evaluate_gates(specs=extract_specs(title), **kwargs)


def test_professional_card_is_blocked_in_consumer_task():
    result = _gates(P620_TITLE, price=208.0, budget_max="1000")
    assert result.blocked is True
    assert [hit.key for hit in result.blocks] == ["professional_card"]


def test_professional_card_allowed_when_task_targets_it():
    result = _gates(P620_TITLE, price=208.0, allow_professional=True)
    assert result.blocked is False


def test_low_vram_consumer_card_is_blocked():
    result = _gates("华硕 GTX1050 2G 显卡，包邮", price=300.0)
    assert result.blocked is True
    assert "vram" in [hit.key for hit in result.blocks]


def test_sufficient_vram_consumer_card_passes():
    result = _gates("影驰GTX1070 8G显卡，包邮，功能正常", price=700.0, budget_max="1000")
    assert result.blocked is False


def test_defect_blocks_recommendation():
    result = _gates("GTX1070 8G 显卡，装驱动黑屏点不亮，包邮")
    assert result.blocked is True
    assert "defect" in [hit.key for hit in result.blocks]


def test_over_budget_blocks():
    result = _gates("RTX 3060 12G 显卡，包邮", price=1800.0, budget_max="1000")
    assert result.blocked is True
    assert "budget" in [hit.key for hit in result.blocks]


def test_pickup_only_blocks_when_task_requires_shipping():
    blocked = _gates("GTX1070 8G 显卡，仅限同城自提", price=700.0, require_shipping=True)
    assert blocked.blocked is True
    relaxed = _gates("GTX1070 8G 显卡，仅限同城自提", price=700.0, require_shipping=False)
    assert relaxed.blocked is False


def test_bad_seller_credit_blocks():
    result = _gates(
        "GTX1070 8G 显卡，包邮",
        price=700.0,
        seller_credit="卖家信用较差",
    )
    assert result.blocked is True
    assert "seller_credit" in [hit.key for hit in result.blocks]


def test_warnings_do_not_block():
    result = _gates("GTX1070 8G 显卡", price=700.0)
    assert result.blocked is False
    assert "shipping_unknown" in [hit.key for hit in result.warnings]


def test_task_allows_professional_detection():
    assert task_allows_professional("quadro p620 专业卡") is True
    assert task_allows_professional("显卡") is False
    assert task_allows_professional("GTX1070 8G") is False
