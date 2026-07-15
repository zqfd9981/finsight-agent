from __future__ import annotations

import re

from finsight_agent.control_plane.orchestrator.models import OrchestrationResult
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.report_block import EvidenceOverviewBlock
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext

from .compressor import build_history_summary

_COMPANY_PATTERN = re.compile(r"(宁德时代|贵州茅台|比亚迪|中远海能|招商轮船|中国船舶)")


class SessionContextExtractor:
    """从结构化执行产物中提取首版 SessionContext。"""

    def extract(
        self,
        *,
        request: AnalysisRequest,
        router_result: RouterResult,
        orchestration_result: OrchestrationResult,
        previous_context: SessionContext | None = None,
    ) -> SessionContext:
        del request

        active_topic = self._build_active_topic(router_result, orchestration_result)
        active_candidates = self._build_active_candidates(
            router_result,
            orchestration_result,
        )[:3]
        key_evidence_refs = self._build_key_evidence_refs(orchestration_result)[:5]
        available_follow_ups = self._build_available_follow_ups(
            active_candidates=active_candidates,
            key_evidence_refs=key_evidence_refs,
            intent=router_result.intent,
        )
        history_summary = build_history_summary(
            intent=router_result.intent,
            active_topic=active_topic,
            active_candidates=active_candidates,
            has_evidence_refs=bool(key_evidence_refs),
            previous_summary=(previous_context.history_summary if previous_context else ""),
        )

        return SessionContext(
            session_id=orchestration_result.session_id,
            active_topic=active_topic,
            active_candidates=active_candidates,
            key_evidence_refs=key_evidence_refs,
            history_summary=history_summary,
            available_follow_ups=available_follow_ups,
        )

    def _build_active_topic(
        self,
        router_result: RouterResult,
        orchestration_result: OrchestrationResult,
    ) -> str:
        entities = router_result.entities
        if router_result.intent == "metric_lookup":
            # 适配新 entities 结构：用扁平字段（schema.py 已展开嵌套对象）
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
    ) -> list[str]:
        candidates: list[str] = []
        target = str(router_result.entities.get("target") or "").strip()
        # 适配新 entities 结构：company 可能是 dict（新格式）或字符串（旧格式）
        # schema.py 已展开为扁平字段 company_name
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

        return self._unique(candidates)

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
