from __future__ import annotations

from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName


def build_plan_with_rules(router_result: RouterResult) -> Plan:
    if router_result.intent == Intent.METRIC_LOOKUP.value:
        time_hint = router_result.entities.get("time_scope", "latest")
        return Plan(
            plan_id="plan_metric_lookup_v1",
            intent=router_result.intent,
            stages=[
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ],
            stage_constraints={
                StageName.QUERY_STRUCTURED_DATA.value: {
                    "time_hint": time_hint,
                },
                StageName.SYNTHESIZE_BRIEF_ANSWER.value: {
                    "preferred_output": router_result.constraints.get(
                        "preferred_output",
                        ResponseMode.BRIEF_ANSWER.value,
                    )
                },
            },
            response_mode=ResponseMode.BRIEF_ANSWER.value,
        )

    if router_result.intent == Intent.EVENT_IMPACT_ANALYSIS.value:
        time_hint = router_result.constraints.get("time_hint", "unspecified")
        return Plan(
            plan_id="plan_event_impact_analysis_v1",
            intent=router_result.intent,
            stages=[
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
            stage_constraints={
                StageName.COLLECT_EVENT_CONTEXT.value: {
                    "time_hint": time_hint,
                    "retrieval_budget": 3,
                },
                StageName.ANALYZE_TARGETS.value: {
                    "target_scope": router_result.entities.get("themes", []),
                },
                StageName.RETRIEVE_EVIDENCE.value: {
                    "retrieval_budget": 4,
                },
                StageName.SYNTHESIZE_REPORT.value: {
                    "preferred_output": router_result.constraints.get(
                        "preferred_output",
                        ResponseMode.REPORT.value,
                    )
                },
            },
            response_mode=ResponseMode.REPORT.value,
        )

    if router_result.intent == Intent.EVIDENCE_LOOKUP.value:
        return Plan(
            plan_id="plan_evidence_lookup_v1",
            intent=router_result.intent,
            stages=[
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
            stage_constraints={
                StageName.RETRIEVE_EVIDENCE.value: {
                    "retrieval_budget": router_result.constraints.get(
                        "retrieval_budget",
                        4,
                    ),
                    "target": router_result.entities.get("target", ""),
                },
                StageName.SYNTHESIZE_REPORT.value: {
                    "preferred_output": router_result.constraints.get(
                        "preferred_output",
                        ResponseMode.REPORT.value,
                    )
                },
            },
            response_mode=ResponseMode.REPORT.value,
        )

    return Plan(
        plan_id="plan_out_of_scope_v1",
        intent=router_result.intent,
        stages=[],
        stage_constraints={
            "guardrail": {
                "preferred_output": router_result.constraints.get(
                    "preferred_output",
                    "guardrail",
                ),
                "reason_code": router_result.constraints.get("reason_code", ""),
            }
        },
        response_mode=ResponseMode.BRIEF_ANSWER.value,
    )
