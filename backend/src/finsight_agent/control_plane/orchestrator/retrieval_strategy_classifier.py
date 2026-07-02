from __future__ import annotations

from typing import Protocol


RETRIEVAL_STRATEGIES = (
    "event_primary",
    "disclosure_primary",
    "dual_primary",
)
DEFAULT_RETRIEVAL_STRATEGY = "event_primary"


class RetrievalStrategyClassifier(Protocol):
    """检索策略分类器协议。

    控制面只依赖这一层抽象，具体模型实现可以后续按同一接口插拔。
    """

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        """返回三分类策略标签、置信度和调试原因。"""


class StubRetrievalStrategyClassifier:
    """训练分类器未就绪时的安全默认实现。"""

    def classify(
        self,
        *,
        query: str,
        router_payload: dict[str, object],
        session_topic: str,
    ) -> dict[str, str]:
        del query, router_payload, session_topic
        return {
            "strategy": DEFAULT_RETRIEVAL_STRATEGY,
            "confidence": "low",
            "reason": "stub_fallback",
        }
