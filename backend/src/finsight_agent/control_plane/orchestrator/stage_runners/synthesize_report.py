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
    retrieve_result = execution_state[StageName.RETRIEVE_EVIDENCE.value]
    retrieval_result = retrieve_result.output_payload.get("retrieval_result")
    if not isinstance(retrieval_result, RetrievalResult):
        raise TypeError("retrieve_evidence 阶段缺少 retrieval_result")

    evidence_count = len(retrieval_result.evidence_items)
    if evidence_count:
        summary = f"已检索到 {evidence_count} 条证据，可用于继续研判。"
    else:
        summary = "暂未检索到相关证据。"

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
    uncertainty_notes = [] if evidence_count else ["当前未检索到可用证据。"]
    next_actions = ["可继续追问更具体的公司、时间或主题。"]
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
