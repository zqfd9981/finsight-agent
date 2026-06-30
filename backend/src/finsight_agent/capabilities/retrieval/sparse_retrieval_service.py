from __future__ import annotations

from dataclasses import dataclass, field

from .models import SparseChunkHit, SparseSearchFilters
from .query_rewrite import build_alias_queries
from .sparse_index import SparseChunkIndex


@dataclass(slots=True)
class SparseSearchResult:
    """稀疏检索的最小聚合结果。"""

    hits: list[SparseChunkHit] = field(default_factory=list)
    triggered_rewrite_queries: list[str] = field(default_factory=list)
    hit_sources: dict[str, str] = field(default_factory=dict)


class SparseRetrievalService:
    """原 query 优先、alias 补充的首版 sparse 检索编排层。"""

    def __init__(self, index: SparseChunkIndex, min_original_hits: int = 3) -> None:
        self._index = index
        self._min_original_hits = min_original_hits

    def search(
        self,
        query_text: str,
        limit: int,
        filters: SparseSearchFilters | None = None,
    ) -> SparseSearchResult:
        """先查原 query，命中不足时再触发轻量 alias 查询。"""

        original_hits = self._index.search(
            query_text=query_text,
            limit=limit,
            filters=filters,
        )
        hit_sources = {hit.chunk_id: "original" for hit in original_hits}
        merged_hits = list(original_hits)
        triggered_rewrite_queries: list[str] = []

        if len(original_hits) >= self._min_original_hits:
            return SparseSearchResult(
                hits=merged_hits[:limit],
                triggered_rewrite_queries=triggered_rewrite_queries,
                hit_sources=hit_sources,
            )

        for rewrite_query in build_alias_queries(query_text):
            triggered_rewrite_queries.append(rewrite_query.query_text)
            rewrite_hits = self._index.search(
                query_text=rewrite_query.query_text,
                limit=limit,
                filters=filters,
            )
            for hit in rewrite_hits:
                if hit.chunk_id in hit_sources:
                    continue
                hit_sources[hit.chunk_id] = "rewritten"
                merged_hits.append(hit)
                if len(merged_hits) >= limit:
                    break
            if len(merged_hits) >= limit:
                break

        return SparseSearchResult(
            hits=merged_hits[:limit],
            triggered_rewrite_queries=triggered_rewrite_queries,
            hit_sources=hit_sources,
        )
