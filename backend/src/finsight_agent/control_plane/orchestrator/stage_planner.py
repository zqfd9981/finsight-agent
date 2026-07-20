from __future__ import annotations

"""(intent, strategy) → (stages, stage_constraints, response_mode) 查表函数。

替代原 PlannerService 的 stage 编排职责，纯查表无 LLM 调用。router 只做意图识别，
classifier 只对 event_impact_analysis 做 strategy 三分类，本函数把两者的结果映射成
orchestrator 可直接执行的 stage 列表 + stage 级约束 + 最终响应模式。
"""

import logging

from shared.contracts.router_result import RouterResult
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName

_logger = logging.getLogger(__name__)


def build_plan(
    router_result: RouterResult,
    *,
    strategy_classifier: object | None = None,
    query: str = "",
    session_topic: str = "",
) -> tuple[list[str], dict[str, dict[str, object]], str, dict[str, str] | None]:
    """单一入口：intent(+event 策略分类) → (stages, stage_constraints, response_mode, strategy_payload)。

    取代原先 classify_strategy_node + plan_stages_node 的二段路由：对 event_impact_analysis
    意图内部调用 strategy_classifier 做策略三分类，其余意图 strategy_payload 为 None，
    再统一查表 resolve_stages。对外只暴露本函数。
    """
    strategy_payload: dict[str, str] | None = None
    if (
        router_result.intent == Intent.EVENT_IMPACT_ANALYSIS.value
        and strategy_classifier is not None
    ):
        try:
            payload = strategy_classifier.classify(
                query=query,
                router_payload={
                    "intent": router_result.intent,
                    "follow_up_type": router_result.follow_up_type,
                    "confidence": router_result.confidence,
                    "entities": router_result.entities,
                    "needs": router_result.needs,
                    "constraints": router_result.constraints,
                },
                session_topic=session_topic,
            )
            strategy_payload = {
                "strategy": str(payload.get("strategy") or "").strip(),
                "confidence": str(payload.get("confidence") or "").strip(),
                "reason": str(payload.get("reason") or "").strip(),
            }
        except Exception as exc:  # noqa: BLE001
            _logger.warning("build_plan classify_strategy 失败，回退 None: %s", exc)
            strategy_payload = None
    stages, stage_constraints, response_mode = resolve_stages(
        router_result, strategy_payload=strategy_payload
    )
    return stages, stage_constraints, response_mode, strategy_payload


