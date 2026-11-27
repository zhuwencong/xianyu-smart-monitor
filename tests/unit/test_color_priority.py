"""配色偏好排序的回归测试。

背景：X9s Pro 的橙色（元气橙/活力橙）是买家首选配色，但二手市场占比只有约 3%，
按纯 ai_score 排序会被大量其他配色压到后面。这里锁定两个行为：
1. 配色识别要准（橙色 / 其他 / 未标注）
2. 排序时橙色靠前，但同配色内仍按 ai_score 排，且不改动 ai_score 本身
"""
import pytest

from src.services.workbench_service import (
    ORANGE_COLOR_TOKENS,
    detect_color,
    list_candidates,
)


def test_detect_orange_colors():
    """橙色系的几种常见写法都要识别出来。"""
    for title in (
        "OPPO Find X9s Pro 16+512G 活力橙",
        "X9s Pro 元气橙 16+512 国行",
        "OPPO X9s Pro 橙色 16+512",
        "oppo find x9s pro orange 512",
        "X9s Pro 橘色 512G",
    ):
        assert detect_color(title) == "orange", f"未识别为橙色: {title}"


def test_detect_other_colors():
    """其他三色不能被误判成橙色。"""
    for title in (
        "OPPO X9s Pro 自在白 16+512",
        "OPPO X9s Pro 乘风青 16+512",
        "X9s Pro 原生钛 16+512",
        "X9s Pro 钛色 512G",
    ):
        assert detect_color(title) == "other", f"误判: {title}"


def test_detect_unknown_color():
    """没写配色的返回 unknown，不能猜。"""
    for title in (
        "OPPO X9s Pro 16+512 国行 99新",
        "X9s Pro 16+512G 全原无拆",
        "",
        None,
    ):
        assert detect_color(title) == "unknown"


def test_color_grading_slang_not_treated_as_orange():
    """「自定义垃圾橙色」是描述成色的黑话，不是配色。

    真实案例：标题写「自在白 ... 自定义垃圾橙色」，实际是白色机器，
    早期版本把它误判成橙色并顶到了榜首。
    """
    title = (
        "OPPO Find X9s Pro 16+512 自在白 月初激活，备用了两天，"
        "图片实拍可看，避免纠纷自定义垃圾橙色，洁癖病人不要拍。"
    )
    assert detect_color(title) == "other", "成色黑话被误判成橙色配色"


def test_orange_still_wins_when_no_other_color_named():
    """只说橙色、没提其他配色时，仍应识别为橙色。"""
    for title in (
        "OPPO X9s Pro 16+512 橙色 国行",
        "X9s Pro 元气橙 512G",
        "OPPO Find X9s Pro 16+512G 活力橙 全新",
    ):
        assert detect_color(title) == "orange", f"应识别为橙色: {title}"


def test_orange_tokens_cover_official_name():
    """官方名「元气橙」必须在词表里 —— 这是买家指定的首选色。"""
    assert "元气橙" in ORANGE_COLOR_TOKENS


# --- 排序行为 ---

class _FakeTask:
    id = 8
    task_name = "OPPO Find X9s Pro 16+512"
    keyword = "OPPO Find X9s Pro 512"


def _row(item_id: str, title: str, score: int, recommended: bool = False, status: str = "PASS"):
    """构造一条足够 list_candidates 处理的候选行。

    注意：ai_score 不是直接读这个 score 参数 —— 系统会用 criteria_analysis
    里的 status 重新计算。所以这里必须填齐 status，才能得到预期的分数档位。
    """
    import json

    def dim():
        return {"status": status, "comment": "测试", "evidence": "测试"}

    raw = {
        "商品信息": {"商品ID": item_id, "商品标题": title, "当前售价": "3800"},
        "ai_analysis": {
            "is_recommended": recommended,
            "reason": "测试",
            "risk_tags": [],
            "criteria_analysis": {
                "model_chip": dim(),
                "battery_health": dim(),
                "condition": dim(),
                "history": dim(),
                "seller_credit": dim(),
                "shipping": dim(),
                "seller_type": {"status": status, "persona": "个人", "comment": "测试", "analysis_details": {}},
            },
        },
    }
    return {
        "id": int(item_id),
        "item_id": item_id,
        "title": title,
        "price": 3800.0,
        "price_display": "¥3800",
        "link": f"https://www.goofish.com/item?id={item_id}",
        "publish_time": "2026-11-22T12:00:00+08:00",
        "seller_nickname": "seller",
        "task_name": _FakeTask.task_name,
        "keyword": _FakeTask.keyword,
        "result_filename": "x.jsonl",
        "crawl_time": "2026-11-23T00:00:00+08:00",
        "analysis_source": "ai",
        "review_status": "unseen",
        "ai_score": score,
        "raw_json": json.dumps(raw, ensure_ascii=False),
    }


