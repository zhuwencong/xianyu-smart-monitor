"""
AI 请求消息构造辅助函数
"""
from typing import Dict, List, Union


TEXT_ONLY_ANALYSIS_NOTE = (
    "补充说明：本次未提供商品图片，请仅根据商品文字字段和卖家信息判断，不要推断图片内容。"
)


def build_analysis_text_prompt(
    product_json: str,
    prompt_text: str,
    *,
    include_images: bool,
) -> str:
    note = "" if include_images else f"\n{TEXT_ONLY_ANALYSIS_NOTE}\n"
    value_note = (
        "\n【价格参考的使用规则（硬性）】\n"
        "1) 只有当 price_insight.market_scope 为 model 或 family 时，才代表「同型号可比较」，"
        "此时可以引用 market_median_price 作为同型号中位价。\n"
        "2) market_scope 为 insufficient、或没有该字段时，视为「同型号样本不足」，"
        "禁止使用『远低于市场均价』这类表述，只能写『同型号样本不足，无法比价』。\n"
        "3) 严禁跨型号比价：不同型号、不同显存容量的均价不能拿来评价本商品，"
        "例如不能用『显卡』全类均价去评价一块专业卡或多屏卡。\n"
        "4) price_insight 里的 market_avg_price / 当前搜索样本 的平均值可能混入了其他型号，"
        "只能作为背景参考，不得作为本商品『便宜』的证据。\n"
        "\n【底层硬门槛（不可推翻）】\n"
        "程序会用客观事实（卡型是否为消费级、显存容量、功能故障、矿卡/维修痕迹、"
        "预算区间、物流方式）做一票否决。你的 is_recommended 不能推翻这些结论；"
        "如果商品已经命中其中的硬性条件，请直接给出 is_recommended=false 并在 reason 里说明。\n"
        "\n如需综合性价比，可另外输出可选字段 value_score(0-100) 和 value_summary，"
        "但必须保留原有 is_recommended/reason 等字段。\n"
    )
    output_schema_note = (
        "\n【输出字段硬性要求】最终 JSON 顶层必须包含且仅包含以下字段："
        "prompt_version(字符串，可填 \"EagleEye-V6.4\")、is_recommended(布尔值)、"
        "reason(字符串)、risk_tags(字符串数组)、criteria_analysis(非空对象，且必须含 seller_type 键)。"
        "缺少任一字段即视为格式错误，请不要省略。\n"
    )
    return f"""请基于你的专业知识和我的要求，分析以下完整的商品JSON数据：

```json
{product_json}
```

    {prompt_text}
    {value_note}
    {output_schema_note}
    {note}"""


def build_user_message_content(
    text_prompt: str,
    image_data_urls: List[str],
) -> Union[str, List[Dict[str, object]]]:
    if not image_data_urls:
        return text_prompt

    user_content: List[Dict[str, object]] = [
        {"type": "image_url", "image_url": {"url": url}}
        for url in image_data_urls
    ]
    user_content.append({"type": "text", "text": text_prompt})
    return user_content
