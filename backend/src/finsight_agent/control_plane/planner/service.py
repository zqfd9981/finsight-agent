from __future__ import annotations

from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName


class PlannerService:
    """V1 planner 的最小服务骨架。"""

    def build_plan(self, router_result: RouterResult) -> Plan:
        """基于路由结果生成最小计划占位对象。"""
        stages = []
        if router_result.intent == "metric_lookup":
            stages = [
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ]

        return Plan(
            plan_id="plan_stub_metric_lookup",
            intent=router_result.intent,
            stages=stages,
            stage_constraints=router_result.constraints,
            response_mode=ResponseMode.BRIEF_ANSWER.value,
        )
