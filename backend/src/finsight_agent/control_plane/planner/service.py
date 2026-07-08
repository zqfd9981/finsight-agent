from __future__ import annotations

from copy import deepcopy

from finsight_agent.config.feature_flags import llm_planner_enabled
from finsight_agent.config.settings import load_settings
from finsight_agent.infra.llm import LlmClient
from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult
from shared.enums.intent import Intent

from .llm import build_plan_with_llm
from .rules import build_plan_with_rules


class PlannerService:
    """V1 planner 的最小服务骨架。"""

    def __init__(self, llm_client: LlmClient | None = None) -> None:
        settings = load_settings()
        self._planner_system_prompt = settings.control_plane.prompts.planner_system_prompt_path.read_text(
            encoding="utf-8"
        )
        self._llm_client = llm_client or LlmClient()

    def build_plan(self, router_result: RouterResult) -> Plan:
        """基于路由结果生成最小计划占位对象。"""
        rule_plan = build_plan_with_rules(router_result)
        llm_plan = self._build_plan_with_llm(router_result)
        if llm_plan is not None:
            return _reconcile_llm_plan(rule_plan, llm_plan)

        return rule_plan

    def _build_plan_with_llm(self, router_result: RouterResult) -> Plan | None:
        if not llm_planner_enabled():
            return None
        return build_plan_with_llm(
            self._llm_client,
            self._planner_system_prompt,
            router_result,
        )


def _reconcile_llm_plan(rule_plan: Plan, llm_plan: Plan) -> Plan:
    if rule_plan.intent in {
        Intent.METRIC_LOOKUP.value,
        Intent.OUT_OF_SCOPE.value,
    }:
        return rule_plan

    if llm_plan.intent != rule_plan.intent:
        return rule_plan
    if llm_plan.stages != rule_plan.stages:
        return rule_plan

    return Plan(
        plan_id=llm_plan.plan_id or rule_plan.plan_id,
        intent=rule_plan.intent,
        stages=list(rule_plan.stages),
        stage_constraints=_merge_stage_constraints(
            rule_plan.stage_constraints,
            llm_plan.stage_constraints,
        ),
        response_mode=rule_plan.response_mode,
    )


def _merge_stage_constraints(
    rule_constraints: dict[str, object],
    llm_constraints: dict[str, object],
) -> dict[str, object]:
    merged = deepcopy(rule_constraints)

    for stage_name, stage_value in merged.items():
        if not isinstance(stage_value, dict):
            continue
        llm_stage_value = llm_constraints.get(stage_name)
        if not isinstance(llm_stage_value, dict):
            continue

        for key, rule_value in stage_value.items():
            llm_value = llm_stage_value.get(key)
            if _is_safe_constraint_override(rule_value, llm_value):
                stage_value[key] = llm_value

    return merged


def _is_safe_constraint_override(rule_value: object, llm_value: object) -> bool:
    if isinstance(rule_value, bool):
        return isinstance(llm_value, bool)
    if isinstance(rule_value, int):
        return isinstance(llm_value, int) and llm_value > 0
    if isinstance(rule_value, str):
        return isinstance(llm_value, str) and bool(llm_value.strip())
    if isinstance(rule_value, list):
        return isinstance(llm_value, list)
    return False
