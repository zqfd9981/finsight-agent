from __future__ import annotations

from finsight_agent.capabilities.structured_data.compute_intent import detect_compute_intent
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

    Phase 1 路由策略（最终方案五层架构）：
    1. metric_type=derived → 走 query_metric_lookup 单值衍生路径（毛利率/ROE 等规则表）
    2. 否则优先 query_via_assembler（entities 校验 → SQLAssembler → 执行 → 多行）
       - via="assembler" 或 fallback 命中 → 用 StructuredQueryResult.to_stage_payload
       - via="fallback" 且 degraded → 再走 query_metric_lookup 单值完整路径
         （含衍生兜底 + external provider），保证绝不退步

    entities 兼容三种格式（router schema 已归一化）：
    - 列表型（新格式，多实体）：company/metric/time_scope 为 list
    - 单值 dict（新格式，单实体）：company/metric/time_scope 为 dict
    - 字符串（旧格式）：company/metric/time_scope 为 str
    """
    entities = router_result.entities
    constraints = stage_constraints or {}

    # 2.2 定案：Router 顶层 filters/ranking 约束字段注入 entities，
    # 复用既有 entities → validator → assemble 通道（已被 test_query_via_assembler 覆盖）。
    entities = _inject_router_constraints(entities, router_result)

    metric_type = _extract_metric_type(entities)

    # 路径优先级：compute（同比/环比/复合增长/聚合） > derived（毛利率/ROE 规则表） > assembler
    # 关键：router 可能把"净利润同比增长率"识别成 metric_type=derived + standard_name=net_profit_growth_rate，
    # 但 _DERIVED_METRICS 规则表没有 growth_rate 类 key，会失败。compute 路径能剥掉 _growth_rate 后缀
    # 还原原料指标（net_profit）再算 yoy，所以 compute 必须优先于 derived。
    plan = detect_compute_intent(request.query, entities)
    computed = (
        structured_data_service.query_via_compute(plan) if plan is not None else None
    )

    if computed is not None:
        structured_result = computed.to_stage_payload()
        structured_result["via"] = computed.via
    elif plan is not None:
        # compute 命中但计算失败（如 CAGR 缺期数据）→ 用原料指标查 assembler，返回已有期数据
        # 避免 derived 路径因 metric=net_profit_growth_rate 不命中规则表而误报"衍生指标计算失败"
        fallback_entities = _rewrite_entities_for_raw_metric(entities, plan)
        result = structured_data_service.query_via_assembler(fallback_entities)
        if result.via == "assembler" or not result.is_degraded:
            structured_result = result.to_stage_payload()
            structured_result["via"] = result.via
        else:
            structured_result = _query_single_value(
                structured_data_service, fallback_entities, constraints
            )
    elif metric_type == "derived":
        # 衍生指标直接走单值衍生规则表（毛利率/ROE 等规则表，比 SQL 更可靠）
        structured_result = _query_single_value(
            structured_data_service, entities, constraints
        )
    else:
        # 优先确定性组装器主路径
        result = structured_data_service.query_via_assembler(entities)
        if result.via == "assembler" or not result.is_degraded:
            structured_result = result.to_stage_payload()
            structured_result["via"] = result.via
        else:
            # assembler + fallback 均 degraded，再走单值完整路径（衍生/external 兜底）
            structured_result = _query_single_value(
                structured_data_service, entities, constraints
            )

    if structured_result.get("computed"):
        summary = f"已计算 {structured_result.get('kind', '')} 结果。"
    else:
        company = str(structured_result.get("company", "")).strip()
        metric = str(structured_result.get("metric", "")).strip()
        summary = f"已查询 {company}{metric} 的结构化结果。".strip()
        if structured_result.get("is_multi"):
            summary = f"已查询 {company} 多项结构化指标，共 {len(structured_result.get('records', []))} 行。"

    return StageExecutionResult(
        stage_name=StageName.QUERY_STRUCTURED_DATA.value,
        status="success",
        output_payload={"structured_result": structured_result},
        user_summary=summary,
    )


def _inject_router_constraints(entities: dict, router_result: "RouterResult") -> dict:
    """把 RouterResult 顶层的 filters/ranking 注入 entities，供既有 validator→assemble 通道消费。

    仅当 Router 实际产出了约束字段才注入；规则版 Router 恒为空，原样返回。
    """
    if not router_result.filters and router_result.ranking is None:
        return entities
    merged = dict(entities)
    if router_result.filters:
        merged["filters"] = router_result.filters
    if router_result.ranking is not None:
        merged["ranking"] = router_result.ranking
    return merged


def _extract_metric_type(entities: dict) -> str:
    """从 entities 抽 metric_type，兼容 list/dict/str。"""
    metric_entity = entities.get("metric", "")
    if isinstance(metric_entity, dict):
        return str(metric_entity.get("metric_type") or "direct").strip()
    if isinstance(metric_entity, list):
        for it in metric_entity:
            if isinstance(it, dict):
                return str(it.get("metric_type") or "direct").strip()
    return "direct"


def _rewrite_entities_for_raw_metric(entities: dict, plan) -> dict:
    """compute 失败时，把 entities 的 metric 替换为 plan.metric（原料指标）。

    用于 compute 命中但计算失败（如 CAGR 缺期数据）时 fallback 到 assembler，
    返回已有期数据，避免 derived 路径因 metric=net_profit_growth_rate 不命中
    规则表而误报"衍生指标计算失败"。

    - metric 替换为 {raw: plan.metric_raw, standard_name: plan.metric, metric_type: direct}
    - time_scope 替换为 plan.periods（list 格式，多期）
    - company 原样保留
    """
    new_entities = dict(entities)
    new_entities["metric"] = {
        "raw": plan.metric_raw or plan.metric,
        "standard_name": plan.metric,
        "metric_type": "direct",
    }
    if plan.periods:
        new_entities["time_scope"] = [
            {"period_end": p, "raw": ""} for p in plan.periods
        ]
    return new_entities


def _query_single_value(
    service: StructuredDataService,
    entities: dict,
    constraints: dict[str, object],
) -> dict[str, object]:
    """单值完整路径：抽第一个 company/metric/time_scope 调 query_metric_lookup。

    保留现有衍生指标 + external provider 能力，作为 assembler 路径的兜底。
    """
    company_entity = entities.get("company", "")
    if isinstance(company_entity, list):
        company_entity = company_entity[0] if company_entity else {}
    if isinstance(company_entity, dict):
        company = str(
            company_entity.get("standard_name") or company_entity.get("raw") or ""
        ).strip()
        company_code = str(company_entity.get("stock_code") or "").strip()
    else:
        company = str(company_entity or "").strip()
        company_code = ""

    metric_entity = entities.get("metric", "")
    if isinstance(metric_entity, list):
        metric_entity = metric_entity[0] if metric_entity else ""
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
    if isinstance(time_entity, list):
        time_entity = time_entity[0] if time_entity else ""
    if isinstance(time_entity, dict):
        period_end = str(time_entity.get("period_end") or "").strip()
    else:
        period_end = ""
        time_entity = str(time_entity or "").strip()

    effective_period_end = period_end or str(
        constraints.get("time_hint") or ""
    ).strip() or "latest"

    return service.query_metric_lookup(
        company=company,
        metric=metric,
        time_scope=effective_period_end,
        company_code=company_code,
        metric_raw=metric_raw,
        metric_type=metric_type,
    )
