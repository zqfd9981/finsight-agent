from __future__ import annotations

import logging

from finsight_agent.capabilities.structured_data.service import StructuredDataService
from finsight_agent.infra.llm import LlmClient
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

from ..models import StageExecutionResult

_logger = logging.getLogger(__name__)

# 反思阶段提供给 LLM 的常用指标 standard_name 参考，帮助其产出可查的原料指标
_AVAILABLE_METRICS = [
    "revenue",
    "operating_cost",
    "net_profit",
    "net_profit_attributable_to_parent",
    "total_assets",
    "total_liabilities",
    "total_owners_equity",
    "operating_cash_flow",
    "total_current_assets",
    "total_current_liabilities",
    "inventory",
    "accounts_receivable",
    "fixed_assets",
    "cash_and_equivalents",
    "operating_profit",
    "total_profit",
    "income_tax_expense",
]

_REFLECT_SYSTEM_PROMPT = (
    "You are FinSight Agent V1 reflection engine. "
    "A structured-data query degraded (no direct value found). "
    "Decide whether the answer can be derived from ingredient metrics. "
    "Return exactly one JSON object, no markdown: "
    '{"need_requery": bool, "ingredient_metrics": [standard snake_case names], '
    '"reasoning": str}. '
    "Only list ingredient_metrics that are truly needed and present in available_metrics. "
    "If no derivation is possible, set need_requery=false and an empty list."
)


def run_reflect_and_requery_stage(
    *,
    request: AnalysisRequest,
    router_result: RouterResult,
    stage_constraints: dict[str, object] | None = None,
    execution_state: dict[str, object],
    structured_data_service: StructuredDataService,
    llm_client: LlmClient | None = None,
) -> StageExecutionResult:
    """ReAct 反思节点：结构化查询降级时，LLM 反思缺哪些原料指标并补查。

    未降级（已命中）时直接 no-op，零开销。命中降级则：
    1. 调 LLM 反思 need_requery + ingredient_metrics
    2. 逐个 query_metric_lookup 补查原料
    3. 累积 ingredient_results 供 synthesize 基于原料计算（如毛利率=营收-成本推导）
    LLM 不可用或调用失败时保持 degraded，不抛出（保证主路径不崩）。
    """
    upstream = execution_state.get(StageName.QUERY_STRUCTURED_DATA.value)
    if not isinstance(upstream, StageExecutionResult):
        return _noop_result()
    structured_result = dict(upstream.output_payload.get("structured_result", {}))
    if not structured_result.get("is_degraded", False):
        return _noop_result()

    company = str(structured_result.get("company", "")).strip()
    metric = str(structured_result.get("metric", "")).strip()
    time_scope = str(
        structured_result.get("period_end")
        or structured_result.get("time_scope")
        or ""
    ).strip()

    ingredient_results: list[dict] = []
    reasoning = ""
    if llm_client is not None and company:
        try:
            payload = llm_client.complete_json(
                prompt_name="reflect_requery",
                variables={
                    "system_prompt": _REFLECT_SYSTEM_PROMPT,
                    "query": request.query,
                    "company": company,
                    "metric": metric,
                    "time_scope": time_scope,
                    "available_metrics": _AVAILABLE_METRICS,
                },
            )
            need = bool(payload.get("need_requery", False))
            ingredients = payload.get("ingredient_metrics") or []
            reasoning = str(payload.get("reasoning", "")).strip()
            if need and isinstance(ingredients, list):
                for ing in ingredients[:5]:
                    ing_name = str(ing).strip()
                    if not ing_name:
                        continue
                    try:
                        res = structured_data_service.query_metric_lookup(
                            company=company,
                            metric=ing_name,
                            time_scope=time_scope or "latest",
                        )
                    except Exception as exc:
                        _logger.warning("reflect 补查 %s 失败: %s", ing_name, exc)
                        continue
                    ingredient_results.append(
                        {
                            "metric": ing_name,
                            "value": str(res.get("value", "")),
                            "unit": str(res.get("unit", "")),
                            "is_degraded": bool(res.get("is_degraded", False)),
                        }
                    )
        except Exception as exc:
            _logger.warning("reflect_and_requery 反思失败，保持降级: %s", exc)

    return StageExecutionResult(
        stage_name=StageName.REFLECT_AND_REQUERY.value,
        status="success",
        output_payload={
            "ingredient_results": ingredient_results,
            "reasoning": reasoning,
            "need_requery": bool(ingredient_results),
        },
        user_summary=(
            f"已反思并补查 {len(ingredient_results)} 个原料指标"
            if ingredient_results
            else None
        ),
    )


def _noop_result() -> StageExecutionResult:
    return StageExecutionResult(
        stage_name=StageName.REFLECT_AND_REQUERY.value,
        status="success",
        output_payload={"ingredient_results": [], "reasoning": "", "need_requery": False},
    )
