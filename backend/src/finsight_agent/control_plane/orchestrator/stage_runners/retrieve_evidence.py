from __future__ import annotations

from collections.abc import Iterable

from finsight_agent.capabilities.retrieval.service import RetrievalFacade
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_retrieve_evidence_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, object],
    retrieval_facade: RetrievalFacade,
) -> StageExecutionResult:
    constraints = stage_constraints or {}
    limit = int(constraints.get("retrieval_budget") or 5)
    retrieval_query = _build_retrieval_query(
        request=request,
        router_result=router_result,
        stage_constraints=constraints,
        execution_state=execution_state,
    )
    retrieval_result = retrieval_facade.retrieve_evidence(
        raw_query=retrieval_query,
        limit=limit,
    )
    evidence_refs = [
        item.evidence_id
        for item in retrieval_result.evidence_items
        if item.evidence_id
    ]
    summary = f"已检索到 {len(evidence_refs)} 条证据。"

    return StageExecutionResult(
        stage_name=StageName.RETRIEVE_EVIDENCE.value,
        status="success",
        output_payload={"retrieval_result": retrieval_result},
        evidence_refs=evidence_refs,
        user_summary=summary,
    )


def _build_retrieval_query(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object],
    execution_state: dict[str, object],
) -> str:
    entities = router_result.entities
    collect_event_context = _read_stage_output(
        execution_state.get("collect_event_context")
    )
    analyze_targets = _read_stage_output(execution_state.get("analyze_targets"))
    event_context = _read_mapping(collect_event_context.get("event_context"))
    event_entities = _read_mapping(collect_event_context.get("event_entities"))
    prioritized_target = str(stage_constraints.get("target") or "").strip()
    fallback_target = str(entities.get("target") or "").strip()

    query_parts = [
        request.query.strip(),
        str(entities.get("claim") or "").strip(),
        prioritized_target,
        str(event_context.get("event") or event_entities.get("event") or entities.get("event") or "").strip(),
        *_normalize_parts(
            event_context.get("themes")
            or event_entities.get("themes")
            or entities.get("themes")
        ),
        str(
            event_context.get("time_scope")
            or event_entities.get("time_scope")
            or entities.get("time_scope")
            or ""
        ).strip(),
        fallback_target,
        *_normalize_parts(analyze_targets.get("target_scope") or stage_constraints.get("target_scope")),
    ]

    normalized_parts: list[str] = []
    seen: set[str] = set()
    for part in query_parts:
        if not part:
            continue
        if part in seen:
            continue
        normalized_parts.append(part)
        seen.add(part)

    return " ".join(normalized_parts)


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
