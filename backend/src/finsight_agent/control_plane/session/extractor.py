from __future__ import annotations

import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from finsight_agent.control_plane.orchestrator.models import OrchestrationResult
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.report_block import EvidenceOverviewBlock
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import ConversationTurn, SessionContext

from .compressor import build_history_summary

_COMPANY_PATTERN = re.compile(r"(宁德时代|贵州茅台|比亚迪|中远海能|招商轮船|中国船舶)")

# 短期记忆保留的最大轮次（更早的进 history_summary）
_MAX_TURNS = 3


class SessionContextExtractor:
    """从结构化执行产物中提取 SessionContext（v2 支持多轮记忆）。"""

    def extract(
        self,
        *,
        request: AnalysisRequest,
        router_result: RouterResult,
        orchestration_result: OrchestrationResult,
        previous_context: SessionContext | None = None,
    ) -> SessionContext:
        # 构造本轮 ConversationTurn
        current_turn = self._build_current_turn(
            request=request,
            router_result=router_result,
            orchestration_result=orchestration_result,
        )

        # 计算新的 turns 列表（最近 3 轮）
        previous_turns = list(previous_context.turns) if previous_context else []
        new_turns = previous_turns + [current_turn]
        # 超过 3 轮时，最早的会被 summarizer 压缩（由 SessionService 触发）
        # 这里只做截断，summarize 由上层 service 统一处理
        new_turns = new_turns[-_MAX_TURNS:]

        # 活跃上下文：本轮 entities 覆盖上一轮；本轮为空时保留上一轮（支持指代消解）
        active_topic = self._build_active_topic(router_result, orchestration_result)
        active_candidates = self._build_active_candidates(
            router_result,
            orchestration_result,
            previous_context,
        )[:3]
        active_metrics = self._build_active_metrics(router_result, previous_context)
        active_time_scope = self._build_active_time_scope(router_result, previous_context)
        key_evidence_refs = self._build_key_evidence_refs(orchestration_result)[:5]
        available_follow_ups = self._build_available_follow_ups(
            active_candidates=active_candidates,
            key_evidence_refs=key_evidence_refs,
            intent=router_result.intent,
        )

        # history_summary 由 SessionService 调用 summarizer 更新，
        # extractor 这里沿用旧值（保持模板兜底兼容）
        history_summary = ""
        if previous_context is not None:
            history_summary = previous_context.history_summary
        else:
            history_summary = build_history_summary(
                intent=router_result.intent,
                active_topic=active_topic,
                active_candidates=active_candidates,
                has_evidence_refs=bool(key_evidence_refs),
                previous_summary="",
            )

        return SessionContext(
            version="v2",
            session_id=orchestration_result.session_id,
            active_topic=active_topic,
            active_candidates=active_candidates,
            key_evidence_refs=key_evidence_refs,
            history_summary=history_summary,
            available_follow_ups=available_follow_ups,
            active_metrics=active_metrics,
            active_time_scope=active_time_scope,
            turns=new_turns,
        )

    # ── ConversationTurn 构造 ──

    def _build_current_turn(
        self,
        *,
        request: AnalysisRequest,
        router_result: RouterResult,
        orchestration_result: OrchestrationResult,
    ) -> ConversationTurn:
        """构造本轮 ConversationTurn。"""
        response_summary = ""
        final_response = orchestration_result.final_response
        if final_response is not None and final_response.summary:
            response_summary = final_response.summary[:200]

        return ConversationTurn(
            turn_id=f"turn_{uuid.uuid4().hex[:8]}",
            query=request.query,
            query_mode=request.query_mode,
            intent=router_result.intent,
            response_summary=response_summary,
            entities_snapshot=self._extract_entities_snapshot(router_result),
            evidence_refs=self._build_key_evidence_refs(orchestration_result)[:5],
            created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        )

    def _extract_entities_snapshot(self, router_result: RouterResult) -> dict:
        """提取 router entities 的关键字段作为快照。"""
        entities = router_result.entities or {}
        return {
            "company_name": entities.get("company_name") or "",
            "company_standard_name": entities.get("company_standard_name") or "",
            "stock_code": entities.get("stock_code") or "",
            "metric_raw": entities.get("metric_raw") or "",
            "metric_standard_name": entities.get("metric_standard_name") or "",
            "metric_type": entities.get("metric_type") or "",
            "time_scope_raw": entities.get("time_scope_raw") or "",
            "period_end": entities.get("period_end") or "",
            "fiscal_year": entities.get("fiscal_year") or "",
        }

    # ── 活跃上下文构造（支持指代消解的回填逻辑）──

    def _build_active_topic(
        self,
        router_result: RouterResult,
        orchestration_result: OrchestrationResult,
    ) -> str:
        entities = router_result.entities
        if router_result.intent == "metric_lookup":
            company = str(entities.get("company_name") or "").strip()
            time_scope = str(entities.get("time_scope_raw") or "").strip()
            metric = str(entities.get("metric_raw") or "").strip()
            topic = " ".join(part for part in (company, time_scope, metric) if part)
            return topic.strip()

        if router_result.intent == "evidence_lookup":
            claim = str(entities.get("claim") or "").strip()
            if claim:
                return claim
            target = str(entities.get("target") or "").strip()
            if target:
                return target

        if router_result.intent == "event_impact_analysis":
            event = str(entities.get("event") or "").strip()
            themes = entities.get("themes") or []
            if isinstance(themes, list):
                theme_text = "、".join(str(item).strip() for item in themes if str(item).strip())
                if event and theme_text:
                    return f"{event} 对 {theme_text} 的影响"
            return event

        final_response = orchestration_result.final_response
        if final_response and final_response.summary:
            return final_response.summary.strip()
        return ""

    def _build_active_candidates(
        self,
        router_result: RouterResult,
        orchestration_result: OrchestrationResult,
        previous_context: SessionContext | None = None,
    ) -> list[str]:
        """构造活跃公司列表，本轮为空时回退到上一轮（支持指代消解）。"""
        candidates: list[str] = []
        target = str(router_result.entities.get("target") or "").strip()
        company = str(router_result.entities.get("company_name") or "").strip()

        if target:
            candidates.extend(self._extract_companies(target))
        if company:
            candidates.extend(self._extract_companies(company))

        final_response = orchestration_result.final_response
        if final_response is not None:
            for block in final_response.report_blocks:
                if block.get("block_type") != "evidence_overview":
                    continue
                typed_block = EvidenceOverviewBlock(**block)
                for item in typed_block["items"]:
                    company_name = str(item.get("company_name") or "").strip()
                    if company_name:
                        candidates.append(company_name)

        # 本轮未提取到公司时，回退到上一轮活跃公司（支持"它净利润多少"复用公司）
        if not candidates and previous_context is not None:
            return list(previous_context.active_candidates)

        return self._unique(candidates)

    def _build_active_metrics(
        self,
        router_result: RouterResult,
        previous_context: SessionContext | None = None,
    ) -> list[str]:
        """构造活跃指标列表，本轮为空时回退到上一轮。"""
        metric = str(
            router_result.entities.get("metric_standard_name") or ""
        ).strip()
        if metric:
            return [metric]
        if previous_context is not None and previous_context.active_metrics:
            return list(previous_context.active_metrics)
        return []

    def _build_active_time_scope(
        self,
        router_result: RouterResult,
        previous_context: SessionContext | None = None,
    ) -> dict:
        """构造活跃时间范围，本轮为空时回退到上一轮。"""
        period_end = str(router_result.entities.get("period_end") or "").strip()
        fiscal_year = router_result.entities.get("fiscal_year")
        if period_end or fiscal_year:
            return {
                "period_end": period_end,
                "fiscal_year": fiscal_year,
            }
        if previous_context is not None and previous_context.active_time_scope:
            return dict(previous_context.active_time_scope)
        return {}

    def _build_key_evidence_refs(
        self,
        orchestration_result: OrchestrationResult,
    ) -> list[str]:
        evidence_refs: list[str] = []

        for observation in orchestration_result.stage_observations:
            direct_refs = getattr(observation, "evidence_refs", None)
            if isinstance(direct_refs, list):
                for ref in direct_refs:
                    candidate = str(ref).strip()
                    if candidate:
                        evidence_refs.append(candidate)
            output_summary = getattr(observation, "output_summary", None)
            if not isinstance(output_summary, dict):
                continue
            refs = output_summary.get("evidence_refs")
            if isinstance(refs, list):
                for ref in refs:
                    candidate = str(ref).strip()
                    if candidate:
                        evidence_refs.append(candidate)

        final_response = orchestration_result.final_response
        if final_response is not None:
            for block in final_response.report_blocks:
                if block.get("block_type") != "evidence_overview":
                    continue
                typed_block = EvidenceOverviewBlock(**block)
                for item in typed_block["items"]:
                    evidence_id = str(item.get("evidence_id") or "").strip()
                    if evidence_id:
                        evidence_refs.append(evidence_id)

        return self._unique(evidence_refs)

    def _build_available_follow_ups(
        self,
        *,
        active_candidates: list[str],
        key_evidence_refs: list[str],
        intent: str,
    ) -> list[str]:
        follow_ups: list[str] = []
        if len(active_candidates) >= 2:
            follow_ups.append("compare")
        if intent == "metric_lookup" or key_evidence_refs:
            follow_ups.append("drilldown")
        if intent != "out_of_scope":
            follow_ups.append("expand")
        return self._unique(follow_ups)

    def _extract_companies(self, text: str) -> list[str]:
        return [match.group(1) for match in _COMPANY_PATTERN.finditer(text)]

    def _unique(self, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            candidate = str(value).strip()
            if not candidate or candidate in seen:
                continue
            normalized.append(candidate)
            seen.add(candidate)
        return normalized
