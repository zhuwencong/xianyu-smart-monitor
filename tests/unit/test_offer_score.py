"""绝对分模型（6 维 100 分 + 辅助加减分 + 一票否决）的行为约束。

这些用例锁的是**容易退化的地方**，不是复述需求表：

1. 缺项按 0 计，绝不「剔除后重标定」——否则缺价格分的商品能算出 100 分。
2. 两把价格尺子必须各自独立：二手行情防骗，相对全新防买亏。
   它们会给出相反结论，混成一个数就再也拆不开。
3. 站外引流要能识别，但「微信支付」「扫码支付」是平台内支付，不能误杀。
4. 硬门槛（矿卡/故障）必须并入否决，否则矿卡能拿高分显示「直接冲」。
5. 否决时总分照算，grade 强制 skip —— 两者不能混成一个 0 分。
6. 电池循环、评论区这类**平台根本不提供**的字段，必须是「不可判」，
   绝不当成 0 分扣——那等于惩罚所有卖家。
"""
from datetime import datetime, timedelta

from src.domain.scoring.offer_score import (
    DIMENSION_ORDER,
    GRADE_NEGOTIATE,
    TOO_CHEAP_RATIO,
    WEIGHTS,
    OfferFacts,
    count_sold,
    parse_storage,
    registered_months,
    score_offer,
    storage_matches,
)

NOW = datetime(2026, 11, 28, 12, 0)


def _facts(**kwargs) -> OfferFacts:
    """构造一条「各项都说得过去」的基准商品，用例只改需要变的那几项。"""
    base = dict(
        listing_id="1",
        price=1000.0,
        market_median=1200.0,
        market_scope="model",
        market_samples=8,
        published_at=NOW - timedelta(minutes=20),
        reference_at=NOW,
        image_count=4,
        title="OPPO Find X9 Pro 16+512 自用",
        description="自用一代，序列号可查，电池健康 92%，支持验货宝，同城可面交。" + "详" * 60,
        tags=("验货宝",),
        seller_credit="信用极好",
        sold_count=6,
        registered_months=40,
        # 全新价锚点：¥1200 的锚点意味着二手 ¥1000 = 全新生 83%，落在「不如买新」档。
        # 用例按需覆写，默认有这个值是为了让「满分场景」真的能拿满分。
        new_price_anchor=1000.0,
        battery_cycles=200,
        warranty_months=6,
        storage_matches=True,
    )
    base.update(kwargs)
    return OfferFacts(**base)


def _dim(result, key):
    return next(d for d in result["dimensions"] if d["key"] == key)


def _veto_keys(result):
    return [flag["key"] for flag in result["veto_flags"]]


# ---------------------------------------------------------------------------
# 权重与结构
# ---------------------------------------------------------------------------


def test_weights_sum_to_one_hundred():
    assert sum(WEIGHTS.values()) == 100
    assert WEIGHTS == {
        "price_market": 30,
        "value_vs_new": 25,
        "seller": 15,
        "authenticity": 15,
        "device_health": 10,
        "safety": 5,
    }


def test_every_dimension_can_reach_its_full_weight():
    """每个维度的分项之和必须**正好等于**权重，一分不多一分不少。

    这条不变量是这次发现「卖家维度 16/15」的方式：权重从 20 改成 15 时，
    维度内的分项分值表忘了同步缩放，结果一条满分商品的进度条画成 16/15。
    单看分数「16 分挺高」不会觉得有问题，只有专门核对才抓得住。
    """
    perfect = score_offer(
        _facts(
            price=950.0,
            # 950/1900 = 0.50，落在「真漏」档（<0.65）才拿得到 25 分
            new_price_anchor=1900.0,
            seller_credit="信用极好",
            sold_count=10,
            registered_months=48,
            image_count=6,
            warranty_months=8,
            battery_cycles=100,
            storage_matches=True,
        )
    )
    for dim in perfect["dimensions"]:
        assert dim["value"] <= dim["max"], f"{dim['label']} 超出满分：{dim['value']}/{dim['max']}"
    assert perfect["total"] <= 100
    # 六个维度都拿到分时，理论上限就是 100
    assert perfect["scored_max"] == 100
    # 满分场景下每一维都应该顶格（分项表与权重脱节时这里会失败）
    for dim in perfect["dimensions"]:
        assert dim["value"] == dim["max"], f"{dim['label']} 拿不到满分：{dim['value']}/{dim['max']}，{dim['reason']}"


