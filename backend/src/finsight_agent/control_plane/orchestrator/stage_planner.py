from __future__ import annotations

"""(intent, strategy) → (stages, stage_constraints, response_mode) 查表函数。

替代原 PlannerService 的 stage 编排职责，纯查表无 LLM 调用。router 只做意图识别，
classifier 只对 event_impact_analysis 做 strategy 三分类，本函数把两者的结果映射成
orchestrator 可直接执行的 stage 列表 + stage 级约束 + 最终响应模式。
"""

from shared.contracts.router_result import RouterResult
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName


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
    time_hint = router_result.entities.get("time_scope", "latest")
    stages = [
        StageName.QUERY_STRUCTURED_DATA.value,
        StageName.SYNTHESIZE_ANSWER.value,
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
        }
        return stages, stage_constraints, response_mode

    if strategy == "dual_primary":
        stages = [
            StageName.COLLECT_EVENT_CONTEXT.value,
            StageName.ANALYZE_TARGETS.value,
            StageName.RETRIEVE_EVIDENCE.value,
            StageName.SYNTHESIZE_ANSWER.value,
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
        }
        return stages, stage_constraints, response_mode

    # event_primary：走 event_answer 模板，基于 collect_event_context 输出
    stages = [
        StageName.COLLECT_EVENT_CONTEXT.value,
        StageName.SYNTHESIZE_ANSWER.value,
    ]
    response_mode = ResponseMode.EVENT_ANSWER.value
    stage_constraints = {
        StageName.COLLECT_EVENT_CONTEXT.value: collect_constraints,
        StageName.SYNTHESIZE_ANSWER.value: {
            "response_mode": response_mode,
            "preferred_output": ResponseMode.BRIEF_ANSWER.value,
        },
    }
    return stages, stage_constraints, response_mode


def _build_evidence_lookup_plan(
    router_result: RouterResult,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    stages = [
        StageName.RETRIEVE_EVIDENCE.value,
        StageName.SYNTHESIZE_ANSWER.value,
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
    }
    return stages, stage_constraints, response_mode


def _build_general_finance_qa_plan(
    router_result: RouterResult,
) -> tuple[list[str], dict[str, dict[str, object]], str]:
    """泛财经轻路径：LLM 直答，不调任何检索。"""
    stages = [StageName.SYNTHESIZE_ANSWER.value]
    response_mode = ResponseMode.DIRECT.value
    stage_constraints = {
        StageName.SYNTHESIZE_ANSWER.value: {
            "response_mode": response_mode,
            "preferred_output": response_mode,
        },
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
