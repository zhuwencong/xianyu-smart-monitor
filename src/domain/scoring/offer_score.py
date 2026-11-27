"""二手交易的绝对分模型：6 个维度合计 100 分 + 辅助加减分 + 独立的一票否决。

这个模块与 ``engine.resolve_overall`` 是**两套不同的尺子**，不能互相顶替：

- ``resolve_overall``：相对分。它把「匹配 / 性能 / 价格 / 卖家 / 凭证」加权，
  再让 AI 的 ``value_score`` 掺 25%，回答的是「这机器本身有多好」。
  因为掺了 AI、又按卡片品类动态增删维度，它无法给出「80 分以上就冲」这种绝对阈值。

- 本模块：绝对分。全部由可复算的客观事实得出（二手价格比、相对全新折扣率、
  信用等级、已售件数、注册时长、保修/电池、验货宝标签），**不读 AI 的任何输出**，
  因此阈值是可信的：80 分就是「比二手行情低 + 比全新便宜得值 + 卖家可信 +
  拿到实证 + 机器可核验 + 平台内交易」。

**为什么要有两把价格尺子**：捡漏失败有两种——买到骗子机，或者买了个
「不划算的便宜」。只看二手行情（``price_market``）只能防住第一种：
一台 ¥2000 的 X8s 在二手市场里确实偏低，但全新清仓只要 ¥2549，
为省 21% 接一台没保修、可能用了两年的机器并不划算。所以必须再加
``value_vs_new``（二手价 ÷ 当前全新最低价），专门防第二种。

三条约定下的红线：

1. **不猜**。拿不到事实的维度标 ``value=None``（不可判），
   但**分母仍然是固定的 100，缺项按 0 计，不做剔除后重标定**。
   绝不塞一个「中位数」蒙混，也绝不用重标定把「没比成价」洗成满分。
   UI 上要显示成「不可判 / 缺口 xx 分」，不能显示成 0 分。
2. **不伪装核实**。「描述与图片是否一致」「是否催付款」这类没有原话依据的判断，
   一律在 evidence 里标 ``inferred=True``，让人知道这是推定而非核实。
3. **否决独立于总分**。命中任意一条 veto，``grade`` 强制 ``skip``，
   但 ``total`` 仍按实际得分计算并保留——这样能看出「一条好货可惜栽在定金上」，
   而不是所有被否决的商品又变成一个相同的 0 分。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# 权重：按「防骗 30 + 防买亏 25」的思路重排，合计 100。
#
# 为什么原模型不够：捡漏失败有两种——买到骗子机（原模型已防），
# 或买了个「比全新只便宜一点」的不划算所谓便宜（原模型完全没防）。
# 二手价再低，只要全新清仓价更低就没意义，所以必须引入「相对全新」的价比。
#
# 「时效性」从主维度降为辅助信号：它的 15 分权重被价格锚点拿走，
# 但信号本身仍然有用（刚上架 = 手要快），改为 ±分附加，见 _adjustments()。
WEIGHTS = {
    "price_market": 30,
    "value_vs_new": 25,
    "seller": 15,
    "authenticity": 15,
    "device_health": 10,
    "safety": 5,
}

DIMENSION_LABELS = {
    "price_market": "价格分",
    "value_vs_new": "性价比分",
    "seller": "卖家可信",
    "authenticity": "商品真实",
    "device_health": "机型健康",
    "safety": "交易安全",
}

# 顺序即 UI 展示顺序：先「贵不贵」，再「值不值」，再「人/货/机/交易」。
DIMENSION_ORDER = (
    "price_market",
    "value_vs_new",
    "seller",
    "authenticity",
    "device_health",
    "safety",
)

# 评级阈值（总分）。命中 veto 时一律 skip，这里只管纯分数。
GRADE_BUY = 80
GRADE_NEGOTIATE = 60
GRADE_WATCH = 40

GRADE_LABELS = {
    "buy": "直接冲",
    "negotiate": "可谈",
    "watch": "观望",
    "skip": "跳过",
}

# 捡漏线：低于同型号行情 15%。再深一档（-30% 以上）就不是漏，是钓鱼。
BARGAIN_RATIO = 0.85
# 低于行情 30% 以上：一票否决（无论卖家说得多好听）。
TOO_CHEAP_RATIO = 0.70

_COMPARABLE_SCOPES = {"model", "family"}

# --- 卖家信用档位：芝麻信用优先，缺失时退回「卖家信用等级」 ---
# 分值按 15 分权重缩放后的贡献给（原 20 分制时的 8/6/4/2/0 等比缩成 6 档）。
_CREDIT_SCORE = {
    "信用极好": 6,
    "信用优秀": 5,
    "信用良好": 3,
    "信用中等": 1,
    "信用较差": 0,
    "信用极差": 0,
}

_REGISTERED_RE = re.compile(r"(\d+)\s*年")
_REGISTERED_MONTH_RE = re.compile(r"(\d+)\s*个月")

# --- 个人卖家语气 ---
_PERSONAL_TOKENS = (
    "自用", "个人闲置", "闲置", "换机", "升级换下", "升级了", "自用一手",
    "自己用的", "本人", "只此一台", "仅此一台", "家里闲置", "用不上",
    "换了新", "毕业出", "搬家", "年会", "抽奖中的", "礼物",
)
# 注意不要收「支持验货」——它是验货宝的正向信号，会被商家词表误读成商家口吻。
# 「支持验机」「可开发票」这类说法个人卖家也会写，同样不列入。
_MERCHANT_TOKENS = (
    "全新未拆", "现货", "批发", "多台", "大量", "统一发货", "可开票",
    "零售", "代购", "机皇", "货源", "店铺", "本店", "包售后",
)

# --- 实证材料：序列号 / 电池界面 / 运行截图 ---
_SERIAL_TOKENS = (
    "序列号", "sn码", "sn号", "imei", "三码", "串号", "机身码",
    "电池健康", "电池容量", "循环次数", "电池效率", "gpu-z", "gpuz",
    "跑分", "烤机", "甜甜圈", "furmark", "压力测试", "健康度",
)

# --- 交易方式 ---
_INSPECT_TAG = "验货宝"
_INSPECT_TOKENS = ("验货宝", "走验货宝", "支持验货", "平台验机")
_FACE_TOKENS = (
    "面交", "自提", "同城", "可看机", "可验机", "当面", "现场试",
    "自取", "支持上门",
)

# --- 一票否决：站外交易 ---
# 注意：「微信支付」「扫码支付」是平台内支付方式，绝不能算站外引流。
_OFFSITE_TOKENS = (
    "加微信", "加vx", "加v", "加v信", "vx同号", "微信同号", "微信联系",
    "微信私聊", "扫码加", "站外交易", "私下交易", "不走平台", "脱离平台",
    "支付宝转账", "先转账", "直接转我",
)
_PAYMENT_CONTEXT = ("微信支付", "扫码支付", "支付宝支付", "花呗", "平台支付")
_PHONE_WECHAT_RE = re.compile(r"1[3-9]\d{9}\s*(?:微信|vx|v信|加)", re.IGNORECASE)
_PHONE_WECHAT_RE2 = re.compile(r"(?:微信|vx|v信)\s*[：:]?\s*1[3-9]\d{9}", re.IGNORECASE)

# --- 一票否决：定金 / 不验机 ---
# 「售出非质量问题不退不换」是二手常规免责，不算否决，故不收录。
_DEPOSIT_TOKENS = (
    "定金", "订金", "预付", "先付", "全款先", "款到发货", "先打款",
    "不验机", "不支持验机", "验机费", "验机收费", "不退定金",
)
_URGE_TOKENS = ("急出", "急售", "速拍", "马上付款", "立刻付款", "催付")


# --- 机型专属健康信号 ---
# 电池循环次数：实测 1174 条记录里出现 0 次——闲鱼列表页不提供该字段，
# 只有卖家主动在描述里写才有。所以它必然是「不可判」的常态，
# 不能当成 0 分扣，只能当成「未知，需向卖家索取」。
_CYCLE_RE = re.compile(r"(?:循环|充电次数|cycle)\D{0,6}(\d{1,4})\s*次?", re.IGNORECASE)
_WARRANTY_TOKENS = ("在保", "保修内", "还有保修", "质保内", "保期内", "官方保修")
_OUT_OF_WARRANTY_TOKENS = ("过保", "已过保", "保修过期", "无保修", "保修已过")
_ACTIVATED_RE = re.compile(r"激活(?:日期|时间|于)?\s*[：:]?\s*(\d{4})\s*[-年/.]?\s*(\d{1,2})")
# 版本核验：卖家自己写清容量配置，才谈得上「防低配刷高配描述」。
#
# 这里刻意**不用** `\b`——Python 的 `\w` 包含中文，`容量16+512` 里
# 「量」和「1」之间不存在单词边界，用 `\b` 会漏掉几乎所有中文场景的写法。
# 改为「匹配 + 白名单校验」：RAM 只认 2–32，存储只认常见档位，
# 这样 `5300+200` 这种价格相加不会被误当成 16+512。
_STORAGE_RE = re.compile(r"(\d{1,2})\s*[+＋]\s*(\d{3,4})\s*(?:g|gb)?", re.IGNORECASE)
_TB_RE = re.compile(r"(\d{1,2})\s*(?:t|tb)\b", re.IGNORECASE)
_GB_RE = re.compile(r"(\d{3,4})\s*(?:g|gb)\b", re.IGNORECASE)
_RAM_RANGE = range(2, 33)
_STORAGE_GB = frozenset({16, 32, 64, 128, 256, 512, 1024, 2048})

# --- 稀缺性 / 话术 ---
_PREMIUM_COLOR_TOKENS = ("限定色", "限定版", "特别版", "联名", "典藏")
# 顶配判定必须用正则，不能用子串。
#
# 曾经写成 tuple 里的 "16+1"，结果 `16+512` 包含子串 "16+1"，
# 所有 16+512 的机器都被误加「版本稀缺」+3 分——这是最难发现的一类错：
# 分数看着合理，只是每条都悄悄高了 3 分，任何单点断言都看不出来。
_TOP_CONFIG_RE = re.compile(
    r"(?:16|24)\s*[+＋]\s*1\s*t"      # 16+1T / 24+1T
    r"|(?<!\d)1\s*tb?\b",             # 单写 1T / 1TB
    re.IGNORECASE,
)
_TOP_CONFIG_TOKENS = ("顶配",)
# 真实闲置话术（+3）：这类说法没有商业动机，编造成本高。
_TRUE_IDLE_TOKENS = (
    "年会", "奖品", "抽奖", "中奖", "考研", "上岸", "毕业", "换新机",
    "换手机了", "用不上", "闲置很久", "买了没用", "多买了一台",
)
# 贩子话术（-5）：与商家口吻不同，这是「催单」语气，个人卖家极少这样说。
_HUSTLE_TOKENS = ("秒发", "仅需", "手慢无", "错过拍大腿", "最后一台", "清仓处理", "走过路过")

# --- 平台信号 ---
# 「评论区有人问还在吗超 5 条没人拍」需要商品评论区数据，当前链路完全没抓，
# 因此这一项恒为「不可判」，绝不假装算过。
_COMMENT_ASK_TOKENS = ("还在吗", "还有吗", "在不在", "出了吗")


@dataclass(frozen=True)
class OfferFacts:
    """一件商品的客观事实。全部字段都可能缺失，缺失即「不可判」。"""

    listing_id: str = ""
    price: float | None = None
    market_median: float | None = None
    market_scope: str = ""
    market_samples: int = 0
    published_at: datetime | None = None
    reference_at: datetime | None = None
    image_count: int = 0
    title: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    seller_credit: str = ""
    seller_level: str = ""
    sold_count: int | None = None
    registered_months: int | None = None

    # --- 相对全新的价格锚（由任务配置提供，不由模型猜） ---
    new_price_anchor: float | None = None
    # 锚点来源说明，用于 UI 展示「这个 2549 是谁定的、什么时候的」
    new_price_note: str = ""

    # --- 机型专属 ---
    # 保修剩余月数。None = 未知；负数 = 已过保。
    warranty_months: int | None = None
    # 电池循环次数。None = 卖家没写（常态）。
    battery_cycles: int | None = None
    # 卖家的版本描述是否与目标配置一致。None = 无法判断。
    storage_matches: bool | None = None
    # 商品评论区里的「还在吗」提问数。None = 没抓评论区（常态）。
    comment_asks: int | None = None
    # 已售状态（有人拍下）——这不是评论数据，列表页有，可以真判。
    sold_out: bool = False

    @property
    def text(self) -> str:
        return f"{self.title} {self.description}".lower()


@dataclass
class _Dimension:
    key: str
    value: int | None
    max_value: int
    reason: str
    inferred: bool = False

    def as_dict(self) -> dict:
        # 上限夹紧：万一某项分值表与权重脱节（曾出现卖家维度 16/15），
        # UI 绝不能显示「16/15」这种数字——那会让整块评分看起来是错的。
        # 开发期由 tests 里的不变量用例负责抓出来，这里只保证不出厂。
        value = self.value
        if value is not None and value > self.max_value:
            value = self.max_value
        return {
            "key": self.key,
            "label": DIMENSION_LABELS.get(self.key, self.key),
            "value": value,
            "max": self.max_value,
            # UI 画进度条用 max 当分母，同时把它当「权重」标注文字
            "weight": self.max_value,
            "reason": self.reason,
            "inferred": self.inferred,
            "scored": value is not None,
        }


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("¥", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def registered_months(raw) -> int | None:
    """把「来闲鱼5年10个月」解析成月数；解析不出来返回 None。"""
    text = str(raw or "")
    if not text:
        return None
    years = _REGISTERED_RE.search(text)
    months = _REGISTERED_MONTH_RE.search(text)
    if not years and not months:
        return None
    return (int(years.group(1)) * 12 if years else 0) + (int(months.group(1)) if months else 0)


def count_sold(listings) -> int | None:
    """数卖家已售件数。列表缺失返回 None（不可判），而不是 0（不可信）。"""
    if not isinstance(listings, list) or not listings:
        return None
    sold = 0
    for item in listings:
        if not isinstance(item, dict):
            continue
        if str(item.get("商品状态") or "") == "已售":
            sold += 1
    return sold


def parse_storage(title: str, description: str) -> tuple[int, int] | None:
    """从标题/描述里抽出 (内存GB, 存储GB)。抽不出返回 None。

    只认白名单档位，避免把「满 3000+200 优惠」这类价格相加误判成 16+512。
    """
    text = f"{title} {description}"
    for match in _STORAGE_RE.finditer(text):
        ram, storage = int(match.group(1)), int(match.group(2))
        if ram in _RAM_RANGE and storage in _STORAGE_GB:
            return ram, storage
    # 兜底：只写了「512G」这种单值存储
    for match in _GB_RE.finditer(text):
        if int(match.group(1)) in _STORAGE_GB:
            return 0, int(match.group(1))
    for match in _TB_RE.finditer(text):
        value = int(match.group(1)) * 1024
        if value in _STORAGE_GB:
            return 0, value
    return None


def storage_matches(title: str, description: str, target_config: str | None) -> bool | None:
    """卖家的容量描述是否与任务目标配置一致。

    返回 None 表示**无法判断**（卖家没写容量，或任务没指定目标配置）——
    与 False（写了但写的不对，疑似低配充高配）严格区分：
    前者是信息缺口，后者是风险信号，混为一谈会冤枉大量正常卖家。
    """
    target = _parse_target_config(target_config)
    if not target:
        return None
    found = parse_storage(title, description)
    if not found:
        return None
    _target_ram, target_storage = target
    _found_ram, found_storage = found
    return found_storage == target_storage


def _parse_target_config(raw: str | None) -> tuple[int, int] | None:
    """解析任务的「目标配置」，如 `12+512` / `512G` / `1T`。"""
    text = str(raw or "").strip()
    if not text:
        return None
    match = _STORAGE_RE.search(text)
    if match:
        ram, storage = int(match.group(1)), int(match.group(2))
        if ram in _RAM_RANGE and storage in _STORAGE_GB:
            return ram, storage
    match = _TB_RE.search(text)
    if match:
        value = int(match.group(1)) * 1024
        if value in _STORAGE_GB:
            return 0, value
    match = _GB_RE.search(text)
    if match:
        value = int(match.group(1))
        if value in _STORAGE_GB:
            return 0, value
    return None


def _has_any(text: str, tokens) -> str:
    for token in tokens:
        if token in text:
            return token
    return ""


def _offsite_hit(text: str) -> str:
    """站外引流命中判定。必须排除「微信支付」这类正常支付表述。"""
    for token in _OFFSITE_TOKENS:
        start = text.find(token)
        if start == -1:
            continue
        window = text[max(0, start - 12): start + len(token) + 12]
        if any(ctx in window for ctx in _PAYMENT_CONTEXT):
            continue
        return token
    match = _PHONE_WECHAT_RE.search(text) or _PHONE_WECHAT_RE2.search(text)
    if match:
        return match.group(0)
    return ""


# ---------------------------------------------------------------------------
# 主维度
# ---------------------------------------------------------------------------


def _score_price_market(facts: OfferFacts) -> tuple[_Dimension, list[dict]]:
    """价格分（30）：相对「同型号二手行情」，用来防骗。

    这一维只回答「这个价在二手市场里正常吗」，不回答「划不划算」。
    后者是 ``_score_value_vs_new`` 的事——两件事分开，是因为它们会给出
    相反的结论：一台 ¥3800 的 X9s Pro 在二手行情里可能偏低（该加分），
    但相对 ¥5299 的全新只便宜 28%（该扣分）。
    """
    vetoes: list[dict] = []
    median = _to_float(facts.market_median)
    price = _to_float(facts.price)
    comparable = facts.market_scope in _COMPARABLE_SCOPES and (facts.market_samples or 0) >= 3

    if not (price and median and median > 0 and comparable):
        return (
            _Dimension(
                "price_market",
                None,
                WEIGHTS["price_market"],
                "缺同型号行情基准，不拿跨型号均价凑数",
            ),
            vetoes,
        )

    ratio = price / median
    if ratio <= TOO_CHEAP_RATIO:
        vetoes.append(
            {
                "key": "too_cheap",
                "label": "价格低得反常",
                "detail": f"售价 ¥{price:g} 仅为同型号二手行情 ¥{median:g} 的 {ratio * 100:.0f}%，低于 30% 以上，疑似钓鱼或货不对板",
            }
        )
        return (
            _Dimension(
                "price_market", 0, WEIGHTS["price_market"],
                f"报价仅为二手行情 {ratio * 100:.0f}%，触发价格风控",
            ),
            vetoes,
        )
    # 按「低于二手行情几个百分点」划档，随优惠加深单调不减：
    #   高于行情 → 0 / 行情内 → 5 / 低 3~5% → 15 / 低 5~15% → 25 / 跌破捡漏线 → 30
    if ratio > 1.0:
        return _Dimension("price_market", 0, WEIGHTS["price_market"], f"高于二手行情 {(ratio - 1) * 100:.0f}%，无议价价值"), vetoes
    if ratio >= 0.97:
        return _Dimension("price_market", 5, WEIGHTS["price_market"], f"低于二手行情 {(1 - ratio) * 100:.1f}%，属正常价"), vetoes
    if ratio >= 0.95:
        return _Dimension("price_market", 15, WEIGHTS["price_market"], f"低于二手行情 {(1 - ratio) * 100:.1f}%，刚够谈价空间"), vetoes
    if ratio >= BARGAIN_RATIO:
        return _Dimension("price_market", 25, WEIGHTS["price_market"], f"低于二手行情 {(1 - ratio) * 100:.0f}%，接近捡漏线"), vetoes
    return (
        _Dimension(
            "price_market",
            30,
            WEIGHTS["price_market"],
            f"低于二手行情 {ratio * 100:.0f}%，属真漏且未到反常区间",
        ),
        vetoes,
    )


def _score_value_vs_new(facts: OfferFacts) -> _Dimension:
    """性价比分（25）：相对「当前电商全新最低价」，用来防买亏。

    这是原模型完全缺失的一维，也是最容易造成「假捡漏」的地方：
    二手 ¥2000 的 X8s 看着比行情低，但全新清仓只要 ¥2549，
    便宜 21% 就换一台没有保修、可能被用过两年的机器，并不划算。

    **锚点必须由人配置，不能由模型推断**。项目只抓闲鱼，拿不到京东/淘宝
    的实时价；让 AI 猜一个全新价等于凭空造数，比没有这一维更危险。
    没有配置锚点时这一维返回「不可判」，UI 上明确显示缺口。
    """
    price = _to_float(facts.price)
    anchor = _to_float(facts.new_price_anchor)
    if not (price and anchor and anchor > 0):
        return _Dimension(
            "value_vs_new",
            None,
            WEIGHTS["value_vs_new"],
            "任务未配置「全新最低价」锚点，无法判断这个二手价是否真划算",
        )

    ratio = price / anchor
    note = f"（锚点 ¥{anchor:g}{'，' + facts.new_price_note if facts.new_price_note else ''}）"
    if ratio >= 0.85:
        return _Dimension(
            "value_vs_new", 5, WEIGHTS["value_vs_new"],
            f"二手价是全新的 {ratio * 100:.0f}%，只便宜 {100 - ratio * 100:.0f}%，不如买新{note}",
        )
    if ratio >= 0.75:
        return _Dimension(
            "value_vs_new", 10, WEIGHTS["value_vs_new"],
            f"二手价是全新的 {ratio * 100:.0f}%，属正常二手价{note}",
        )
    if ratio >= 0.65:
        return _Dimension(
            "value_vs_new", 18, WEIGHTS["value_vs_new"],
            f"二手价是全新的 {ratio * 100:.0f}%，比全新省 {100 - ratio * 100:.0f}%，值得出手{note}",
        )
    return _Dimension(
        "value_vs_new", 25, WEIGHTS["value_vs_new"],
        f"二手价仅为全新的 {ratio * 100:.0f}%，省 {100 - ratio * 100:.0f}%，真漏（前提是没有命中风控）{note}",
    )


def _score_seller(facts: OfferFacts) -> _Dimension:
    credit_text = str(facts.seller_credit or "") or str(facts.seller_level or "")
    credit_value: int | None = None
    for key, value in _CREDIT_SCORE.items():
        if key in credit_text:
            credit_value = value
            break

    sold = facts.sold_count
    if sold is None:
        sold_value: int | None = None
    elif sold >= 5:
        sold_value = 5
    elif sold >= 3:
        sold_value = 3
    elif sold >= 1:
        sold_value = 1
    else:
        sold_value = 0

    months = facts.registered_months
    if months is None:
        tenure_value: int | None = None
    elif months >= 12:
        tenure_value = 3
    elif months >= 6:
        tenure_value = 1
    else:
        tenure_value = 0

    # 个人语气是文本推定，权重最低（1 分），不能让它左右结论。
    personal = _has_any(facts.text, _PERSONAL_TOKENS)
    merchant = _has_any(facts.text, _MERCHANT_TOKENS)
    if merchant:
        tone_value: int | None = 0
        tone_reason = f"描述出现商家口吻「{merchant}」"
    elif personal:
        tone_value = 1
        tone_reason = f"描述为个人语气「{personal}」"
    else:
        tone_value = None
        tone_reason = "描述未体现个人或商家口吻"

    # 分值按 15 分权重等比缩放（信用 6 / 成交 5 / 年资 3 / 语气 1）。
    parts = [
        ("信用", credit_value, 6),
        ("历史成交", sold_value, 5),
        ("账号年资", tenure_value, 3),
        ("个人语气", tone_value, 1),
    ]
    earned = sum(v for _n, v, _m in parts if v is not None)

    # 三项客观事实（信用/成交/年资，共 14 分）全缺时，不能用「个人语气」1 分
    # 撑满整个维度——那等于用一句软文把「卖家资料全无」包装成可信卖家。
    # 客观事实一项都拿不到就整维不可判，这是这条维度存在的意义。
    has_objective = any(v is not None for _n, v, _m in parts[:3])
    if not has_objective:
        return _Dimension(
            "seller",
            None,
            WEIGHTS["seller"],
            "卖家信用、成交记录、注册时长全部缺失，无法判断可信度",
        )

    detail = "、".join(
        f"{name}{'—' if v is None else v}" for name, v, _m in parts
    )
    value = earned
    reason = f"{detail}（{tone_reason}）" if tone_value is not None else f"{detail}"
    return _Dimension("seller", value, WEIGHTS["seller"], reason, inferred=tone_value is not None)


def _score_authenticity(facts: OfferFacts) -> _Dimension:
    """商品真实（15）：图、实证材料、图文一致。分值按 15 分权重缩放。"""
    images = max(0, int(facts.image_count or 0))
    if images >= 3:
        photo_value, photo_reason = 5, f"{images} 张图，符合实拍特征"
    elif images >= 1:
        photo_value, photo_reason = 2, f"仅 {images} 张图，不足以判断成色"
    else:
        photo_value, photo_reason = 0, "无商品图片"

    serial = _has_any(facts.text, _SERIAL_TOKENS)
    serial_value = 6 if serial else 0
    serial_reason = f"描述含实证材料「{serial}」" if serial else "缺序列号/电池健康等实证截图"

    # 一致性只能靠「描述是否具体 + 是否有足够图片」做代理推断，
    # 真正的图描述比对需要视觉模型，这里必须标明是推定。
    desc_len = len(str(facts.description or ""))
    consistent = desc_len >= 80 and images >= 2
    consistency_value = 4 if consistent else 0
    consistency_reason = (
        f"描述 {desc_len} 字且配图 {images} 张，具备核对条件（推定，未逐图比对）"
        if consistent
        else "描述过简或图片不足，无法核对图文一致性"
    )

    parts = [
        ("实拍图", photo_value, 5, photo_reason),
        ("实证材料", serial_value, 6, serial_reason),
        ("图文一致", consistency_value, 4, consistency_reason),
    ]
    earned = sum(v for _n, v, _m, _r in parts)
    reason = "；".join(f"{name}{v}/{m}" for name, v, m, _r in parts)
    return _Dimension(
        "authenticity",
        earned,
        WEIGHTS["authenticity"],
        reason,
        inferred=True,
    )


def _score_device_health(facts: OfferFacts) -> _Dimension:
    """机型健康（10）：保修剩余 / 电池循环 / 版本核验。

    这一维替代了原来的「通用成色」。理由：成色是主观形容词（「99新」人人会写），
    而保修、电池、配置是能查证的事实，且随机型生命周期变化——X8s 上市 19 个月
    大多已过保，X9s Pro 上市 7 个月本该还剩 5 个月保修，同一套标准对两者不公平。

    **电池循环必须允许「不可判」**：实测 1174 条记录里出现 0 次，
    平台不提供这个字段。把它当 0 分扣等于惩罚所有卖家，所以只给「未知」。
    """
    parts: list[tuple[str, int | None, int, str]] = []

    # --- 保修（4 分）---
    warranty = facts.warranty_months
    if warranty is None:
        if _has_any(facts.text, _WARRANTY_TOKENS):
            warranty = 1
        elif _has_any(facts.text, _OUT_OF_WARRANTY_TOKENS):
            warranty = -1
    if warranty is None:
        warranty_value, warranty_reason = None, "未说明保修状态"
    elif warranty > 0:
        warranty_value = 4
        warranty_reason = f"在保（剩约 {warranty} 个月）" if warranty > 1 else "描述称仍在保"
    else:
        warranty_value = 0
        warranty_reason = "已过保"
    parts.append(("保修", warranty_value, 4, warranty_reason))

    # --- 电池循环（4 分）---
    cycles = facts.battery_cycles
    if cycles is None:
        match = _CYCLE_RE.search(facts.text)
        if match:
            try:
                cycles = int(match.group(1))
            except (TypeError, ValueError):
                cycles = None
    if cycles is None:
        cycles_value, cycles_reason = None, "卖家未提供电池循环次数（平台不显示，需主动索取）"
    elif cycles <= 300:
        cycles_value = 4
        cycles_reason = f"循环 {cycles} 次，电池状态良好"
    elif cycles <= 800:
        cycles_value = 2
        cycles_reason = f"循环 {cycles} 次，正常衰减"
    else:
        cycles_value = 0
        cycles_reason = f"循环 {cycles} 次，衰减明显"
    parts.append(("电池", cycles_value, 4, cycles_reason))

    # --- 版本核验（2 分）---
    if facts.storage_matches is None:
        storage_value, storage_reason = None, "描述未写清容量配置，无法核验版本"
    elif facts.storage_matches:
        storage_value = 2
        storage_reason = "描述配置与目标一致"
    else:
        storage_value = 0
        storage_reason = "描述配置与目标不符，疑似低配充高配"
    parts.append(("版本", storage_value, 2, storage_reason))

    known = [(n, v, m, r) for n, v, m, r in parts if v is not None]
    if not known:
        return _Dimension(
            "device_health",
            None,
            WEIGHTS["device_health"],
            "保修、电池、配置三项都无法核验",
        )
    earned = sum(v for _n, v, _m, _r in known)
    # 只说「电池0/4」看不出关键数字（循环 1200 次还是 900 次差别很大），
    # 所以把**得分最低那几项**的具体依据附上。只列掉分的项，
    # 满分项列出来只是噪音——它们已经由 4/4 数字说清了。
    weak = [r for _n, v, m, r in parts if v is not None and v < m]
    summary = "；".join(f"{n}{'未知' if v is None else v}/{m}" for n, v, m, _r in parts)
    reason = f"{summary}（{'；'.join(weak)}）" if weak else summary
    return _Dimension(
        "device_health",
        earned,
        WEIGHTS["device_health"],
        reason,
        inferred=True,
    )


def _freshness_days(facts: OfferFacts) -> float | None:
    published = facts.published_at
    if published is None:
        return None
    reference = facts.reference_at or datetime.now()
    return (reference - published).total_seconds() / 86400


def _score_safety(facts: OfferFacts) -> tuple[_Dimension, list[dict]]:
    vetoes: list[dict] = []
    joined_tags = " ".join(facts.tags or ())
    inspect = bool(_has_any(joined_tags, (_INSPECT_TAG,)) or _has_any(facts.text, _INSPECT_TOKENS))
    face = bool(_has_any(facts.text, _FACE_TOKENS))

    offsite = _offsite_hit(facts.text)
    deposit = _has_any(facts.text, _DEPOSIT_TOKENS)
    urge = _has_any(facts.text, _URGE_TOKENS)

    if offsite:
        vetoes.append(
            {
                "key": "offsite",
                "label": "引导站外交易",
                "detail": f"描述出现「{offsite}」，脱离平台交易没有保障",
            }
        )
    if deposit:
        vetoes.append(
            {
                "key": "deposit",
                "label": "要求定金/不验机",
                "detail": f"描述出现「{deposit}」，先款或拒绝验机均不可接受",
            }
        )

    # 分值按 5 分权重缩放（验货宝 2.5 / 面交 1.5 / 不催款 1），取整后为 3/1/1。
    #
    # 权重从 15 降到 5 是有意的：交易方式的风险已经由「一票否决」兜住
    # （站外引流、定金、不验机都直接 skip），再给它 15 分等于双重计罚。
    # 剩下的 5 分只用来在「都合规」的商品之间拉开细微差距。
    inspect_value = 3 if inspect else 0
    face_value = 1 if face else 0
    # 「不催款」没有对话数据，只能由描述里有无催促话术反推，属推定值。
    pressure_value = 0 if (deposit or urge or offsite) else 1

    parts = [
        ("验货宝", inspect_value, 3),
        ("面交验机", face_value, 1),
        ("不催款", pressure_value, 1),
    ]
    earned = sum(v for _n, v, _m in parts)
    reason = "、".join(f"{name}{v}/{m}" for name, v, m in parts)
    return (
        _Dimension("safety", earned, WEIGHTS["safety"], reason, inferred=True),
        vetoes,
    )


def _adjustments(facts: OfferFacts) -> list[dict]:
    """辅助信号：不占主权重，直接对总分做 ± 修正。

    这一组回答的是「主维度看不见的临门一脚」：稀缺色、真实闲置话术、
    贩子催单话术、刚上架。它们的共同点是**证据强度弱于主维度**，
    所以给 ±分而不是给权重——权重会让弱信号在总分里占固定比例，
    一旦某条缺数据就会系统性偏移；±分只在命中时生效，不命中时不扣不加。

    上限钉死在 ±10，且总分会再夹到 0–100，避免辅助信号把结论翻盘。
    """
    items: list[dict] = []

    # 版本稀缺性（+3）：限定色/顶配流动性好，砸手里风险低。
    premium = _has_any(facts.text, _PREMIUM_COLOR_TOKENS) or _has_any(facts.text, _TOP_CONFIG_TOKENS)
    if not premium and _TOP_CONFIG_RE.search(facts.text):
        premium = _TOP_CONFIG_RE.search(facts.text).group(0)
    if premium:
        items.append({"key": "scarcity", "label": f"版本稀缺「{premium}」", "delta": 3, "tone": "good"})

    # 描述话术：真实闲置 +3，贩子催单 -5。
    idle = _has_any(facts.text, _TRUE_IDLE_TOKENS)
    hustle = _has_any(facts.text, _HUSTLE_TOKENS)
    if idle and not hustle:
        items.append({"key": "idle_tone", "label": f"真实闲置话术「{idle}」", "delta": 3, "tone": "good"})
    if hustle:
        items.append({"key": "hustle_tone", "label": f"贩子催单话术「{hustle}」", "delta": -5, "tone": "bad"})

    # 时效性（原 15 分主维度，现降为辅助）：刚上架 +4，超过 3 天 -4。
    days = _freshness_days(facts)
    if days is not None:
        if 0 <= days < 1 / 24:
            items.append({"key": "freshness", "label": "刚上架（1 小时内）", "delta": 4, "tone": "good"})
        elif days <= 1:
            items.append({"key": "freshness", "label": "上架 1 天内", "delta": 2, "tone": "good"})
        elif days > 3:
            items.append({"key": "freshness", "label": f"上架已 {int(days)} 天", "delta": -4, "tone": "bad"})

    # 平台信号：
    # - 「已售」是列表页真有的数据，可以真判（+2，说明这条已被市场验证）。
    # - 「评论区问还在吗超 5 条没人拍」需要商品评论区，当前链路没抓，
    #   所以只在真的拿到 comment_asks 时才计算，否则什么都不输出，
    #   绝不用「没有信号」冒充「信号正常」。
    if facts.sold_out:
        items.append({"key": "sold_out", "label": "该链接已售（他人已拍下）", "delta": 2, "tone": "good"})
    if facts.comment_asks is not None and facts.comment_asks > 5 and not facts.sold_out:
        items.append(
            {
                "key": "stale_asks",
                "label": f"评论区 {facts.comment_asks} 人问「还在吗」仍无人拍",
                "delta": -5,
                "tone": "bad",
            }
        )

    # 夹住辅助总分，防止多条叠加后反客为主。
    # 这里不只是加一行说明，而是要**把明细之和真正压回 ±10**：
    # 否则 UI 上列出的每一条加减分加起来的数与实际进总分的数不一致，
    # 用户会看到「-4 -5 +3 +4 = -2」却显示总分多了 10 分，那是最难查的一类错。
    total = sum(int(item["delta"]) for item in items)
    if total > 10:
        items.append({"key": "clamp", "label": f"辅助分合计 {total:+d}，按 +10 封顶", "delta": 10 - total, "tone": "neutral"})
    elif total < -10:
        items.append({"key": "clamp", "label": f"辅助分合计 {total:+d}，按 -10 封顶", "delta": -10 - total, "tone": "neutral"})
    return items


# ---------------------------------------------------------------------------
# 缺项 → 验机话术
# ---------------------------------------------------------------------------

_ASK_SCRIPTS = {
    "price_benchmark": "这台能按¥{price}出的话我今天就能拍，方便的话发个实拍视频？",
    "serial": "能拍一下序列号/设置里的关于本机页面吗？另外电池健康度是多少？",
    "photos": "目前只看到 {count} 张图，能不能补几张细节图和瑕疵处特写？",
    "inspect": "支持走验货宝吗？我承担验货费用，走平台对双方都更稳妥。",
    "face": "支持同城面交当面验机吗？我这边可以配合你的时间。",
    "seller": "看您主页成交不多，方便说下这台机器的购买渠道和入手时间吗？",
    "warranty": "这台是什么时候激活的？保修还在的话，麻烦截一下关于本机里的保修状态。",
    "cycles": "电池循环次数和健康度能截个图吗？闲鱼页面不显示这个，我得自己确认一下。",
    "storage": "麻烦拍一下「关于本机」里的容量信息，我想确认下版本和描述一致。",
}


def _missing_items(facts: OfferFacts, dims: dict[str, _Dimension]) -> list[dict]:
    """缺项清单：既是「这一项没算分」的说明，也是「该去问什么」的话术来源。

    每条都带 ``ask``（可直接复制的问卖家话术）或为空字符串——
    空字符串代表这个问题**问卖家也没用**（锚点没配、评论区没抓），
    此时绝不编一句听着像样的话糊弄过去。
    """
    missing: list[dict] = []

    if dims["price_market"].value is None:
        missing.append(
            {
                "key": "price_benchmark",
                "label": "缺同型号行情基准",
                "detail": "同型号样本不足 3 条，无法判断这个价格在二手市场里算不算低",
                "weight_lost": WEIGHTS["price_market"],
                "ask": _ASK_SCRIPTS["price_benchmark"].format(
                    price=int(facts.price) if facts.price else "标价"
                ),
            }
        )

    # 锚点缺失是**任务配置问题**，不是卖家的问题——所以 ask 为空，
    # 只在 detail 里明确告诉人「去任务设置里填一个当前全新最低价」。
    if dims["value_vs_new"].value is None:
        note = f"锚点备注：{facts.new_price_note}" if facts.new_price_note else ""
        missing.append(
            {
                "key": "new_price_anchor",
                "label": "未配置全新价锚点",
                "detail": "拿不到电商实时价，需在任务设置里手动填「当前全新最低价（含国补/清仓）」，否则无法判断这个二手价是否真划算",
                "weight_lost": WEIGHTS["value_vs_new"],
                "ask": "",
                "internal": True,
                "note": note,
            }
        )

    # 保修：只在「既没有结构化月数、描述里也没提在保/过保」时才列为缺项。
    # 卖家写了「过保」不算缺失——那是有答案，只是答案不好。
    if facts.warranty_months is None and not _has_any(facts.text, _WARRANTY_TOKENS + _OUT_OF_WARRANTY_TOKENS):
        missing.append(
            {
                "key": "warranty",
                "label": "保修状态未知",
                "detail": "描述没写在保还是过保，这直接决定机器还剩多少残值",
                "weight_lost": 4,
                "ask": _ASK_SCRIPTS["warranty"],
            }
        )

    cycles = facts.battery_cycles
    if cycles is None:
        match = _CYCLE_RE.search(facts.text)
        if match:
            cycles = int(match.group(1)) if match.group(1).isdigit() else None
    if cycles is None:
        missing.append(
            {
                "key": "battery_cycles",
                "label": "电池循环次数未知",
                "detail": "闲鱼列表页不提供该字段，实测 1174 条记录里出现 0 次，必须主动向卖家索取截图",
                "weight_lost": 4,
                "ask": _ASK_SCRIPTS["cycles"],
            }
        )

    if facts.storage_matches is None:
        missing.append(
            {
                "key": "storage",
                "label": "容量版本未核实",
                "detail": "描述没写清内存+存储配置，无法排除低配充高配",
                "weight_lost": 2,
                "ask": _ASK_SCRIPTS["storage"],
            }
        )

    serial = _has_any(facts.text, _SERIAL_TOKENS)
    if not serial:
        missing.append(
            {
                "key": "serial",
                "label": "缺序列号/电池截图",
                "detail": "没有序列号、IMEI、电池健康或跑分截图，无法排除翻新和串号",
                "weight_lost": 6,
                "ask": _ASK_SCRIPTS["serial"],
            }
        )

    images = max(0, int(facts.image_count or 0))
    if images < 3:
        missing.append(
            {
                "key": "photos",
                "label": f"实物图不足（{images} 张）",
                "detail": "图片少于 3 张，成色与配件完整度无法确认",
                "weight_lost": 5 if images else 5,
                "ask": _ASK_SCRIPTS["photos"].format(count=images),
            }
        )

    joined_tags = " ".join(facts.tags or ())
    if not (_has_any(joined_tags, (_INSPECT_TAG,)) or _has_any(facts.text, _INSPECT_TOKENS)):
        missing.append(
            {
                "key": "inspect",
                "label": "未开通验货宝",
                "detail": "卖家未标验货宝，平台不介入验机",
                "weight_lost": 3,
                "ask": _ASK_SCRIPTS["inspect"],
            }
        )
    if not _has_any(facts.text, _FACE_TOKENS):
        missing.append(
            {
                "key": "face",
                "label": "未提面交",
                "detail": "描述没有提到同城面交，无法当面验机",
                "weight_lost": 1,
                "ask": _ASK_SCRIPTS["face"],
            }
        )
    if (facts.sold_count or 0) < 1:
        missing.append(
            {
                "key": "seller",
                "label": "卖家无成交记录",
                "detail": "主页看不到已完成交易，账号可信度无法佐证",
                "weight_lost": 5,
                "ask": _ASK_SCRIPTS["seller"],
            }
        )

    # 这条永远存在：商品评论区在现有抓取链路里拿不到。
    # 与其假装检查过「评论区有翻新/串号实锤质疑」这条否决，
    # 不如明确告诉用户「这一项没看，请人工点开商品页核对」。
    missing.append(
        {
            "key": "comments",
            "label": "商品评论区未抓取",
            "detail": "「评论区有翻新/串号实锤质疑」这条否决暂无数据来源，需人工点开商品页核对",
            "weight_lost": 0,
            "ask": "",
        }
    )
    return missing


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def score_offer(facts: OfferFacts, *, hard_blocks: tuple[dict, ...] = ()) -> dict:
    """对一件商品打绝对分。纯函数，不读库、不调模型。

    ``hard_blocks`` 是本项目底层硬门槛（矿卡/故障/维修史/价格异常等）的命中结果。
    它们**必须**并入一票否决：否则一张矿卡能靠「价格低 + 卖家信用好 + 图多」
    凑到 86 分显示「直接冲」，和引擎那边「强制不匹配」的结论直接打架。
    硬门槛不算分、只否决，所以并入后总分照常计算，只是 grade 强制 skip。
    """
    price_dim, price_vetoes = _score_price_market(facts)
    safety_dim, safety_vetoes = _score_safety(facts)
    dims = {
        "price_market": price_dim,
        "value_vs_new": _score_value_vs_new(facts),
        "seller": _score_seller(facts),
        "authenticity": _score_authenticity(facts),
        "device_health": _score_device_health(facts),
        "safety": safety_dim,
    }

    # 分母固定 100，**缺失维度按 0 计**，不做「剔除后重标定」。
    #
    # 这一点必须如此：如果用 `earned / possible` 重标定，一个缺价格分（30 分）的
    # 商品只要其余维度满分就能算出 100 分「直接冲」——而它恰恰是没比价成功的那台。
    # 实测 1126 条记录里绝大多数手机任务的同型号样本不足，重标定会让这些商品
    # 全部顶格，评分体系的绝对阈值立刻失效。缺项就是拿不到分，这是诚实的代价。
    #
    # 同一个逻辑延伸到新加的「性价比分」：没配全新价锚点的任务，25 分直接没了，
    # 所以最高只能到 75 分 = 「可谈」。这不是 bug，而是「不知道划不划算就不许冲」。
    base = sum(int(v.value or 0) for v in dims.values())
    possible = sum(v.max_value for v in dims.values() if v.value is not None)

    # 辅助信号不占权重，只在总分上做 ±修正，合计钉死 ±10。
    adjustments = _adjustments(facts)
    adj_total = sum(int(a["delta"]) for a in adjustments)
    adj_total = max(-10, min(10, adj_total))

    # **上限是 scored_max，不是 100**。
    #
    # 这一条与「缺项按 0 计」是同一个原则的两面：拿不到的分不能靠时效性补回来。
    # 缺 25 分锚点时理论最高 75，若允许 +10 辅助分把总分抬到 85，
    # 就等于「没比过全新价」的商品也能显示「直接冲」，规则被辅助分绕过去了。
    # 反过来也一样：六维都是 0 分的商品，不该因为「刚上架」就变成 4 分好货。
    ceiling = possible if possible else 0
    total = None if possible == 0 else max(0, min(ceiling, base + adj_total))
    # 实际计入总分的辅助分，与「意图加分」分开报。
    # 两者不等时（被缺项上限吃掉），UI 必须显示实际值，否则加减分明细对不上账。
    adj_applied = 0 if total is None else total - base

    price_unknown = dims["price_market"].value is None
    value_unknown = dims["value_vs_new"].value is None

    vetoes = price_vetoes + safety_vetoes + list(hard_blocks)
    if vetoes:
        grade = "skip"
    elif total is None:
        grade = "watch"
    elif total >= GRADE_BUY:
        grade = "buy"
    elif total >= GRADE_NEGOTIATE:
        grade = "negotiate"
    elif total >= GRADE_WATCH:
        grade = "watch"
    else:
        grade = "skip"

    # 「总分够但结论不能给」的降级，顺序即优先级。
    #
    # 这里必须用**全部满分的理论值**判断，而不是检查 total 是否已经必然 ≤75。
    # 因为辅助分最多能把总分抬 10 分：缺 25 分锚点的商品，六维满分只有 75，
    # 加上 +10 辅助分就变成 85 —— 一条没比过全新价的商品于是显示「直接冲」，
    # 正好绕开了「不知道划不划算就不许冲」这条规则。
    if grade == "buy" and price_unknown:
        grade = "negotiate"
    if grade == "buy" and value_unknown:
        grade = "negotiate"
    # 交易安全拿不到一半（既无验货宝也无面交），不能标「直接冲」。
    # 这维度只有 5 分，扣完也不足以把总分拉到 80 以下——实测一条价格合适、
    # 卖家干净的显卡能靠其他维度凑到 83 分，但它恰恰是「平台不验机、
    # 也不给当面验」的最危险组合。评级要给结论，不能只看加权和。
    if grade == "buy" and (dims["safety"].value or 0) < WEIGHTS["safety"] / 2:
        grade = "negotiate"

    missing = _missing_items(facts, dims)
    grade_note = ""
    if vetoes:
        grade_note = "命中一票否决，总分仅供参考（分数反映成色与价格，不代表可以买）"
    elif price_unknown and value_unknown:
        grade_note = "价格与性价比两维都不可判，最高只能给「可谈」"
    elif price_unknown:
        grade_note = "二手行情维度不可判（同型号样本不足），最高只能给「可谈」"
    elif value_unknown:
        grade_note = (
            f"未配置全新价锚点，缺失 {WEIGHTS['value_vs_new']} 分，"
            f"最高只能给「可谈」——去任务设置里填当前全新最低价"
        )
    elif grade == "negotiate" and total >= GRADE_BUY:
        grade_note = "总分够高，但交易方式不安全（无验货宝/面交），先谈妥验机再下手"
    elif grade == "skip" and total >= GRADE_WATCH:
        grade_note = "总分不足 60"
    elif grade == "skip":
        grade_note = "总分不足 40"

    price = _to_float(facts.price)
    anchor = _to_float(facts.new_price_anchor)
    return {
        "listing_id": str(facts.listing_id or ""),
        "scores": {k: (v.value if v.value is not None else None) for k, v in dims.items()},
        "weights": dict(WEIGHTS),
        "dimensions": [dims[k].as_dict() for k in DIMENSION_ORDER],
        "total": total,
        # base_total 是六个维度拿到的原始分，total 是加上辅助分后的最终分。
        # 分开给，UI 才能解释「为什么 71 分的商品显示 74」。
        "base_total": base if possible else None,
        # scored_max = 实际拿到过分的维度权重之和；缺项时它小于 100
        "scored_max": possible,
        "max_total": 100,
        "adjustments": adjustments,
        "adjustment_total": adj_applied,
        "adjustment_intent": adj_total,
        "price_judged": not price_unknown,
        "value_judged": not value_unknown,
        "grade": grade,
        "grade_label": GRADE_LABELS[grade],
        "grade_note": grade_note,
        "veto_flags": vetoes,
        "vetoed": bool(vetoes),
        "missing_items": missing,
        "missing_labels": [item["label"] for item in missing],
        "ask_script": "；".join(
            item["ask"] for item in missing if item.get("ask")
        ),
        # 两个价格比率都直接给，省得前端再算一遍，也避免两边算错不一致
        "price_ratio": (round(price / _to_float(facts.market_median), 4) if price and _to_float(facts.market_median) else None),
        "ratio_used_vs_new": round(price / anchor, 4) if price and anchor else None,
        "market_median": _to_float(facts.market_median),
        "new_price_anchor": anchor,
        "new_price_note": facts.new_price_note,
    }