def test_dimensions_are_emitted_in_display_order():
    """UI 按返回顺序画进度条，顺序必须稳定且与 DIMENSION_ORDER 一致。"""
    result = score_offer(_facts())
    assert [d["key"] for d in result["dimensions"]] == list(DIMENSION_ORDER)


def test_price_and_value_are_separate_dimensions():
    """「价格分（防骗）」与「性价比分（防买亏）」必须是两个独立分数。

    这是本轮需求的核心：一台机器可以「在二手市场里偏低」但「比全新只便宜一点」，
    两个结论必须能同时呈现在 UI 上，不能被合成一个数字。
    """
    result = score_offer(_facts(price=950.0, market_median=1200.0, new_price_anchor=2549.0))
    assert _dim(result, "price_market")["value"] is not None
    assert _dim(result, "value_vs_new")["value"] is not None
    # 二手行情 -21%（高分），但相对全新只是 37%、省 63%（这档也是高分，换个例子）
    # 关键是两者数值**不必相等**，证明是两个独立计算
    assert result["price_ratio"] is not None
    assert result["ratio_used_vs_new"] is not None


def test_perfect_offer_reaches_buy_grade():
    result = score_offer(_facts(price=950.0))
    assert result["total"] is not None and result["total"] >= 80
    assert result["grade"] == "buy"
    assert result["vetoed"] is False


# ---------------------------------------------------------------------------
# 性价比分：相对「当前全新最低价」
# ---------------------------------------------------------------------------


def test_value_vs_new_tiers():
    """≥0.85 → 5 / 0.75–0.85 → 10 / 0.65–0.75 → 18 / <0.65 → 25。"""
    anchor = 2549.0
    assert _dim(score_offer(_facts(price=2400.0, new_price_anchor=anchor)), "value_vs_new")["value"] == 5
    assert _dim(score_offer(_facts(price=2549.0 * 0.86, new_price_anchor=anchor)), "value_vs_new")["value"] == 5
    assert _dim(score_offer(_facts(price=2549.0 * 0.82, new_price_anchor=anchor)), "value_vs_new")["value"] == 10
    assert _dim(score_offer(_facts(price=2549.0 * 0.70, new_price_anchor=anchor)), "value_vs_new")["value"] == 18
    assert _dim(score_offer(_facts(price=2549.0 * 0.60, new_price_anchor=anchor)), "value_vs_new")["value"] == 25


def test_value_vs_new_is_monotonic_in_discount():
    """相对全新越便宜分越高，允许同分，绝不允许倒挂。"""
    scores = [
        _dim(score_offer(_facts(price=2549.0 * ratio, new_price_anchor=2549.0)), "value_vs_new")["value"]
        for ratio in (1.0, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.55)
    ]
    assert scores == sorted(scores), f"性价比档位出现倒挂: {scores}"


def test_missing_anchor_makes_value_unknown_not_zero():
    """没配锚点时必须「不可判」，不是 0 分。

    0 分会把「任务没配置」错误地表达成「这台机器性价比差」，
    而事实是这一项根本没算——UI 与话术都要能区分这两件事。
    """
    result = score_offer(_facts(new_price_anchor=None))
    dim = _dim(result, "value_vs_new")
    assert dim["value"] is None
    assert dim["scored"] is False
    assert result["value_judged"] is False
    assert result["ratio_used_vs_new"] is None
    keys = [item["key"] for item in result["missing_items"]]
    assert "new_price_anchor" in keys


def test_missing_anchor_caps_grade_at_negotiate():
    """缺 25 分锚点时理论最高只有 75 分，绝不可能「直接冲」。"""
    result = score_offer(_facts(price=950.0, new_price_anchor=None))
    assert result["total"] <= 75, f"缺性价比分却算出 {result['total']}"
    assert result["grade"] != "buy"
    assert "锚点" in result["grade_note"]


def test_anchor_missing_item_has_no_ask_script():
    """锚点属于任务配置问题，问卖家没用——不能编一句话术充数。"""
    result = score_offer(_facts(new_price_anchor=None))
    item = next(i for i in result["missing_items"] if i["key"] == "new_price_anchor")
    assert item["ask"] == ""
    assert item["internal"] is True


# ---------------------------------------------------------------------------
# 价格分：相对「同型号二手行情」
# ---------------------------------------------------------------------------


