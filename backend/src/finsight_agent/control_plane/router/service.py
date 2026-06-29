from __future__ import annotations

from finsight_agent.config.feature_flags import llm_router_enabled
from finsight_agent.config.settings import load_settings
from finsight_agent.infra.llm import LlmClient
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.enums.follow_up_type import FollowUpType

from .llm import route_with_llm
from .rules import detect_follow_up_type, route_with_rules


class RouterService:
    """V1 router 的最小服务骨架。"""

    def __init__(self, llm_client: LlmClient | None = None) -> None:
        settings = load_settings()
        self._router_system_prompt = settings.control_plane.prompts.router_system_prompt_path.read_text(
            encoding="utf-8"
        )
        self._llm_client = llm_client or LlmClient()

    def route(
        self,
        query: str,
        session_context: SessionContext | None = None,
    ) -> RouterResult:
        """根据 query 和可选会话上下文返回结构化路由结果。"""
        normalized_query = query.strip()
        follow_up_type = detect_follow_up_type(normalized_query, session_context)

        llm_result = self._route_with_llm(normalized_query, session_context)
        if llm_result is not None:
            if not llm_result.follow_up_type:
                llm_result.follow_up_type = follow_up_type
            return llm_result

        return route_with_rules(normalized_query, session_context, follow_up_type)

    def build_metric_lookup_stub(self) -> RouterResult:
        """返回 metric_lookup 快路径的占位路由结果。"""
        return RouterResult(
            intent="metric_lookup",
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={},
            needs=["structured_data_query"],
            constraints={"preferred_output": "brief_answer"},
        )

    def _route_with_llm(
        self,
        query: str,
        session_context: SessionContext | None,
    ) -> RouterResult | None:
        if not llm_router_enabled():
            return None
        return route_with_llm(
            self._llm_client,
            self._router_system_prompt,
            query,
            session_context,
        )
