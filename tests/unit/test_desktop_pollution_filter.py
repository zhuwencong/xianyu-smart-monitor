# -*- coding: utf-8 -*-
"""手机任务反台式机污染过滤的回归测试。

背景：闲鱼搜「OPPO Find X8 Ultra 16+512」，会返回大量台式主机 ——
卖家把「16G内存 + 512G固态」当成卖点，和手机的 16+512 撞在一起。
这类商品被 AI 误判推荐率低，但会消耗详情页请求（风控主要触发点）
和图片 token，必须在下详情前就用标题挡掉。

关键教训（导致误杀的词）：
- 「整机」  → 手机写「整机全原装、无拆无修」
- 「装机」  → 「原装机」包含「装机」
- 「处理器」→ 「天玑9500处理器」（89 条手机）
- 「内存」  → 「16+512内存」「内存16+512」
- 「主板」  → 「主板原装无拆修」「主板状态正常」
这些词一旦进排除列表，误杀的手机远多于挡掉的电脑。
"""
from src.services.title_filter import build_title_filter

EXCLUDE = [
    "主机", "台式", "显卡", "核显", "独显", "显存", "rtx", "gtx", "geforce",
    "固态", "机械硬盘", "nvme", "机箱", "水冷", "风冷", "散热器", "鲁大师",
    "显示器", "内存条", "ddr4", "ddr5", "cpu", "酷睿", "锐龙",
    "i3-", "i5-", "i7-", "12400", "13400", "12600", "13600", "12100", "12490", "10400",
    "3700x", "5600x", "b450", "b550", "b560", "b660", "b760", "h510", "h610", "a520", "z690",
    "电脑", "硬盘", "win10", "win11", "跑分",
]


def _flt():
    return build_title_filter(include=None, exclude=EXCLUDE)


class TestDesktopPCFiltered:
    """真实台式主机标题必须被挡掉。"""

    def test_typical_desktop_listing(self):
        title = (
            "主机一套，i5-12400F六核，16G海盗船DDR4，RX 6750 10G显存，"
            "华硕H610M主板，512G固态，接口全，功能都好，鲁大师跑分120万+"
        )
        keep, reason = _flt().check(title)
        assert keep is False, "台式主机没被过滤"
        assert "命中排除词" in reason

    def test_desktop_without_the_word_host(self):
        """没写「主机」但配置一堆硬件，也要挡。"""
        title = (
            "cpui5 12400f 主板华硕610m-k argb 内存金百达银爵8x2 3200 "
            "硬盘金百达kp230 512g 二手显卡七彩虹烈焰战神1060"
        )
        assert _flt().check(title)[0] is False

    def test_desktop_full_build(self):
        title = (
            "i7-13700H+RTX3070m游戏电脑主机｜14核CPU｜32G内存｜512G固态，"
            "个人自用一手自用台式整机，英特尔13代"
        )
        assert _flt().check(title)[0] is False


class TestPhoneNotFiltered:
    """真手机一条都不能被误杀 —— 这是本组词存在的唯一理由。"""

    def test_phone_says_zhengji_quanyuanzhuang(self):
        """「整机全原装」里的整机指手机整机，所以「整机」不能作排除词。"""
        title = (
            "OPPO Find X8 Ultra 16+512G 月光白，国行正品，"
            "整机全原装、无拆无修，全网通5G，插卡直接用。"
        )
        assert _flt().check(title)[0] is True

    def test_phone_says_yuanzhuangji(self):
        """「原装机」包含「装机」二字，所以「装机」不能作排除词。"""
        title = "OPPO findx9pro 12+512 原装机 出单机送 69原厂手机壳 无磕碰"
        assert _flt().check(title)[0] is True

    def test_phone_says_chuliqi(self):
        """「天玑9500处理器」是手机规格，所以「处理器」不能作排除词。"""
        title = "个人闲置 OPPO Find X9 Pro 16+512G， 国行无锁，天玑9500处理器，ColorOS 17系统"
        assert _flt().check(title)[0] is True

    def test_phone_says_neicun(self):
        """「16+512内存」是手机写法，所以「内存」不能作排除词。"""
        title = "Oppo find x8 ultra 黑 16+512内存 电池97 全原无拆修 成色靓"
        assert _flt().check(title)[0] is True

    def test_phone_says_zhuban_zhuangtai_zhengchang(self):
        """「主板原装无拆修」是手机验机话术，所以「主板」不能作排除词。"""
        title = (
            "系统流畅，外观很新，无磕碰划痕；主板原装无拆修，"
            "支持指纹解锁。包装配件齐全"
        )
        assert _flt().check(title)[0] is True

    def test_phone_with_cpu_brand_only(self):
        """只提芯片品牌不提整机配置的手机不该被挡。"""
        title = "OPPO Find X9 Pro 16+512 追光红 天玑9500 7500mAh 电池健康100%"
        assert _flt().check(title)[0] is True


class TestTabletPadNotFiltered:
    def test_pad_go(self):
        """平板也算移动设备，虽然带了「8G+512G」，但没硬件词组合，保留。"""
        title = "当贝PadGO闺蜜机 熊猫白 27寸4K大屏 8G+512G，屏幕高度可调，安卓系统 WiFi6"
        assert _flt().check(title)[0] is True