def test_missing_price_cannot_be_rescued_by_other_dimensions():
    """没有同型号行情时不能拿满其他维度就冲上 100。

    这是最容易犯的错：用 earned/possible 重标定，缺 30 分权重的价格维度
    会让其余维度满分直接等于 100 分「直接冲」——而那台恰恰没比价成功。
    """
    result = score_offer(
        _facts(market_median=None, market_scope="insufficient", market_samples=0)
    )
    assert _dim(result, "price_market")["value"] is None
    assert _dim(result, "price_market")["scored"] is False
    assert result["scored_max"] == 70, "缺 30 分价格维度时有效满分应为 70"
    assert result["total"] <= 70, f"缺价格分却算出 {result['total']}，说明做了重标定"
    assert result["grade"] != "buy", "价格不可判却给了「直接冲」"


def test_price_tiers_follow_the_spec():
    """高于行情 0 / 行情内 5 / 低 5% 15 / 低 5~15% 25 / 跌破捡漏线 30。"""
    assert _dim(score_offer(_facts(price=1300.0)), "price_market")["value"] == 0  # +8%
    assert _dim(score_offer(_facts(price=1200.0)), "price_market")["value"] == 5  # 等于行情
    assert _dim(score_offer(_facts(price=1140.0)), "price_market")["value"] == 15  # -5.0%
    assert _dim(score_offer(_facts(price=1080.0)), "price_market")["value"] == 25  # -10.0%
    assert _dim(score_offer(_facts(price=990.0)), "price_market")["value"] == 30  # -17.5% 已跌破捡漏线


def test_price_score_is_monotonic_in_discount():
    """优惠越深分越高，允许同分，绝不允许倒挂。"""
    scores = [
        _dim(score_offer(_facts(price=1200.0 * ratio)), "price_market")["value"]
        for ratio in (1.1, 1.0, 0.97, 0.95, 0.90, 0.85, 0.80, 0.72)
    ]
    assert scores == sorted(scores), f"价格档位出现倒挂: {scores}"


def test_absurdly_cheap_triggers_price_veto():
    """低于行情 30% 以上：0 分 + 否决，不是「超级捡漏」。"""
    result = score_offer(_facts(price=1200.0 * (TOO_CHEAP_RATIO - 0.05)))
    assert _dim(result, "price_market")["value"] == 0
    assert "too_cheap" in _veto_keys(result)
    assert result["grade"] == "skip"
    assert result["vetoed"] is True


# ---------------------------------------------------------------------------
# 机型健康分：保修 / 电池 / 版本
# ---------------------------------------------------------------------------


def test_device_health_rewards_in_warranty():
    in_warranty = score_offer(_facts(warranty_months=8))
    out = score_offer(_facts(warranty_months=-1))
    assert _dim(in_warranty, "device_health")["value"] > _dim(out, "device_health")["value"]
    assert _dim(out, "device_health")["value"] is not None


def test_device_health_warranty_inferred_from_text():
    """没有结构化月数时，描述里写「在保」/「过保」也能判，且标为推定。

    基准事实里电池 200 次（4 分）、配置一致（2 分），所以在保 = 4+4+2 = 10，
    过保 = 0+4+2 = 6，两者差 4 分正好是保修项的权重。
    """
    in_warranty = _dim(score_offer(_facts(warranty_months=None, description="还在保，官方保修到明年" + "详" * 60)), "device_health")
    expired = _dim(score_offer(_facts(warranty_months=None, description="已过保，无保修" + "详" * 60)), "device_health")
    assert in_warranty["value"] == 10
    assert expired["value"] == 6
    assert in_warranty["inferred"] is True


def test_battery_cycles_tiers():
    """≤300 → 4 / ≤800 → 2 / >800 → 0。"""
    assert _dim(score_offer(_facts(battery_cycles=120)), "device_health")["value"] == 10
    assert _dim(score_offer(_facts(battery_cycles=600)), "device_health")["value"] == 8
    assert _dim(score_offer(_facts(battery_cycles=900)), "device_health")["value"] == 6


def test_battery_cycles_parsed_from_description():
    """卖家在描述里写了循环次数，就不用再当未知。

    并且关键数字要出现在依据里——只说「电池0/4」看不出是 1200 次还是 900 次。
    """
    result = score_offer(_facts(battery_cycles=None, description="电池循环 1200 次，其他都正常" + "详" * 60))
    dim = _dim(result, "device_health")
    assert dim["value"] is not None
    assert "1200" in dim["reason"]