def resolve_stages(
    router_result: RouterResult,
    *,
    strategy_payload: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    """(intent, strategy) → (stages, stage_constraints, response_mode)。"""
    if router_result.intent == Intent.METRIC_LOOKUP.value:
        return _build_metric_lookup_plan(router_result)
    if router_result.intent == Intent.EVENT_IMPACT_ANALYSIS.value:
        return _build_event_impact_plan(router_result, strategy_payload=strategy_payload)
    if router_result.intent == Intent.EVIDENCE_LOOKUP.value:
        return _build_evidence_lookup_plan(router_result)
    if router_result.intent == Intent.GENERAL_FINANCE_QA.value:
        return _build_general_finance_qa_plan(router_result)
    return _build_out_of_scope_plan(router_result)


def _build_metric_lookup_plan(
    router_result: RouterResult,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    # 适配新 entities 结构：period_end 优先（新格式），fallback 到 time_scope 原文（旧格式）
    entities = router_result.entities
    period_end = str(entities.get("period_end") or "").strip()
    time_scope_raw = str(entities.get("time_scope_raw") or "").strip()
    # time_hint 传给 query_structured_data stage 作为 fallback
    # 新格式：period_end 日期优先；旧格式：time_scope 原文
    time_hint = period_end or time_scope_raw or "latest"
    stages = [
        StageName.QUERY_STRUCTURED_DATA.value,
        StageName.REFLECT_AND_REQUERY.value,
        StageName.SYNTHESIZE_ANSWER.value,
        StageName.VERIFY_ANSWER.value,
    ]
    response_mode = ResponseMode.BRIEF_ANSWER.value
    stage_constraints = {
        StageName.QUERY_STRUCTURED_DATA.value: {"time_hint": time_hint},
        StageName.SYNTHESIZE_ANSWER.value: {
            "response_mode": response_mode,
            "preferred_output": router_result.constraints.get(
                "preferred_output", response_mode
            ),
        },
    }
    return stages, stage_constraints, response_mode


def _build_event_impact_plan(
    router_result: RouterResult,
    *,
    strategy_payload: dict[str, str] | None,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    time_hint = str(router_result.constraints.get("time_hint", "unspecified")).strip()
    strategy_meta = dict(strategy_payload or {})
    strategy = str(strategy_meta.get("strategy") or "event_primary").strip()
    confidence = str(strategy_meta.get("confidence") or "low").strip()
    reason = str(strategy_meta.get("reason") or "").strip()
    collect_constraints = {
        "time_hint": time_hint,
        "retrieval_budget": 3,
        "strategy": strategy,
        "strategy_confidence": confidence,
        "strategy_reason": reason,
    }

    if strategy == "disclosure_primary":
        stages = [
            StageName.COLLECT_EVENT_CONTEXT.value,
            StageName.RETRIEVE_EVIDENCE.value,
            StageName.SYNTHESIZE_ANSWER.value,
            StageName.VERIFY_ANSWER.value,
        ]
        response_mode = ResponseMode.REPORT.value
        stage_constraints = {
            StageName.COLLECT_EVENT_CONTEXT.value: collect_constraints,
            StageName.RETRIEVE_EVIDENCE.value: {"retrieval_budget": 4},
            StageName.SYNTHESIZE_ANSWER.value: {
                "response_mode": response_mode,
                "preferred_output": router_result.constraints.get(
                    "preferred_output", response_mode
                ),
            },
            StageName.VERIFY_ANSWER.value: {},
        }
        return stages, stage_constraints, response_mode

    if strategy == "dual_primary":
        stages = [
            StageName.COLLECT_EVENT_CONTEXT.value,
            StageName.ANALYZE_TARGETS.value,
            StageName.RETRIEVE_EVIDENCE.value,
            StageName.SYNTHESIZE_ANSWER.value,
            StageName.VERIFY_ANSWER.value,
        ]
        response_mode = ResponseMode.REPORT.value
        stage_constraints = {
            StageName.COLLECT_EVENT_CONTEXT.value: collect_constraints,
            StageName.ANALYZE_TARGETS.value: {
                "target_scope": router_result.entities.get("themes", []),
            },
            StageName.RETRIEVE_EVIDENCE.value: {"retrieval_budget": 4},
            StageName.SYNTHESIZE_ANSWER.value: {
                "response_mode": response_mode,
                "preferred_output": router_result.constraints.get(
                    "preferred_output", response_mode
                ),
            },
            StageName.VERIFY_ANSWER.value: {},
        }
        return stages, stage_constraints, response_mode

    # event_primary：走 event_answer 模板，基于 collect_event_context 输出
    stages = [
        StageName.COLLECT_EVENT_CONTEXT.value,
        StageName.SYNTHESIZE_ANSWER.value,
        StageName.VERIFY_ANSWER.value,
    ]
    response_mode = ResponseMode.EVENT_ANSWER.value
    stage_constraints = {
        StageName.COLLECT_EVENT_CONTEXT.value: collect_constraints,
        StageName.SYNTHESIZE_ANSWER.value: {
            "response_mode": response_mode,
            "preferred_output": ResponseMode.BRIEF_ANSWER.value,
        },
        StageName.VERIFY_ANSWER.value: {},
    }
    return stages, stage_constraints, response_mode


def _build_evidence_lookup_plan(
    router_result: RouterResult,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    stages = [
        StageName.RETRIEVE_EVIDENCE.value,
        StageName.SYNTHESIZE_ANSWER.value,
        StageName.VERIFY_ANSWER.value,
    ]
    response_mode = ResponseMode.REPORT.value
    stage_constraints = {
        StageName.RETRIEVE_EVIDENCE.value: {
            "retrieval_budget": router_result.constraints.get("retrieval_budget", 4),
            "target": router_result.entities.get("target", ""),
        },
        StageName.SYNTHESIZE_ANSWER.value: {
            "response_mode": response_mode,
            "preferred_output": router_result.constraints.get(
                "preferred_output", response_mode
            ),
        },
        StageName.VERIFY_ANSWER.value: {},
    }
    return stages, stage_constraints, response_mode


def _build_general_finance_qa_plan(
    router_result: RouterResult,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    """泛财经轻路径：LLM 直答，不调任何检索。"""
    stages = [StageName.SYNTHESIZE_ANSWER.value, StageName.VERIFY_ANSWER.value]
    response_mode = ResponseMode.DIRECT.value
    stage_constraints = {
        StageName.SYNTHESIZE_ANSWER.value: {
            "response_mode": response_mode,
            "preferred_output": response_mode,
        },
        StageName.VERIFY_ANSWER.value: {},
    }
    return stages, stage_constraints, response_mode


def _build_out_of_scope_plan(
    router_result: RouterResult,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    """out_of_scope 不走 stage，由 guardrail 短路。"""
    stage_constraints = {
        "guardrail": {
            "preferred_output": router_result.constraints.get(
                "preferred_output", "guardrail"
            ),
            "reason_code": router_result.constraints.get("reason_code", ""),
        }
    }
    return [], stage_constraints, ResponseMode.BRIEF_ANSWER.value
