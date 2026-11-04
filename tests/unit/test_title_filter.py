from src.services.title_filter import build_title_filter


def test_empty_filter_keeps_everything():
    title_filter = build_title_filter(None, None)
    assert title_filter.is_empty is True
    assert title_filter.check("任意标题") == (True, "")


def test_include_ignores_case_and_whitespace():
    title_filter = build_title_filter(["GTX 1070"], None)
    assert title_filter.check("自用 gtx1070 8g 显卡")[0] is True
    assert title_filter.check("技嘉 GTX 1070 8G")[0] is True
    keep, reason = title_filter.check("影驰GTX1060 6G")
    assert keep is False
    assert "必含词" in reason


def test_include_is_or_semantics():
    title_filter = build_title_filter(["512", "1t"], None)
    assert title_filter.check("真我GT8Pro 16+512")[0] is True
    assert title_filter.check("真我GT8Pro 1TB")[0] is True
    assert title_filter.check("真我GT8Pro 12+256")[0] is False


def test_exclude_wins_over_include():
    title_filter = build_title_filter(["1070"], ["1070ti"])
    assert title_filter.check("GTX1070 8G 自用")[0] is True
    keep, reason = title_filter.check("GTX1070Ti 8G 自用")
    assert keep is False
    assert "排除词" in reason


def test_string_terms_are_split_on_comma_and_newline():
    title_filter = build_title_filter("1070, 8G\n自用", None)
    assert title_filter.include == ("1070", "8g", "自用")


def test_chinese_comma_is_supported():
    title_filter = build_title_filter("1070，矿卡", None)
    assert title_filter.include == ("1070", "矿卡")