def test_missing_battery_cycles_is_unknown_not_penalty():
    """电池循环实测 1174 条里出现 0 次——平台不提供。

    把它当 0 分扣等于惩罚所有卖家，所以必须是「不可判 + 向卖家索取」。
    """
    result = score_offer(_facts(battery_cycles=None, description="成色很好" + "详" * 60))
    dim = _dim(result, "device_health")
    assert "未知" in dim["reason"]
    keys = [item["key"] for item in result["missing_items"]]
    assert "battery_cycles" in keys
    ask = next(i for i in result["missing_items"] if i["key"] == "battery_cycles")
    assert ask["ask"], "电池循环可以问卖家，必须给出话术"


def test_all_health_items_unverifiable_is_unknown():
    """保修、电池、配置三项都拿不到 → 整维不可判，不硬凑 0 分。"""
    result = score_offer(
        _facts(warranty_months=None, battery_cycles=None, storage_matches=None,
               description="便宜出，看图" + "详" * 60)
    )
    assert _dim(result, "device_health")["value"] is None


def test_storage_mismatch_costs_points():
    """描述容量与目标不符（疑似低配充高配）要比对得上少分。"""
    match = score_offer(_facts(storage_matches=True))
    mismatch = score_offer(_facts(storage_matches=False))
    assert _dim(mismatch, "device_health")["value"] < _dim(match, "device_health")["value"]


def test_parse_storage_ignores_price_sums():
    """`3000+200` 这种价格相加不能被当成 `16+512`。"""
    assert parse_storage("优惠 3000+200 到手", "") is None
    assert parse_storage("X9 Pro 16+512", "") == (16, 512)
    assert parse_storage("", "12+256g 国行") == (12, 256)
    assert parse_storage("1TB 版本", "") == (0, 1024)


def test_storage_matches_returns_none_when_cannot_tell():
    """卖家没写容量 / 任务没指定配置 → None（不可判），不是 False（风险）。"""
    assert storage_matches("好机器", "成色很好", "OPPO Find X9 Pro 16+512") is None
    assert storage_matches("X9 Pro 16+512", "", "") is None
    assert storage_matches("X9 Pro 16+512", "", "OPPO Find X9 Pro 16+512") is True
    assert storage_matches("X9 Pro 12+256", "", "OPPO Find X9 Pro 16+512") is False


# ---------------------------------------------------------------------------
# 卖家 / 真实 / 安全
# ---------------------------------------------------------------------------


def test_seller_credit_tiers():
    good = score_offer(_facts(seller_credit="信用极好", sold_count=10, registered_months=36))
    bad = score_offer(_facts(seller_credit="信用较差", sold_count=0, registered_months=3))
    assert _dim(good, "seller")["value"] > _dim(bad, "seller")["value"]
    assert _dim(bad, "seller")["value"] is not None


def test_missing_seller_data_is_not_zero():
    """卖家三项客观事实全缺时是「不可判」，不能被一句个人语气包装成可信。"""
    dim = _dim(
        score_offer(
            _facts(
                seller_credit="",
                sold_count=None,
                registered_months=None,
                title="自用 OPPO Find X9 Pro 16+512",
                description="自用一代，成色很好" + "详" * 60,
            )
        ),
        "seller",
    )
    assert dim["value"] is None, "客观事实全缺却给出了可信分"


def test_tone_alone_cannot_fill_seller_dimension():
    """只有个人语气不能顶满 15 分——这是维度内重标定的典型错误。"""
    result = score_offer(
        _facts(seller_credit="", sold_count=None, registered_months=None)
    )
    assert _dim(result, "seller")["value"] is None
    assert result["scored_max"] == 85  # 15 分卖家维度从分母中退出


def test_authenticity_needs_evidence():
    weak = score_offer(_facts(image_count=0, description="好", tags=()))
    strong = score_offer(_facts())
    assert _dim(strong, "authenticity")["value"] > _dim(weak, "authenticity")["value"]
    assert _dim(weak, "authenticity")["value"] == 0


# ---------------------------------------------------------------------------
# 一票否决
# ---------------------------------------------------------------------------


