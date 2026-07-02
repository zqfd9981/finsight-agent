from __future__ import annotations

from collections.abc import Iterable

from finsight_agent.control_plane.orchestrator.context_retriever import (
    ExternalContextRetriever,
)
from finsight_agent.control_plane.orchestrator.target_analysis import (
    TargetAnalysisService,
)
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_analyze_targets_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, object],
    session_context: SessionContext | None,
    external_context_retriever: ExternalContextRetriever,
    target_analysis_service: TargetAnalysisService,
) -> StageExecutionResult:
    constraints = stage_constraints or {}
    collect_event_context = _read_stage_output(
        execution_state.get(StageName.COLLECT_EVENT_CONTEXT.value)
    )
    event_context = _read_mapping(collect_event_context.get("event_context"))
    router_entities = router_result.entities

    candidate_pool = _build_candidate_pool(
        router_entities=router_entities,
        event_context=event_context,
        session_context=session_context,
    )

    # 候选池不足时只允许补一次候选发现检索，避免 stage 内部无限回路。
    if not candidate_pool:
        discovery_payload = external_context_retriever.discover_candidates(
            query=request.query,
            event_context=event_context,
            limit=int(constraints.get("candidate_discovery_budget") or 1),
        ) or {}
        candidate_pool = _normalize_parts(
            discovery_payload.get("candidates") or discovery_payload.get("target_scope")
        )

    if not candidate_pool:
        message = "当前只能确认事件背景，尚不能可靠识别具体受影响标的。"
        return StageExecutionResult(
            stage_name=StageName.ANALYZE_TARGETS.value,
            status="degraded",
            output_payload={
                "target_scope": [],
                "ranked_targets": [],
                "open_questions": [message],
                "confidence": "low",
                "analysis_mode": "candidate_discovery_degraded",
            },
            degraded_reason="candidate_pool_insufficient",
            user_summary=message,
        )

    analysis_payload = target_analysis_service.analyze_targets(
        query=request.query,
        event_context=event_context,
        candidate_pool=candidate_pool,
    )
    target_scope = _normalize_parts(analysis_payload.get("target_scope"))
    ranked_targets = analysis_payload.get("ranked_targets") or []
    open_questions = _normalize_parts(analysis_payload.get("open_questions"))

    return StageExecutionResult(
        stage_name=StageName.ANALYZE_TARGETS.value,
        status="success",
        output_payload={
            "target_scope": target_scope,
            "ranked_targets": ranked_targets,
            "open_questions": open_questions,
            "confidence": str(analysis_payload.get("confidence") or "medium").strip(),
            "analysis_mode": str(
                analysis_payload.get("analysis_mode") or "llm_constrained"
            ).strip(),
        },
        user_summary=_build_user_summary(target_scope, ranked_targets),
    )


def _build_candidate_pool(
    *,
    router_entities: dict[str, object],
    event_context: dict[str, object],
    session_context: SessionContext | None,
) -> list[str]:
    return _deduplicate(
        [
            str(router_entities.get("target") or "").strip(),
            *_normalize_parts(router_entities.get("targets")),
            *(
                list(session_context.active_candidates)
                if session_context is not None
                else []
            ),
            *_normalize_parts(event_context.get("candidate_hints")),
        ]
    )


def _build_user_summary(
    target_scope: list[str],
    ranked_targets: object,
) -> str:
    if target_scope:
        return f"已完成受影响标的初筛，当前优先关注：{'、'.join(target_scope[:3])}。"
    if isinstance(ranked_targets, list) and ranked_targets:
        return "已完成受影响标的初筛。"
    return "当前未能形成稳定标的列表。"


def _read_stage_output(stage_value: object) -> dict[str, object]:
    if isinstance(stage_value, StageExecutionResult):
        return _read_mapping(stage_value.output_payload)
    return _read_mapping(stage_value)


def _read_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _normalize_parts(value: object) -> list[str]:
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, Iterable):
        normalized: list[str] = []
        for item in value:
            candidate = str(item).strip()
            if candidate:
                normalized.append(candidate)
        return normalized
    return []


def _deduplicate(parts: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for part in parts:
        candidate = str(part).strip()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
    return normalized
