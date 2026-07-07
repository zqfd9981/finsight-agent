from __future__ import annotations

from typing import Protocol

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)


class EventSearchProvider(Protocol):
    """事件搜索 provider 协议。

    orchestrator 只依赖这层抽象，避免直接绑定具体事件搜索服务（当前默认是博查 Web Search）。
    与 DisclosureSearchProvider 不同：本协议由事件搜索 consumer 拥有，
    因此与 ExternalContextRetriever Protocol 同侧放在 control_plane/orchestrator/。
    """

    def search_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> ExternalContextResult:
        """检索事件背景材料，并返回标准化上下文片段。"""