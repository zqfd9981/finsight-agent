from __future__ import annotations

from shared.contracts.router_result import RouterResult
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent


class RouterService:
    """V1 router 的最小服务骨架。"""

    def build_metric_lookup_stub(self) -> RouterResult:
        """返回 metric_lookup 快路径的占位路由结果。"""
        return RouterResult(
            intent=Intent.METRIC_LOOKUP.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={},
            needs=["structured_data_query"],
            constraints={"preferred_output": "brief_answer"},
        )