def test_offsite_contact_is_vetoed():
    result = score_offer(_facts(description="好机器，加微信详聊 vx1234"))
    assert "offsite" in _veto_keys(result)
    assert result["grade"] == "skip"


def test_wechat_pay_is_not_offsite():
    """「微信支付」「扫码支付」是平台内支付，绝不能当站外引流封杀。"""
    result = score_offer(
        _facts(description="支持微信支付，也可以用扫码支付，顺丰包邮。" + "详" * 60)
    )
    assert "offsite" not in _veto_keys(result), "把平台内支付误判成站外交易了"


def test_phone_number_with_wechat_is_vetoed():
    result = score_offer(_facts(description="同城可自取 13835983574微信"))
    assert "offsite" in _veto_keys(result)


def test_deposit_requirement_is_vetoed():
    result = score_offer(_facts(description="先付定金 200 留货，不验机"))
    assert "deposit" in _veto_keys(result)
    assert result["grade"] == "skip"


def test_normal_no_return_clause_is_not_a_veto():
    """「售出非质量问题不退不换」是二手常规免责，不该被判成不验机。"""
    result = score_offer(
        _facts(description="售出非质量问题不退不换，支持验货宝。" + "详" * 60)
    )
    assert "deposit" not in _veto_keys(result)


def test_hard_gate_blocks_override_high_score():
    """矿卡即使各维度都很漂亮，也必须被否决。"""
    result = score_offer(
        _facts(price=950.0),
        hard_blocks=(
            {"key": "mining", "label": "矿卡/矿机", "detail": "命中矿卡相关表述：挖矿", "source": "hard_gate"},
        ),
    )
    assert result["total"] >= 80, "总分仍应反映成色，供人判断「可惜不可惜」"
    assert result["grade"] == "skip"
    assert result["vetoed"] is True
    assert any(flag.get("source") == "hard_gate" for flag in result["veto_flags"])


# ---------------------------------------------------------------------------
# 辅助加减分
# ---------------------------------------------------------------------------


def test_fresh_listing_gets_positive_adjustment():
    fresh = score_offer(_facts(published_at=NOW - timedelta(minutes=10)))
    stale = score_offer(_facts(published_at=NOW - timedelta(days=8)))
    adj = {a["key"]: a for a in fresh["adjustments"]}
    assert adj["freshness"]["delta"] == 4
    assert {a["key"]: a for a in stale["adjustments"]}["freshness"]["delta"] == -4
    assert fresh["adjustment_total"] > stale["adjustment_total"]


def test_adjustment_total_matches_item_sum_after_clamp():
    """明细之和必须等于实际进总分的值，否则 UI 上加减分对不上账。"""
    # 同时命中：稀缺 +3、真实闲置 +3、刚上架 +4、已售 +2 = +12 → 封顶 +10
    result = score_offer(
        _facts(
            published_at=NOW - timedelta(minutes=5),
            sold_out=True,
            title="X9 Pro 16+512 限定色 顶配 1T",
            description="年会奖品用不上，闲置很久" + "详" * 60,
        )
    )
    deltas = sum(a["delta"] for a in result["adjustments"])
    assert deltas == result["adjustment_total"] == 10


def test_hustle_tone_costs_points():
    hustle = score_offer(_facts(description="秒发，仅需 999，手慢无" + "详" * 60))
    assert {a["key"]: a for a in hustle["adjustments"]}["hustle_tone"]["delta"] == -5


def test_idle_tone_gains_points():
    idle = score_offer(_facts(description="考研上岸了，用不上，闲置很久" + "详" * 60))
    assert {a["key"]: a for a in idle["adjustments"]}["idle_tone"]["delta"] == 3


def test_comment_signal_only_when_data_exists():
    """评论区没抓到时不能凭空产生 -5，那是拿「没数据」冒充「有信号」。"""
    no_data = score_offer(_facts(comment_asks=None))
    assert not any(a["key"] == "stale_asks" for a in no_data["adjustments"])

    with_data = score_offer(_facts(comment_asks=9))
    assert {a["key"]: a for a in with_data["adjustments"]}["stale_asks"]["delta"] == -5

    # 已售的商品不算「没人拍」
    sold = score_offer(_facts(comment_asks=9, sold_out=True))
    assert not any(a["key"] == "stale_asks" for a in sold["adjustments"])


