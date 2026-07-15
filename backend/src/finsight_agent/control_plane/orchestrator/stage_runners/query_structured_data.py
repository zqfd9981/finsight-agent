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
    """结构化数据查询 stage。

    适配新 entities 结构（router LLM 直接输出 standard_name + period_end + stock_code）：
    - company: 优先用 standard_name，fallback 到 company_name 扁平字段
    - company_code: 从 stock_code 提取
    - metric: 优先用 standard_name（已是英文 key），fallback 到 metric_raw
    - metric_type: direct/derived，决定走直接查询还是衍生计算
    - period_end: YYYY-MM-DD 格式，下游 repository 直接用；空则查最新
    """
    entities = router_result.entities
    constraints = stage_constraints or {}

    # 兼容新旧 entities 结构
    # 新格式：entities.company 是 dict，含 standard_name/stock_code
    # 旧格式：entities.company 是字符串
    company_entity = entities.get("company", "")
    if isinstance(company_entity, dict):
        company = str(
            company_entity.get("standard_name") or company_entity.get("raw") or ""
        ).strip()
        company_code = str(company_entity.get("stock_code") or "").strip()
    else:
        company = str(company_entity or "").strip()
        company_code = ""

    metric_entity = entities.get("metric", "")
    if isinstance(metric_entity, dict):
        metric = str(
            metric_entity.get("standard_name") or metric_entity.get("raw") or ""
        ).strip()
        metric_raw = str(metric_entity.get("raw") or metric).strip()
        metric_type = str(metric_entity.get("metric_type") or "direct").strip()
    else:
        metric = str(metric_entity or "").strip()
        metric_raw = metric
        metric_type = "direct"

    time_entity = entities.get("time_scope", "")
    if isinstance(time_entity, dict):
        period_end = str(time_entity.get("period_end") or "").strip()
        time_scope_raw = str(time_entity.get("raw") or "").strip()
    else:
        period_end = ""
        time_scope_raw = str(time_entity or "").strip()

    # period_end 优先（新格式），空则 fallback 到 time_hint 约束（旧格式）
    effective_period_end = period_end or str(
        constraints.get("time_hint") or ""
    ).strip() or "latest"

    structured_result = structured_data_service.query_metric_lookup(
        company=company,
        metric=metric,
        time_scope=effective_period_end,
        company_code=company_code,
        metric_raw=metric_raw,
        metric_type=metric_type,
    )
    summary = f"已查询 {company}{effective_period_end}{metric} 的结构化结果。".strip()

    return StageExecutionResult(
        stage_name=StageName.QUERY_STRUCTURED_DATA.value,
        status="success",
        output_payload={"structured_result": structured_result},
        user_summary=summary,
    )
