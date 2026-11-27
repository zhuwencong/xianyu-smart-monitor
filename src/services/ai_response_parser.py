"""
AI 响应解析工具
"""
import json
from typing import Any


class EmptyAIResponseError(ValueError):
    """AI 返回了空内容。"""


def extract_ai_response_content(response: Any) -> str:
    """从不同形态的 AI 响应中提取文本内容。"""
    if response is None:
        raise EmptyAIResponseError("AI响应对象为空。")

    if isinstance(response, (bytes, bytearray)):
        text = response.decode("utf-8", errors="replace")
        return _normalize_text_content(text)

    if isinstance(response, str):
        return _normalize_text_content(response)

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str):
        return _normalize_text_content(output_text)

    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        if message is None:
            raise EmptyAIResponseError("AI响应缺少 message。")
        content = getattr(message, "content", None)
        
        # 智谱等 OpenAI 兼容网关在某些模式下会把输出放在 reasoning_content 而非 content
        try:
            return _normalize_text_content(_coerce_content_parts(content))
        except EmptyAIResponseError:
            reasoning_content = getattr(message, "reasoning_content", None)
            if reasoning_content:
                return _normalize_text_content(_coerce_content_parts(reasoning_content))
            raise

    raise ValueError(f"无法识别的AI响应类型: {type(response).__name__}")


def _repair_truncated_json(text: str):
    """模型偶尔会在 JSON 末尾被截断（少收尾引号/花括号）。
    这里按未闭合的字符串与括号数量补齐后再试一次解析，
    避免整批商品被误判为「AI响应格式错误」。"""
    if not text.startswith("{"):
        return None
    in_string = False
    escaped = False
    braces = 0
    brackets = 0
    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            if in_string:
                escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            braces += 1
        elif ch == "}":
            braces -= 1
        elif ch == "[":
            brackets += 1
        elif ch == "]":
            brackets -= 1
    if braces <= 0 and brackets <= 0 and not in_string:
        return None
    fixed = text
    if in_string:
        fixed += '"'
    fixed += "]" * max(brackets, 0) + "}" * max(braces, 0)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        # 截断在键名或冒号后时，退一步：截到最后一个完整的 , 或 { 再补齐
        for cut in range(len(text) - 1, 0, -1):
            if text[cut] in ',{':
                candidate = text[:cut] + "}" * 1
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        return None


def parse_ai_response_json(content: str) -> dict:
    """解析 AI 文本响应中的 JSON。"""
    cleaned = _strip_code_fences(content)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        repaired = _repair_truncated_json(cleaned)
        if isinstance(repaired, dict):
            return normalize_analysis_schema(repaired)
        return normalize_analysis_schema(_extract_first_json_value(cleaned, exc))
    return normalize_analysis_schema(parsed)


# criteria_analysis 下应当平铺的字段。模型在长嵌套结构里
# （seller_type 内部有 4 层 analysis_details）经常把尾部字段误挂进
# seller_type，导致 shipping / seller_credit 在读取侧"消失"。
_FLAT_ANALYSIS_KEYS = (
    "model_chip",
    "battery_health",
    "condition",
    "history",
    "seller_type",
    "shipping",
    "seller_credit",
)


def normalize_analysis_schema(parsed: Any) -> Any:
    """把模型可能错位嵌套的分析字段提回 criteria_analysis 顶层。

    实测（deepseek-flash + 显卡判据）：约 6 成响应会把 shipping 与
    seller_credit 塞进 criteria_analysis.seller_type 里。JSON 本身合法，
    所以只看 json.loads 是否成功发现不了问题，字段却整段丢失。
    这里做一次幂等纠正：只在目标键缺失、且来源键存在时才搬移。
    """
    if not isinstance(parsed, dict):
        return parsed

    analysis = parsed.get("criteria_analysis")
    if not isinstance(analysis, dict):
        return parsed

    seller_type = analysis.get("seller_type")
    nested_source = seller_type if isinstance(seller_type, dict) else {}

    for key in _FLAT_ANALYSIS_KEYS:
        if key in analysis or key == "seller_type":
            continue
        if key in nested_source:
            analysis[key] = nested_source.pop(key)

    return parsed


def _coerce_content_parts(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (bytes, bytearray)):
        return content.decode("utf-8", errors="replace")
    if not isinstance(content, list):
        raise ValueError(f"AI响应内容类型不受支持: {type(content).__name__}")

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
            continue
        text = getattr(item, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _normalize_text_content(content: str) -> str:
    text = str(content).strip()
    if not text:
        raise EmptyAIResponseError("AI响应内容为空。")
    return text


def _strip_code_fences(content: str) -> str:
    cleaned = content.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _extract_first_json_value(
    content: str,
    fallback_error: json.JSONDecodeError,
):
    decoder = json.JSONDecoder()
    last_error: json.JSONDecodeError | None = None

    for start_index, char in enumerate(content):
        if char not in "{[":
            continue
        try:
            parsed, _ = decoder.raw_decode(content[start_index:])
            return parsed
        except json.JSONDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise fallback_error
