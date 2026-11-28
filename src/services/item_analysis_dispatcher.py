"""
商品分析分发器
将卖家资料采集、图片下载、AI 分析和结果保存移出主抓取链路。
"""
import asyncio
import copy
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from src.domain.scoring import (
    evaluate_candidate,
    evaluate_gates,
    extract_specs,
    push_min_score,
    resolve_verdict,
    task_allows_professional,
)
from src.domain.scoring.perf import performance_score, value_score
from src.domain.scoring.specs import looks_like_gpu_task
from src.keyword_rule_engine import build_search_text, evaluate_keyword_rules


SellerLoader = Callable[[str], Awaitable[dict]]
ImageDownloader = Callable[[str, list[str], str], Awaitable[list[str]]]
AIAnalyzer = Callable[[dict, list[str], str], Awaitable[Optional[dict]]]
Notifier = Callable[[dict, str], Awaitable[None]]
Saver = Callable[[dict, str], Awaitable[bool]]


@dataclass(frozen=True)
class ItemAnalysisJob:
    keyword: str
    task_name: str
    decision_mode: str
    analyze_images: bool
    prompt_text: str
    keyword_rules: tuple[str, ...]
    final_record: dict
    seller_id: Optional[str]
    zhima_credit_text: Optional[str]
    registration_duration_text: str
    budget_min: Optional[str] = None
    budget_max: Optional[str] = None
    require_shipping: bool = False


def _env_push_min_score() -> int:
    """推送最低分，与面板展示共用 engine.push_min_score。"""
    return push_min_score()


