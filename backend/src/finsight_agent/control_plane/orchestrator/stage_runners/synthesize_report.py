from __future__ import annotations

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.capabilities.retrieval.models import RetrievalResult
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.report_block import EvidenceOverviewBlock, EvidenceOverviewItem
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_synthesize_report_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    del router_result, stage_constraints

    retrieve_result = execution_state[StageName.RETRIEVE_EVIDENCE.value]
    analyze_targets_result = execution_state.get(StageName.ANALYZE_TARGETS.value)
    retrieval_result = retrieve_result.output_payload.get("retrieval_result")
    if not isinstance(retrieval_result, RetrievalResult):
        raise TypeError("retrieve_evidence 阶段缺少 retrieval_result")

    analyze_targets_payload = _read_stage_output(analyze_targets_result)
    target_scope = _normalize_parts(analyze_targets_payload.get("target_scope"))
    open_questions = _normalize_parts(analyze_targets_payload.get("open_questions"))
    evidence_count = len(retrieval_result.evidence_items)
    summary = _build_summary(evidence_count=evidence_count, target_scope=target_scope)

    report_blocks = [
        EvidenceOverviewBlock(
            block_type="evidence_overview",
            title="证据概览",
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
    uncertainty_notes = []
    if not evidence_count:
        uncertainty_notes.append("当前尚未检索到足够强的直接证据。")
    uncertainty_notes.extend(open_questions)

    next_actions = ["可继续追问更具体的公司、时间或主题。"]
    if target_scope:
        next_actions.insert(0, f"可优先补查 {'、'.join(target_scope[:2])} 的直接证据。")
    final_response = reporting_service.build_report_response(
        session_id=request.session_id or "",
        summary=summary,
        report_blocks=report_blocks,
        uncertainty_notes=uncertainty_notes,
        next_actions=next_actions,
    )

    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_REPORT.value,
        status="success",
        output_payload={"final_response": final_response},
        evidence_refs=list(retrieve_result.evidence_refs),
        user_summary=summary,
    )


def _build_summary(*, evidence_count: int, target_scope: list[str]) -> str:
    if target_scope and evidence_count:
        return (
            f"已围绕 {'、'.join(target_scope[:2])} 检索到 {evidence_count} 条证据，"
            "可用于继续研判。"
        )
    if target_scope:
        return f"已完成初步标的分析，当前优先关注：{'、'.join(target_scope[:3])}。"
    if evidence_count:
        return f"已检索到 {evidence_count} 条证据，可用于继续研判。"
    return "暂未检索到相关证据。"


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
