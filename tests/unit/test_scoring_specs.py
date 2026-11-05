from src.domain.scoring.specs import extract_specs

P620_TITLE = (
    "NVIDIA Quadro P620专业显卡，2G显存，4个 miniDP接口，半高设计，低功耗，"
    "无需独立供电，可用于多屏炒股，同时也是最佳亮机卡。成色还可以点使用痕迹，"
    "PCB板完整，金手指无氧化，无拆无修，风扇正常，插上即用，功能稳定～包邮。"
)


def test_extract_professional_card():
    specs = extract_specs(P620_TITLE)
    assert specs.model_family == "p620"
    assert specs.vram_gb == 2
    assert specs.card_class == "professional"
    assert specs.is_gpu is True
    # 「无拆无修」不能被误判成维修史
    assert specs.repair_signals == ()


def test_extract_consumer_card_with_brand_prefix():
    specs = extract_specs("索泰GTX1070 8G X-Gaming OC显卡，个人主机拆机自用")
    assert specs.model_family == "1070"
    assert specs.vram_gb == 8
    assert specs.card_class == "consumer"


def test_extract_card_without_vendor_prefix():
    # 闲鱼上大量标题省略 GTX 前缀，必须能识别
    specs = extract_specs("影驰1060 6G显卡，双风扇散热，功能一切正常，包邮")
    assert specs.model_family == "1060"
    assert specs.vram_gb == 6


def test_extract_suffix_family():
    specs = extract_specs("GTX 1660 Ti 6G 猛禽 显卡 无拆无修 包邮")
    assert specs.model_family == "1660ti"
    assert specs.vram_gb == 6


def test_negated_mining_is_not_mining():
    specs = extract_specs("影驰1060 6G显卡，非矿卡，自用，包邮")
    assert specs.mining_signals == ()
    assert specs.card_class == "consumer"


def test_joking_mining_phrase_is_not_mining():
    # 「矿卡白送」是卖家的反话，不是矿卡
    specs = extract_specs("微星GTX1070红龙，自用，矿卡白送！！！", gpu_hint=True)
    assert specs.mining_signals == ()


def test_negated_repair_is_not_repair():
    specs = extract_specs("华硕猛禽 vega56 显卡，拆开换过硅脂，没有修过，包邮", gpu_hint=True)
    assert specs.repair_signals == ()


def test_real_repair_is_detected():
    specs = extract_specs("华硕TUF GTX1660S 显卡，之前温度异常，返厂维修过，包邮", gpu_hint=True)
    assert specs.repair_signals == ("维修过",)


def test_negated_defect_is_ignored():
    specs = extract_specs("自用索泰GTX1650 4G，无拆无修，无花屏，包邮", gpu_hint=True)
    assert specs.defects == ()


def test_mining_keyword_is_detected():
    specs = extract_specs("RX580 8G 显卡，矿卡退役，包邮")
    assert specs.card_class == "mining"
    assert "矿卡" in specs.mining_signals


def test_defect_and_pickup_detection():
    specs = extract_specs("七彩虹1060 3G显卡，装驱动后黑屏点不亮，仅限同城自提")
    assert "黑屏" in specs.defects
    assert "点不亮" in specs.defects
    assert specs.pickup_only is True
    assert specs.ships is False


def test_pickup_is_ignored_when_shipping_is_offered():
    specs = extract_specs("GTX1070 8G 显卡，可自提也可包邮")
    assert specs.pickup_only is False


def test_non_gpu_title_has_no_model_family():
    specs = extract_specs("真我GT8Pro 16+512 全新未拆封 包邮")
    assert specs.model_family == ""
    assert specs.is_gpu is False
    # 手机内存不能当成显存
    assert specs.vram_gb is None


def test_price_like_number_is_not_treated_as_model():
    specs = extract_specs("华硕 ROG STRIX RTX 3080 O10G 显卡，1650元出")
    assert specs.model_family == "3080"
    assert specs.vram_gb == 10


def test_gpu_hint_recovers_model_without_any_gpu_keyword():
    # 任务本身是显卡任务时，标题里不写「显卡」也要能认出型号
    specs = extract_specs("索泰1660super 毁灭者6G，自提750", gpu_hint=True)
    assert specs.model_family == "1660super"
    assert specs.vram_gb == 6


def test_gpu_hint_accepts_three_digit_radeon_model():
    specs = extract_specs("580显卡8g，有2个", gpu_hint=True)
    assert specs.model_family == "580"
    assert specs.vram_gb == 8


def test_unknown_number_is_not_a_model_even_with_gpu_hint():
    specs = extract_specs("121f00➕h610 666包邮非偏远", gpu_hint=True)
    assert specs.model_family == ""


def test_bare_number_followed_by_price_word_is_ignored():
    specs = extract_specs("闲置显卡，580元出，包邮", gpu_hint=True)
    assert specs.model_family == ""
