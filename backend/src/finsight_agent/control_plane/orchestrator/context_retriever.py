from __future__ import annotations

from typing import Protocol


class ExternalContextRetriever(Protocol):
    """外部上下文检索器协议。

    orchestrator 只依赖这层抽象，避免直接绑定具体新闻 API 或搜索工具。
    """

    def retrieve_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> dict[str, object] | None:
        """检索事件背景材料，并返回标准化上下文片段。"""

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        """在候选池不足时执行一次有界候选发现检索。"""


class NullExternalContextRetriever:
    """默认空实现，保证首版在未接真实外部工具时仍可安全降级。"""

    def retrieve_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> dict[str, object] | None:
        del query, event, themes, time_scope, limit
        return None

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        del query, event_context, limit
        return None