def test_orange_ranks_before_higher_scored_other_color(monkeypatch):
    """橙色的分可以更低，但仍要排在更高质量的其他配色前面。"""
    rows = [
        _row("1", "OPPO X9s Pro 自在白 16+512", 90),
        _row("2", "OPPO X9s Pro 元气橙 16+512", 70),
    ]
    monkeypatch.setattr(
        "src.services.workbench_service._load_candidate_rows", lambda tasks: rows
    )
    monkeypatch.setattr(
        "src.services.workbench_service._resolve_task_for_row", lambda row, a, b: _FakeTask()
    )

    result = list_candidates([_FakeTask()], sort="score", limit=10)
    titles = [item["title"] for item in result["items"]]

    assert "元气橙" in titles[0], f"橙色应排第一，实际顺序: {titles}"


def test_score_unchanged_by_color_priority(monkeypatch):
    """配色优先只影响排序，不能把颜色折进 ai_score。

    同一件商品，无论标题写成橙色还是白色，算出来的 ai_score 必须一样 ——
    否则「颜色」就变成了评分维度，那正是需要避免的事。
    """
    def build(title):
        rows = [_row("3", title, 70)]
        monkeypatch.setattr(
            "src.services.workbench_service._load_candidate_rows", lambda tasks: rows
        )
        monkeypatch.setattr(
            "src.services.workbench_service._resolve_task_for_row",
            lambda row, a, b: _FakeTask(),
        )
        return list_candidates([_FakeTask()], sort="score", limit=10)["items"][0]

    orange = build("OPPO X9s Pro 元气橙 16+512")
    white = build("OPPO X9s Pro 自在白 16+512")

    assert orange["ai_score"] == white["ai_score"], (
        f"配色影响了评分: 橙色 {orange['ai_score']} vs 白色 {white['ai_score']}"
    )


# --- 非橙色推荐门槛 ---
#
# 买家原话：「其他版本暂时不用特别关注，除非评分很高」。
# 这条必须由程序强制，因为实测 AI 完全无视 prompt 里的配色规则 ——
# 30 条推荐里 28 条是非橙色，reason 里连「【非橙色】」标记都没有。
#
# 门槛取值：实测 60 个候选最高 83 分、中位 78。上一版写 85 分，
# 但 85 需要所有维度全 PASS 且价格低于基准 15% 才可能出现，
# 真实数据里从未达到 —— 那条规则等于没写。现取 82。

from src.services.workbench_service import (  # noqa: E402
    OTHER_COLOR_MIN_SCORE,
    _apply_color_gate,
)


def _cand(title, score, recommended=True):
    return {"title": title, "ai_score": score, "recommended": recommended}


def test_other_color_below_threshold_is_demoted():
    """非橙色且分数不到门槛，即使 AI 说推荐也要撤掉。

    真实案例：¥3899 的「自在白」被 AI 判 is_recommended=true，
    但配色非首选、分数只有 78 —— 按买家要求不该特别关注。
    """
    assert _apply_color_gate(_cand("OPPO X9s Pro 自在白 16+512", 78)) is False


def test_other_color_above_threshold_kept():
    """非橙色但分数够高，仍应推荐 —— 这就是「除非评分很高」。"""
    assert _apply_color_gate(_cand("OPPO X9s Pro 原生钛 16+512", 83)) is True


def test_orange_has_no_threshold():
    """橙色是首选配色，低分也照样推荐 —— 不受门槛限制。"""
    assert _apply_color_gate(_cand("OPPO X9s Pro 元气橙 16+512", 70)) is True


def test_not_recommended_stays_rejected():
    """AI 本来就说不推荐的，门槛不能把它翻成推荐。"""
    assert _apply_color_gate(_cand("OPPO X9s Pro 元气橙 16+512", 90, recommended=False)) is False


def test_no_score_passes_through():
    """还没算分的（新抓的）不能一律压掉，否则会漏掉真橙色。"""
    assert _apply_color_gate(_cand("OPPO X9s Pro 元气橙 16+512", None)) is True
    assert _apply_color_gate(_cand("OPPO X9s Pro 自在白 16+512", None)) is True


def test_gate_does_not_touch_score():
    """门槛只改 recommended，绝不能改 ai_score。

    分数是机器质量的度量；若因为配色去改分数，
    「这台机器好不好」和「我喜不喜欢这个颜色」就再也分不开了。
    """
    cand = _cand("OPPO X9s Pro 自在白 16+512", 78)
    _apply_color_gate(cand)
    assert cand["ai_score"] == 78, "配色门槛篡改了 ai_score"


def test_gate_threshold_is_reachable():
    """门槛必须落在真实分数区间内。

    历史 bug：门槛设 85，而真实数据最高只有 83，规则永远不触发。
    """
    assert OTHER_COLOR_MIN_SCORE <= 83, (
        f"门槛 {OTHER_COLOR_MIN_SCORE} 高于实测最高分 83，规则会失效"
    )
    assert OTHER_COLOR_MIN_SCORE > 78, "门槛应高于中位分 78，否则等于不筛"
