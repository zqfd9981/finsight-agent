from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ContextRetrievalPlan,
)
from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
    DEFAULT_RETRIEVAL_STRATEGY,
)


class ContextRetrievalPlanner:
    """把策略分类结果翻译成 collect_event_context 的执行计划。"""

    def build_plan(
        self,
        *,
        strategy_payload: dict[str, str],
        router_payload: dict[str, object],
    ) -> ContextRetrievalPlan:
        del router_payload
        strategy = strategy_payload.get("strategy") or DEFAULT_RETRIEVAL_STRATEGY

        if strategy == "disclosure_primary":
            return ContextRetrievalPlan(
                mode="disclosure_primary",
                steps=[{"source": "disclosure_search", "budget": 1}],
                allow_local_rag=False,
            )
        if strategy == "dual_primary":
            return ContextRetrievalPlan(
                mode="dual_primary",
                steps=[
                    {"source": "event_search", "budget": 1},
                    {"source": "disclosure_search", "budget": 1},
                ],
                allow_local_rag=False,
            )
        return ContextRetrievalPlan(
            mode="event_primary",
            steps=[{"source": "event_search", "budget": 1}],
            allow_local_rag=False,
        )
