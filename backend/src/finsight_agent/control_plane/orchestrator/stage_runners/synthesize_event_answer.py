from __future__ import annotations

from finsight_agent.capabilities.reporting.service import ReportingService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_synthesize_event_answer_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    del stage_constraints

    collect_result = execution_state[StageName.COLLECT_EVENT_CONTEXT.value]
    collect_payload = dict(collect_result.output_payload)
    event_context = dict(collect_payload.get("event_context", {}) or {})
    source_status = dict(collect_payload.get("source_status", {}) or {})
    strategy = str(collect_payload.get("strategy") or source_status.get("mode") or "").strip()

    event = str(event_context.get("event") or "").strip()
    summary_text = str(event_context.get("context_summary") or "").strip()
    supporting_points = [
        str(item).strip()
        for item in event_context.get("supporting_points", [])
        if str(item).strip()
    ]
    evidence_refs = [
        str(item).strip()
        for item in event_context.get("evidence_refs", [])
        if str(item).strip()
    ]

    summary = _build_summary(
        event=event,
        summary_text=summary_text,
        supporting_points=supporting_points,
    )
    uncertainty_notes: list[str] = []
    if not evidence_refs:
        uncertainty_notes.append("Event context is still missing strong traceable evidence.")
    next_actions = [
        "Ask about specific sectors, companies, or disclosures for a deeper follow-up.",
    ]

    final_response = reporting_service.build_brief_response(
        session_id=request.session_id or "",
        summary=summary,
        final_answer_context={
            "query": request.query,
            "intent": router_result.intent,
            "strategy": strategy,
            "event": event,
            "event_summary": summary_text,
            "supporting_points": supporting_points,
            "event_evidence_refs": evidence_refs,
            "uncertainty_notes": uncertainty_notes,
            "next_actions": next_actions,
        },
    )

    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_EVENT_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        evidence_refs=evidence_refs,
        user_summary=summary,
    )


def _build_summary(
    *,
    event: str,
    summary_text: str,
    supporting_points: list[str],
) -> str:
    if summary_text:
        return summary_text
    if supporting_points:
        prefix = event if event else "Current event"
        return f"{prefix} key context: {'; '.join(supporting_points[:3])}"
    if event:
        return f"Completed event-context synthesis for {event}."
    return "Completed event-context synthesis."
