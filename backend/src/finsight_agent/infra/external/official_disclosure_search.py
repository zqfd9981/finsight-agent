from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)
from finsight_agent.infra.external.cninfo_context_search import (
    CninfoContextSearchProvider,
)
from finsight_agent.infra.external.sse_context_search import SseContextSearchProvider


class OfficialDisclosureSearchProvider:
    """官方披露搜索组合 provider。

    首版采用 CNInfo 主查、SSE 补查，再做轻量标准化合并。
    """

    def __init__(
        self,
        *,
        cninfo_provider: CninfoContextSearchProvider | None = None,
        sse_provider: SseContextSearchProvider | None = None,
    ) -> None:
        self._cninfo = cninfo_provider or CninfoContextSearchProvider()
        self._sse = sse_provider or SseContextSearchProvider()

    def search(self, *, query: str, limit: int) -> ExternalContextResult:
        primary = self._cninfo.search(query=query, limit=limit)
        secondary = self._sse.search(query=query, limit=limit)
        return ExternalContextResult(
            items=[*primary.items, *secondary.items],
            summary_hint=primary.summary_hint or secondary.summary_hint,
            supporting_points=[*primary.supporting_points, *secondary.supporting_points][
                :4
            ],
            evidence_refs=[*primary.evidence_refs, *secondary.evidence_refs],
            candidate_hints=[*primary.candidate_hints, *secondary.candidate_hints],
            source_status={
                **primary.source_status,
                **secondary.source_status,
            },
        )