class ItemAnalysisDispatcher:
    """用受控并发处理商品分析和落盘。"""

    def __init__(
        self,
        *,
        concurrency: int,
        skip_ai_analysis: bool,
        seller_loader: SellerLoader,
        image_downloader: ImageDownloader,
        ai_analyzer: AIAnalyzer,
        notifier: Notifier,
        saver: Saver,
        min_push_score: int | None = None,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._skip_ai_analysis = skip_ai_analysis
        self._min_push_score = min_push_score if min_push_score is not None else _env_push_min_score()
        self._seller_loader = seller_loader
        self._image_downloader = image_downloader
        self._ai_analyzer = ai_analyzer
        self._notifier = notifier
        self._saver = saver
        self._tasks: set[asyncio.Task] = set()
        self.completed_count = 0

    def submit(self, job: ItemAnalysisJob) -> None:
        task = asyncio.create_task(self._process_with_limit(job))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def join(self) -> None:
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks))

    async def _process_with_limit(self, job: ItemAnalysisJob) -> None:
        async with self._semaphore:
            await self._process_job(job)

    async def _process_job(self, job: ItemAnalysisJob) -> None:
        record = copy.deepcopy(job.final_record)
        item_data = record.get("商品信息", {}) or {}
        record["卖家信息"] = await self._load_seller_info(job)
        analysis = self._apply_hard_gates(
            job,
            record,
            await self._build_analysis_result(job, record),
        )
        # 分数在分析阶段就定下来：推送门槛和面板排序必须用同一个数，
        # 否则会出现「推送了但面板显示低分」这种自相矛盾。
        self._attach_score(job, record, analysis)
        record["ai_analysis"] = analysis
        if await self._saver(record, job.keyword):
            self.completed_count += 1
        await self._notify_if_recommended(item_data, analysis)

    def _attach_score(self, job: ItemAnalysisJob, record: dict, analysis: dict) -> None:
        """把五维评分写进 ai_analysis，供存储、推送、面板三处共用。"""
        if not isinstance(analysis, dict) or analysis.get("error"):
            return
        # 关键词规则模式 / 跳过 AI 模式没有 criteria，不该被评分门槛拦下。
        if str(analysis.get("analysis_source") or "") == "keyword" or analysis.get("skip_scoring"):
            return
        item = record.get("商品信息", {}) or {}
        seller = record.get("卖家信息", {}) or {}
        try:
            price = float(str(item.get("当前售价") or "").replace("¥", "").strip())
        except (TypeError, ValueError):
            price = None
        title = str(item.get("商品标题") or "")
        description = str(item.get("商品描述") or "")
        specs = extract_specs(
            title,
            description,
            gpu_hint=looks_like_gpu_task(job.keyword, job.task_name, title),
        )
        gates = evaluate_gates(
            specs=specs,
            price=price,
            budget_min=job.budget_min,
            budget_max=job.budget_max,
            require_shipping=job.require_shipping,
            allow_professional=task_allows_professional(job.keyword),
            seller_credit=str(seller.get("卖家信用等级") or ""),
        )
        raw_criteria = analysis.get("criteria_analysis") or {}
        status_by_key = {
            str(key): str(value.get("status") or "NEEDS_MANUAL_CHECK").upper()
            for key, value in raw_criteria.items()
            if isinstance(value, dict)
        }
        verdict = resolve_verdict(
            analysis_failed=False,
            ai_recommended=analysis.get("is_recommended") is True,
            criteria=[{"status": status} for status in status_by_key.values()],
            risk_tags=analysis.get("risk_tags") or [],
            gates=gates,
        )
        result = evaluate_candidate(
            analysis=analysis,
            status_by_key=status_by_key,
            price=price,
            insight=record.get("price_insight") or {},
            verdict=verdict,
            gates=gates,
            performance=performance_score(specs),
            value=value_score(price, specs),
        )
        analysis.update(
            {
                "score_total": result["score"],
                "score_grade": result["grade"],
                "score_caps": result["caps"],
                "score_dims": result["breakdown"],
                "score_ratio": result["bargain_ratio"],
                "score_gap": result["price_gap"],
                "score_gap_scope": result["price_gap_scope"],
            }
        )

    def _apply_hard_gates(
        self,
        job: ItemAnalysisJob,
        record: dict,
        analysis: dict,
    ) -> dict:
        """把底层硬门槛盖在 AI 结论上：模型说能买，也得先过客观事实这一关。"""
        if not isinstance(analysis, dict) or analysis.get("error"):
            return analysis
        if str(analysis.get("analysis_source") or "") == "keyword":
            return analysis

        item = record.get("商品信息", {}) or {}
        seller = record.get("卖家信息", {}) or {}
        try:
            price = float(str(item.get("当前售价") or "").replace("¥", "").strip())
        except (TypeError, ValueError):
            price = None

        gates = evaluate_gates(
            specs=extract_specs(
                item.get("商品标题"),
                item.get("商品描述"),
                gpu_hint=looks_like_gpu_task(job.keyword, job.task_name),
            ),
            price=price,
            budget_min=job.budget_min,
            budget_max=job.budget_max,
            require_shipping=job.require_shipping,
            allow_professional=task_allows_professional(job.keyword),
            seller_credit=str(seller.get("卖家信用等级") or ""),
        )
        analysis["hard_gates"] = gates.as_list()
        if not gates.blocked:
            return analysis

        analysis["is_recommended"] = False
        analysis["hard_blocked"] = True
        labels = "、".join(hit.label for hit in gates.blocks)
        original_reason = str(analysis.get("reason") or "").strip()
        analysis["reason"] = f"[硬门槛否决]{labels}。" + original_reason
        risk_tags = list(analysis.get("risk_tags") or [])
        for hit in gates.blocks:
            if hit.label not in risk_tags:
                risk_tags.append(hit.label)
        analysis["risk_tags"] = risk_tags
        return analysis

    async def _load_seller_info(self, job: ItemAnalysisJob) -> dict:
        seller_info = {}
        if job.seller_id:
            try:
                seller_info = await self._seller_loader(job.seller_id)
            except Exception as exc:
                print(f"   [卖家] 采集卖家 {job.seller_id} 信息失败: {exc}")
        merged = copy.deepcopy(seller_info or {})
        merged["卖家芝麻信用"] = job.zhima_credit_text
        merged["卖家注册时长"] = job.registration_duration_text
        return merged

    async def _build_analysis_result(self, job: ItemAnalysisJob, record: dict) -> dict:
        if job.decision_mode == "keyword":
            return self._build_keyword_result(job, record)
        if self._skip_ai_analysis:
            return self._build_skip_ai_result()
        return await self._run_ai_analysis(job, record)

    def _build_keyword_result(self, job: ItemAnalysisJob, record: dict) -> dict:
        search_text = build_search_text(record)
        return evaluate_keyword_rules(list(job.keyword_rules), search_text)

    def _build_skip_ai_result(self) -> dict:
        return {
            "analysis_source": "ai",
            "is_recommended": True,
            "reason": "商品已跳过AI分析，直接通知",
            "keyword_hit_count": 0,
            # 没有经过 AI 判据，也就没有可信分数，不参与推送分数门槛。
            "skip_scoring": True,
        }

    def _build_ai_error_result(self, reason: str, *, error: str = "") -> dict:
        payload = {
            "analysis_source": "ai",
            "is_recommended": False,
            "reason": reason,
            "keyword_hit_count": 0,
            # 标记「没分析成」而不是「分析完了判定不要」，存储层据此决定是否下一轮重试。
            "analysis_error": True,
        }
        if error:
            payload["error"] = error
        return payload

    async def _run_ai_analysis(self, job: ItemAnalysisJob, record: dict) -> dict:
        image_paths: list[str] = []
        try:
            image_paths = await self._download_images(job, record)
            if not job.prompt_text:
                return self._build_ai_error_result("任务未配置AI prompt，跳过分析。")
            ai_result = await self._ai_analyzer(record, image_paths, job.prompt_text)
            if not ai_result:
                return self._build_ai_error_result(
                    "AI analysis returned None after retries.",
                    error="AI analysis returned None after retries.",
                )
            ai_result.setdefault("analysis_source", "ai")
            ai_result.setdefault("keyword_hit_count", 0)
            return ai_result
        except Exception as exc:
            return self._build_ai_error_result(
                f"AI分析异常: {exc}",
                error=str(exc),
            )
        finally:
            self._cleanup_images(image_paths)

    async def _download_images(self, job: ItemAnalysisJob, record: dict) -> list[str]:
        if not job.analyze_images:
            return []
        item_data = record.get("商品信息", {}) or {}
        image_urls = item_data.get("商品图片列表", [])
        if not image_urls:
            return []
        return await self._image_downloader(
            item_data["商品ID"],
            image_urls,
            job.task_name,
        )

    def _cleanup_images(self, image_paths: list[str]) -> None:
        for img_path in image_paths:
            try:
                if os.path.exists(img_path):
                    os.remove(img_path)
            except Exception as exc:
                print(f"   [图片] 删除图片文件时出错: {exc}")

    async def _notify_if_recommended(self, item_data: dict, analysis_result: dict) -> None:
        if not analysis_result.get("is_recommended"):
            return
        # 分数门槛：AI 说「可以关注」还不够，得真的够便宜、够可信才值得打扰人。
        score = analysis_result.get("score_total")
        try:
            score = int(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        if score is not None and score < self._min_push_score:
            return
        reason = str(analysis_result.get("reason") or "无")
        if score is not None:
            grade = analysis_result.get("score_grade") or ""
            reason = f"[{grade}级 {score}分] {reason}"
        try:
            await self._notifier(item_data, reason)
        except Exception as exc:
            print(f"   [通知] 发送推荐通知失败: {exc}")
