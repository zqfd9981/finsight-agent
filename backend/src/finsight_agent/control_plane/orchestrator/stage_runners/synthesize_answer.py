from __future__ import annotations

"""统一的 synthesize_answer stage：按 response_mode 切换 context 组装逻辑。

替代原 synthesize_brief_answer / synthesize_event_answer / synthesize_report 三个 stage。
response_mode 由 stage_planner.resolve_stages 写入 stage_constraints，本 stage 读取后分发：
  - direct       → 泛财经 LLM 直答，只用 query + router entities
  - brief_answer → 指标类简短答复，读 query_structured_data 结果
  - event_answer → 事件类答复，读 collect_event_context 结果
  - report       → 证据型报告，读 retrieve_evidence + analyze_targets + collect_event_context
"""

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.capabilities.retrieval.models import RetrievalResult
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.report_block import EvidenceOverviewBlock, EvidenceOverviewItem
from shared.contracts.router_result import RouterResult
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_synthesize_answer_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    constraints = dict(stage_constraints or {})
    response_mode = str(
        constraints.get("response_mode") or ResponseMode.BRIEF_ANSWER.value
    )

    if response_mode == ResponseMode.DIRECT.value:
        return _synthesize_direct(request, router_result, reporting_service)
    if response_mode == ResponseMode.BRIEF_ANSWER.value:
        return _synthesize_brief(request, router_result, execution_state, reporting_service)
    if response_mode == ResponseMode.EVENT_ANSWER.value:
        return _synthesize_event(request, router_result, execution_state, reporting_service)
    return _synthesize_report(request, router_result, execution_state, reporting_service)


def _synthesize_direct(
    request: AnalysisRequest,
    router_result: RouterResult,
    reporting_service: ReportingService,
) -> StageExecutionResult:
    """泛财经轻路径：LLM 直答，不读 execution_state。"""
    summary = request.query.strip() or "泛财经问题直接答复。"
    final_response = reporting_service.build_response(
        response_mode=ResponseMode.DIRECT.value,
        session_id=request.session_id or "",
        summary=summary,
        final_answer_context={
            "query": request.query,
            "intent": router_result.intent,
            "topics": router_result.entities.get("topics", []),
            "is_direct": True,
        },
    )
    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        user_summary=summary,
    )


def _synthesize_brief(
    request: AnalysisRequest,
    router_result: RouterResult,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    """指标类简短答复，读 query_structured_data 结果。"""
    stage_result = execution_state[StageName.QUERY_STRUCTURED_DATA.value]
    structured_result = dict(stage_result.output_payload.get("structured_result", {}))

    company = str(structured_result.get("company", "")).strip()
    metric = str(structured_result.get("metric", "")).strip()
    time_scope = str(structured_result.get("time_scope", "")).strip()
    value = str(structured_result.get("value", "")).strip()
    unit = str(structured_result.get("unit", "")).strip()
    is_degraded = bool(structured_result.get("is_degraded", False))
    notes = [
        str(item).strip()
        for item in structured_result.get("notes", [])
        if str(item).strip()
    ]

    if is_degraded:
        note_text = "；".join(notes) if notes else "当前未找到对应指标数据。"
        summary = f"{company}{time_scope}{metric}暂未命中结构化数据。{note_text}"
    else:
        # value 已含 % 号（比率类衍生指标）时不再拼接 unit，避免 "91.63%%"
        if unit == "%" and value.endswith("%"):
            summary = f"{company}{time_scope}{metric}为 {value}。"
        else:
            summary = f"{company}{time_scope}{metric}为 {value}{unit}。"

    final_response = reporting_service.build_response(
        response_mode=ResponseMode.BRIEF_ANSWER.value,
        session_id=request.session_id or "",
        summary=summary,
        final_answer_context={
            "query": request.query,
            "intent": router_result.intent,
            "strategy": "structured_data",
            "structured_result": structured_result,
            "is_degraded": is_degraded,
            "notes": notes,
        },
    )
    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        user_summary=summary,
    )


