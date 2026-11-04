"""标题级本地预筛。

搜索结果里经常混入大量与目标无关的商品（例如搜 GTX 1070 却返回 1060、
搜 512G 手机却返回 256G）。这些商品在进入详情页、卖家主页、图片下载和
AI 分析之前就可以用标题排除掉：

- 详情页是闲鱼风控的主要触发点，少开一次就少一分风险；
- 每个商品的 AI 分析要带上多张图片，token 成本不低；
- 单轮运行有时间上限，把时间留给真正匹配的商品。

规则保持简单、可解释：
- ``include`` 非空时，标题必须命中其中任意一个词（OR）；
- ``exclude`` 命中任意一个词即丢弃（优先级高于 include）；
- 匹配时忽略大小写与所有空白，避免 "GTX 1070" / "gtx1070" 的写法差异。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(text) -> str:
    """去掉空白并转小写，用于宽松匹配。"""
    return _WHITESPACE_RE.sub("", str(text or "")).lower()


def normalize_terms(terms: Iterable | None) -> tuple[str, ...]:
    """把任务配置里的词列表规范化为去空、去重、小写、去空白的元组。"""
    if terms is None:
        return ()
    if isinstance(terms, str):
        raw = re.split(r"[\n,，]+", terms)
    elif isinstance(terms, (list, tuple, set)):
        raw = list(terms)
    else:
        raw = [terms]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = _WHITESPACE_RE.sub("", str(item or "")).lower()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


@dataclass(frozen=True)
class TitleFilter:
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.include and not self.exclude

    def check(self, title) -> tuple[bool, str]:
        """返回 (是否保留, 原因)。原因为空表示通过。"""
        text = normalize_title(title)
        if not text:
            return True, ""
        for term in self.exclude:
            if term in text:
                return False, f"命中排除词「{term}」"
        if self.include and not any(term in text for term in self.include):
            return False, "未命中必含词「" + "/".join(self.include) + "」"
        return True, ""


def build_title_filter(
    include: Sequence[str] | str | None,
    exclude: Sequence[str] | str | None,
) -> TitleFilter:
    return TitleFilter(include=normalize_terms(include), exclude=normalize_terms(exclude))
