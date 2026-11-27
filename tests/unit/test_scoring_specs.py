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


# --- 非显卡品类（路由器等）的功能故障识别 ---
# 背景：故障词表原先是显卡专用的，路由器「自动断联」识别不到，
# 导致一台明确故障的机器拿到 81 分 deal_score +「高性价比」标签。

def test_router_auto_disconnect_detected_as_defect():
    """路由器「自动断联」必须识别为功能故障。"""
    specs = extract_specs(
        "小米路由器BE3600 2.5G版，WiFi7，四天线，3600M速率，2.5G网口。"
        "有拆卸痕迹，不影响使用。绑定米家几分钟后自动断联。"
        "无线mesh组网几十分钟后自动断联。其他功能正常。包邮。"
    )
    assert "自动断联" in specs.defects
    assert "拆卸痕迹" in specs.defects
    assert specs.has_blocking_defect is True


def test_normal_router_not_flagged_as_defect():
    """正常路由器不能被误伤。"""
    for text in (
        "小米AX3000T，WiFi6，四天线，功能正常，没拆没修，插电即用，带原装电源，包邮。",
        "出准新小米路由器BE3600 2.5G版，WiFi7，信号强穿墙好，支持mesh组网，功能正常。",
        # 「定时重启」是功能而非故障
        "小米AX3000T，支持定时重启功能，米家App管理，夜间自动重启不打扰。",
        # 「移动联通电信都能用」不是锁网
        "路由器支持Mesh组网，移动联通电信都能用，信号覆盖全屋。",
    ):
        assert extract_specs(text).defects == (), f"误判为故障: {text}"


# --- 故障机的价格标签必须被覆盖 ---

def test_defect_guard_blocks_bargain_label():
    """明确故障的机器，价格标签不能是「高性价比」。"""
    from src.services.price_history_service import _apply_defect_guard

    label, note = _apply_defect_guard(
        "高性价比",
        title="小米路由器BE3600 2.5G版 WiFi7",
        description="有拆卸痕迹。绑定米家几分钟后自动断联。其他功能正常。包邮。",
    )

    assert label == "故障机·勿买"
    assert "不建议购买" in note
    assert "自动断联" in note


def test_defect_guard_keeps_label_for_healthy_item():
    """健康商品的标签原样保留。"""
    from src.services.price_history_service import _apply_defect_guard

    label, note = _apply_defect_guard(
        "高性价比",
        title="小米AX3000T WiFi6",
        description="功能正常，没拆没修，插电即用，包邮。",
    )

    assert label == "高性价比"
    assert note == ""


# --- 故障机的价格分必须一起压下来 ---
# 只覆盖标签是不够的：分数会进 CSV 导出，任何按分数浏览的路径
# 都可能让一台坏机器凭 81 分冲上榜首。

def _build_defect_price_context():
    """构造一台「比市场便宜但明确故障」的机器，返回其 price_context。"""
    from src.services.price_history_service import build_item_price_context

    defective_title = (
        "小米路由器BE3600 2.5G版，WiFi7，四天线，3600M速率，2.5G网口。"
        "有拆卸痕迹，不影响使用。绑定米家几分钟后自动断联。其他功能正常。包邮。"
    )
    # 3 台健康同型号机器挂 300，这台只卖 85 —— 纯价格算必然是高分。
    market = [
        {"item_id": "a", "title": "小米路由器BE3600 2.5G版 WiFi7", "price": 300, "run_id": "r1"},
        {"item_id": "b", "title": "小米路由器BE3600 2.5G版 WiFi7", "price": 305, "run_id": "r1"},
        {"item_id": "c", "title": "小米路由器BE3600 2.5G版 WiFi7", "price": 310, "run_id": "r1"},
    ]
    snapshots = market + [
        {
            "item_id": "bad",
            "title": defective_title,
            "description": "有拆卸痕迹。绑定米家几分钟后自动断联。其他功能正常。包邮。",
            "price": 85,
            "run_id": "r1",
        }
    ]
    return build_item_price_context(
        snapshots,
        item_id="bad",
        current_price=85,
        market_snapshots=market,
        title=defective_title,
    )


def test_defect_item_price_score_is_capped():
    """故障机的 deal_score 必须被压到上限以内，不能凭低价拿高分。"""
    from src.services.price_history_service import DEFECT_SCORE_CAP

    context = _build_defect_price_context()

    assert context["deal_label"] == "故障机·勿买"
    assert context["deal_score"] <= DEFECT_SCORE_CAP, (
        f"故障机 deal_score={context['deal_score']} 仍超过上限 {DEFECT_SCORE_CAP}"
    )
    assert "自动断联" in context["deal_defect_note"]


def test_healthy_item_price_score_not_capped():
    """同样便宜的机器，只要没故障，分数照常给高。"""
    from src.services.price_history_service import DEFECT_SCORE_CAP, build_item_price_context

    healthy_title = "小米路由器BE3600 2.5G版 WiFi7，功能正常，没拆没修，包邮。"
    market = [
        {"item_id": "a", "title": healthy_title, "price": 300, "run_id": "r1"},
        {"item_id": "b", "title": healthy_title, "price": 305, "run_id": "r1"},
        {"item_id": "c", "title": healthy_title, "price": 310, "run_id": "r1"},
    ]
    snapshots = market + [
        {"item_id": "ok", "title": healthy_title, "description": "功能正常，没拆没修。",
         "price": 85, "run_id": "r1"}
    ]

    context = build_item_price_context(
        snapshots,
        item_id="ok",
        current_price=85,
        market_snapshots=market,
        title=healthy_title,
    )

    assert context["deal_defect_note"] == ""
    assert context["deal_score"] > DEFECT_SCORE_CAP, "健康机器不应被故障上限误伤"