def test_total_stays_within_bounds_after_adjustments():
    result = score_offer(_facts(price=950.0, published_at=NOW - timedelta(minutes=2), sold_out=True))
    assert 0 <= result["total"] <= 100


def test_adjustments_cannot_break_through_unknown_ceiling():
    """回归：辅助分不能把「缺锚点」的商品抬过它自己的理论上限。

    bug 现场：缺 25 分锚点时六维满分 75，辅助分 +10 → 总分 85 → 「直接冲」，
    等于让一条没比过全新价的商品绕过了整条规则。
    """
    result = score_offer(
        _facts(
            new_price_anchor=None,
            price=950.0,
            published_at=NOW - timedelta(minutes=2),
            sold_out=True,
        )
    )
    assert result["scored_max"] == 75
    assert result["total"] <= 75, f"辅助分突破上限：{result['total']}"
    assert result["grade"] != "buy"
    # 被上限吃掉的那部分要如实反映，否则明细加起来对不上总分
    assert result["adjustment_total"] == result["total"] - result["base_total"]
    assert result["adjustment_intent"] >= result["adjustment_total"]


def test_adjustments_cannot_lift_a_bad_offer_into_negotiable():
    """一条各维度几乎全垮的商品，「刚上架 +4」不该把它抬进「可谈」。"""
    result = score_offer(
        _facts(
            price=2000.0,          # 高于行情
            market_median=1200.0,
            new_price_anchor=2000.0,   # 相对全新毫无折扣
            image_count=0,
            description="好",
            tags=(),
            seller_credit="信用较差",
            sold_count=0,
            registered_months=1,
            warranty_months=-1,
            battery_cycles=1500,
            storage_matches=False,
            published_at=NOW - timedelta(minutes=1),
        )
    )
    assert result["total"] < GRADE_NEGOTIATE, f"烂货被辅助分抬到了 {result['total']}"
    assert result["grade"] == "skip"
    assert result["total"] <= result["scored_max"]


def test_top_config_regex_does_not_match_16_512():
    """回归：`16+512` 曾被子串 `16+1` 误判成「顶配」，每条都白送 3 分。

    这类错最难发现：分数看着合理，只是整体系统性偏高，
    任何单点断言都看不出来，只有专门测才抓得住。
    """
    plain = score_offer(_facts(title="OPPO Find X9 Pro 16+512 自用"))
    assert not any(a["key"] == "scarcity" for a in plain["adjustments"])

    top = score_offer(_facts(title="OPPO Find X9 Pro 24+1T 顶配"))
    assert any(a["key"] == "scarcity" for a in top["adjustments"])


# ---------------------------------------------------------------------------
# 缺项话术
# ---------------------------------------------------------------------------


def test_missing_items_feed_ask_script():
    """缺项要能直接变成问卖家的话，否则「闭环」是空话。"""
    result = score_offer(_facts(image_count=1, description="便宜出", tags=()))
    keys = [item["key"] for item in result["missing_items"]]
    assert "photos" in keys
    assert "serial" in keys
    assert "inspect" in keys
    assert result["ask_script"], "缺项应能拼出验机话术"
    # 评论区这一项必须显式存在，表示「没抓」，而不是假装查过
    assert "comments" in keys


def test_comments_item_has_no_fake_ask():
    result = score_offer(_facts())
    comment = next(i for i in result["missing_items"] if i["key"] == "comments")
    assert comment["ask"] == "", "评论区无法通过提问解决，不能编一句话术"


def test_missing_items_carry_lost_weight():
    """每个缺项要说明「丢了多少分」，用户才知道补哪一项最值。"""
    result = score_offer(_facts(market_median=None, market_scope="insufficient", market_samples=0))
    item = next(i for i in result["missing_items"] if i["key"] == "price_benchmark")
    assert item["weight_lost"] == 30


# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------


def test_registered_months_parses_chinese_years():
    assert registered_months("来闲鱼5年10个月") == 70
    assert registered_months("来闲鱼2年") == 24
    assert registered_months("来闲鱼7个月") == 7
    assert registered_months("") is None
    assert registered_months("未知") is None


def test_count_sold_only_counts_sold_listings():
    listings = [
        {"商品状态": "在售"},
        {"商品状态": "已售"},
        {"商品状态": "已售"},
    ]
    assert count_sold(listings) == 2
    assert count_sold([]) is None, "列表为空应是不可判，不是 0 件"
    assert count_sold(None) is None
