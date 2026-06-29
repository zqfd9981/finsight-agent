from __future__ import annotations

from finsight_agent.config.feature_flags import llm_planner_enabled
from finsight_agent.config.settings import load_settings
from finsight_agent.infra.llm import LlmClient
from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult

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
        llm_plan = self._build_plan_with_llm(router_result)
        if llm_plan is not None:
            return llm_plan

        return build_plan_with_rules(router_result)

    def _build_plan_with_llm(self, router_result: RouterResult) -> Plan | None:
        if not llm_planner_enabled():
            return None
        return build_plan_with_llm(
            self._llm_client,
            self._planner_system_prompt,
            router_result,
        )
