from __future__ import annotations

from finsight_agent.capabilities.structured_data.service import StructuredDataService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult


def run_query_structured_data_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None,
    execution_state: dict[str, object],
    structured_data_service: StructuredDataService,
) -> StageExecutionResult:
    entities = router_result.entities
    constraints = stage_constraints or {}
    company = str(entities.get("company", "")).strip()
    metric = str(entities.get("metric", "")).strip()
    time_scope = str(
        constraints.get("time_hint")
        or entities.get("time_scope")
        or "latest"
    ).strip()

    structured_result = structured_data_service.query_metric_lookup(
        company=company,
        metric=metric,
        time_scope=time_scope,
    )
    summary = f"已查询 {company}{time_scope}{metric} 的结构化结果。".strip()

    return StageExecutionResult(
        stage_name=StageName.QUERY_STRUCTURED_DATA.value,
        status="success",
        output_payload={"structured_result": structured_result},
        user_summary=summary,
    )