def _synthesize_event(
    request: AnalysisRequest,
    router_result: RouterResult,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    """事件类答复，读 collect_event_context 结果。"""
    collect_result = execution_state[StageName.COLLECT_EVENT_CONTEXT.value]
    collect_payload = dict(collect_result.output_payload)
    event_context = dict(collect_payload.get("event_context", {}) or {})
    source_status = dict(collect_payload.get("source_status", {}) or {})
    strategy = str(
        collect_payload.get("strategy") or source_status.get("mode") or ""
    ).strip()

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

    summary = _build_event_summary(
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

    final_response = reporting_service.build_response(
        response_mode=ResponseMode.EVENT_ANSWER.value,
        session_id=request.session_id or "",
        summary=summary,
        uncertainty_notes=uncertainty_notes,
        next_actions=next_actions,
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
        stage_name=StageName.SYNTHESIZE_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        evidence_refs=evidence_refs,
        user_summary=summary,
    )


def _synthesize_report(
    request: AnalysisRequest,
    router_result: RouterResult,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    """证据型报告，读 retrieve_evidence + analyze_targets + collect_event_context。"""
    retrieve_result = execution_state[StageName.RETRIEVE_EVIDENCE.value]
    analyze_targets_result = execution_state.get(StageName.ANALYZE_TARGETS.value)
    collect_context_result = execution_state.get(StageName.COLLECT_EVENT_CONTEXT.value)

    retrieval_result = retrieve_result.output_payload.get("retrieval_result")
    if not isinstance(retrieval_result, RetrievalResult):
        raise TypeError("retrieve_evidence stage missing retrieval_result")

    analyze_targets_payload = _read_stage_output(analyze_targets_result)
    collect_context_payload = _read_stage_output(collect_context_result)
    event_context = dict(collect_context_payload.get("event_context", {}) or {})
    source_status = dict(collect_context_payload.get("source_status", {}) or {})
    strategy = str(
        collect_context_payload.get("strategy") or source_status.get("mode") or ""
    ).strip()

    target_scope = _normalize_parts(analyze_targets_payload.get("target_scope"))
    open_questions = _normalize_parts(analyze_targets_payload.get("open_questions"))
    evidence_count = len(retrieval_result.evidence_items)
    event_evidence_count = len(_normalize_parts(event_context.get("evidence_refs")))
    summary = _build_report_summary(
        evidence_count=evidence_count,
        target_scope=target_scope,
    )

    report_blocks = [
        EvidenceOverviewBlock(
            block_type="evidence_overview",
            title="Evidence Overview",
            items=[
                EvidenceOverviewItem(
                    evidence_id=item.evidence_id,
                    excerpt=item.excerpt,
                    company_name=item.company_name,
                    doc_type=item.doc_type,
                )
                for item in retrieval_result.evidence_items
            ],
        )
    ]
    uncertainty_notes: list[str] = []
    if not evidence_count and strategy != "event_primary":
        uncertainty_notes.append("No strong direct evidence was retrieved yet.")
    uncertainty_notes.extend(open_questions)

    next_actions = ["Ask for a narrower company, time window, or disclosure angle."]
    if target_scope:
        next_actions.insert(
            0, f"Prioritize direct evidence review for {', '.join(target_scope[:2])}."
        )

    final_response = reporting_service.build_response(
        response_mode=ResponseMode.REPORT.value,
        session_id=request.session_id or "",
        summary=summary,
        report_blocks=report_blocks,
        uncertainty_notes=uncertainty_notes,
        next_actions=next_actions,
        final_answer_context={
            "query": request.query,
            "intent": router_result.intent,
            "strategy": strategy,
            "event_summary": str(event_context.get("context_summary") or "").strip(),
            "supporting_points": list(event_context.get("supporting_points") or []),
            "target_scope": target_scope,
            "event_evidence_refs": list(event_context.get("evidence_refs") or []),
            "event_evidence_count": event_evidence_count,
            "company_evidence_count": evidence_count,
            "evidence_items": [
                {
                    "evidence_id": item.evidence_id,
                    "excerpt": item.excerpt,
                    "company_name": item.company_name,
                    "doc_type": item.doc_type,
                }
                for item in retrieval_result.evidence_items
            ],
            "uncertainty_notes": uncertainty_notes,
            "next_actions": next_actions,
        },
    )
    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        evidence_refs=list(retrieve_result.evidence_refs),
        user_summary=summary,
    )


def _build_event_summary(
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


def _build_report_summary(
    *,
    evidence_count: int,
    target_scope: list[str],
) -> str:
    if target_scope and evidence_count:
        return (
            f"Retrieved {evidence_count} evidence items for {', '.join(target_scope[:2])}; "
            "ready for report synthesis."
        )
    if target_scope:
        return f"Completed target scoping with focus on {', '.join(target_scope[:3])}."
    if evidence_count:
        return f"Retrieved {evidence_count} evidence items for report synthesis."
    return "No relevant evidence was retrieved."


def _read_stage_output(stage_value: object) -> dict[str, object]:
    if isinstance(stage_value, StageExecutionResult):
        return stage_value.output_payload
    if isinstance(stage_value, dict):
        return stage_value
    return {}


def _normalize_parts(value: object) -> list[str]:
    if isinstance(value, str):
        candidate = value.strip()
        return [candidate] if candidate else []
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            candidate = str(item).strip()
            if candidate:
                normalized.append(candidate)
        return normalized
    return []
