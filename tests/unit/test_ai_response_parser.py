import pytest

from src.services.ai_response_parser import (
    extract_ai_response_content,
    parse_ai_response_json,
    EmptyAIResponseError,
)


def test_parse_ai_response_json_uses_first_object_when_multiple_json_objects_are_concatenated():
    content = """```json
{"is_recommended": true, "reason": "first"}
{"is_recommended": false, "reason": "second"}
```"""

    result = parse_ai_response_json(content)

    assert result == {"is_recommended": True, "reason": "first"}


def test_parse_ai_response_json_extracts_json_from_wrapped_text():
    content = """分析结果如下：

```json
{"is_recommended": true, "reason": "wrapped"}
```

请按第一份结果处理。"""

    result = parse_ai_response_json(content)

    assert result == {"is_recommended": True, "reason": "wrapped"}


def test_parse_ai_response_json_raises_when_no_json_exists():
    with pytest.raises(ValueError):
        parse_ai_response_json("没有任何 JSON 内容")


def test_extract_ai_response_content_with_none_content_but_valid_reasoning_content():
    """当 content 为 None 但 reasoning_content 有值时，应该成功提取 reasoning_content 的内容"""
    # 创建 mock 对象模拟 OpenAI 风格的响应
    message = type('Message', (), {
        'content': None,
        'reasoning_content': '这是推理内容'
    })()
    choice = type('Choice', (), {'message': message})()
    response = type('Response', (), {'choices': [choice]})()

    result = extract_ai_response_content(response)

    assert result == '这是推理内容'


def test_extract_ai_response_content_raises_when_content_and_reasoning_content_are_empty():
    """当 content 和 reasoning_content 都为空时，应该抛出 EmptyAIResponseError"""
    # 创建 mock 对象
    message = type('Message', (), {
        'content': None,
        'reasoning_content': None
    })()
    choice = type('Choice', (), {'message': message})()
    response = type('Response', (), {'choices': [choice]})()

    with pytest.raises(EmptyAIResponseError):
        extract_ai_response_content(response)


def test_parse_ai_response_json_pulls_shipping_and_credit_out_of_seller_type():
    """模型会把 shipping / seller_credit 误嵌进 seller_type，解析时应提回顶层。

    实测 deepseek-flash 输出显卡分析时约六成响应如此。JSON 合法，
    所以只有字段层面的校验才能发现，必须在解析阶段纠正。
    """
    content = """{
      "prompt_version": "EagleEye-V6.4",
      "is_recommended": false,
      "reason": "证据不足",
      "risk_tags": ["无GPU-Z"],
      "criteria_analysis": {
        "model_chip": {"status": "PASS", "comment": "", "evidence": ""},
        "battery_health": {"status": "NOT_APPLICABLE", "comment": "显卡无电池", "evidence": "-"},
        "condition": {"status": "PASS", "comment": "", "evidence": ""},
        "history": {"status": "SUSPECT", "comment": "", "evidence": ""},
        "seller_type": {
          "status": "FAIL",
          "persona": "商家",
          "comment": "",
          "analysis_details": {
            "temporal_analysis": {"comment": "", "evidence": ""},
            "selling_behavior": {"comment": "", "evidence": ""},
            "buying_behavior": {"comment": "", "evidence": ""},
            "behavioral_summary": {"comment": "", "evidence": ""}
          },
          "shipping": {"status": "UNKNOWN", "comment": "", "evidence": ""},
          "seller_credit": {"status": "UNKNOWN", "comment": "", "evidence": ""}
        }
      }
    }"""

    analysis = parse_ai_response_json(content)["criteria_analysis"]

    assert analysis["shipping"]["status"] == "UNKNOWN"
    assert analysis["seller_credit"]["status"] == "UNKNOWN"
    # 搬移后不应残留在 seller_type 里
    assert "shipping" not in analysis["seller_type"]
    assert "seller_credit" not in analysis["seller_type"]
    # analysis_details 必须原样保留
    assert "behavioral_summary" in analysis["seller_type"]["analysis_details"]


def test_parse_ai_response_json_keeps_flat_schema_untouched():
    """字段本来就平铺时，归一化不应改动任何结构。"""
    content = """{
      "is_recommended": true,
      "reason": "ok",
      "risk_tags": [],
      "criteria_analysis": {
        "seller_type": {"status": "PASS", "persona": "个人", "comment": ""},
        "shipping": {"status": "PASS", "comment": "", "evidence": ""},
        "seller_credit": {"status": "PASS", "comment": "", "evidence": ""}
      }
    }"""

    analysis = parse_ai_response_json(content)["criteria_analysis"]

    assert analysis["shipping"]["status"] == "PASS"
    assert analysis["seller_credit"]["status"] == "PASS"
    assert list(analysis["seller_type"].keys()) == ["status", "persona", "comment"]
