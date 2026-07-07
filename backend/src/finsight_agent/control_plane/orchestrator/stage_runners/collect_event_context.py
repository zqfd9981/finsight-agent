from __future__ import annotations

from collections.abc import Iterable

from finsight_agent.capabilities.retrieval.service import RetrievalFacade
from finsight_agent.control_plane.orchestrator.context_retriever import (
    ExternalContextRetriever,
)
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_collect_event_context_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, object],
    retrieval_facade: RetrievalFacade,
    external_context_retriever: ExternalContextRetriever,
) -> StageExecutionResult:
    del execution_state

    constraints = stage_constraints or {}
    entities = router_result.entities
    retrieval_budget = int(constraints.get("retrieval_budget") or 3)
    event = str(entities.get("event") or "").strip()
    themes = _normalize_parts(entities.get("themes"))
    time_scope = str(entities.get("time_scope") or "recent").strip()

    # 先取事件外部上下文；只有外部结果不足或显式要求时，才补一次本地 RAG。
    external_payload = external_context_retriever.retrieve_event_context(
        query=request.query,
        event=event,
        themes=themes,
        time_scope=time_scope,
        limit=retrieval_budget,
    ) or {}

    retrieval_result = None
    if _should_use_local_rag(external_payload):
        retrieval_result = retrieval_facade.retrieve_evidence(
            raw_query=_build_event_context_query(
                query=request.query,
                event=event,
                themes=themes,
                time_scope=time_scope,
            ),
            limit=retrieval_budget,
        )

    local_evidence_refs = [
        item.evidence_id
        for item in (retrieval_result.evidence_items if retrieval_result is not None else [])
        if item.evidence_id
    ]
    external_evidence_refs = _normalize_parts(external_payload.get("evidence_refs"))
    evidence_refs = _deduplicate([*external_evidence_refs, *local_evidence_refs])

    supporting_points = _deduplicate(
        [
            *_normalize_parts(external_payload.get("supporting_points")),
            *[
                item.excerpt.strip()
                for item in (
                    retrieval_result.evidence_items if retrieval_result is not None else []
                )
                if item.excerpt.strip()
            ],
        ]
    )

    summary_parts = _deduplicate(
        [
            str(external_payload.get("summary_hint") or "").strip(),
            event,
            *supporting_points[:2],
        ]
    )
    context_summary = "；".join(part for part in summary_parts if part)
    status = "success" if context_summary or evidence_refs else "degraded"
    degraded_reason = None if status == "success" else "event_context_insufficient"

    source_status = dict(external_payload.get("source_status") or {})
    source_status.update(
        {
            "external_used": bool(external_payload),
            "local_evidence_count": len(local_evidence_refs),
        }
    )
    strategy = str(source_status.get("mode") or "").strip()
    candidate_hints = _normalize_parts(external_payload.get("candidate_hints"))

    event_context = {
        "event": event,
        "themes": themes,
        "time_scope": time_scope,
        "context_summary": context_summary,
        "supporting_points": supporting_points,
        "evidence_refs": evidence_refs,
        "candidate_hints": candidate_hints,
    }
    event_entities = {
        "event": event,
        "themes": themes,
        "time_scope": time_scope,
    }

    return StageExecutionResult(
        stage_name=StageName.COLLECT_EVENT_CONTEXT.value,
        status=status,
        output_payload={
            "event_context": event_context,
            "event_entities": event_entities,
            "source_status": source_status,
            "strategy": strategy,
        },
        evidence_refs=evidence_refs,
        degraded_reason=degraded_reason,
        user_summary=context_summary or "已拿到有限事件背景，后续分析将按降级路径继续。",
    )


def _should_use_local_rag(external_payload: dict[str, object]) -> bool:
    """仅在外部上下文不足或显式要求时，才补一次本地 RAG。"""

    if not external_payload:
        return True

    source_status = external_payload.get("source_status")
    if isinstance(source_status, dict):
        if source_status.get("local_rag_needed") is True:
            return True
        if source_status.get("allow_local_rag") is False:
            return False

    summary_hint = str(external_payload.get("summary_hint") or "").strip()
    supporting_points = _normalize_parts(external_payload.get("supporting_points"))
    evidence_refs = _normalize_parts(external_payload.get("evidence_refs"))
    return not (summary_hint or supporting_points or evidence_refs)


def _build_event_context_query(
    *,
    query: str,
    event: str,
    themes: list[str],
    time_scope: str,
) -> str:
    return " ".join(
        _deduplicate(
            [
                query.strip(),
                event,
                *themes,
                time_scope,
            ]
        )
    )


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
