from __future__ import annotations

from finsight_agent.capabilities.reporting.service import ReportingService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_synthesize_brief_answer_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, StageExecutionResult],
    reporting_service: ReportingService,
) -> StageExecutionResult:
    stage_result = execution_state[StageName.QUERY_STRUCTURED_DATA.value]
    structured_result = dict(stage_result.output_payload.get("structured_result", {}))

    company = str(structured_result.get("company", "")).strip()
    metric = str(structured_result.get("metric", "")).strip()
    time_scope = str(structured_result.get("time_scope", "")).strip()
    value = str(structured_result.get("value", "")).strip()
    summary = f"{company}{time_scope}{metric}为{value}。"
    final_response = reporting_service.build_brief_response(
        session_id=request.session_id or "",
        summary=summary,
    )

    return StageExecutionResult(
        stage_name=StageName.SYNTHESIZE_BRIEF_ANSWER.value,
        status="success",
        output_payload={"final_response": final_response},
        user_summary=summary,
    )
