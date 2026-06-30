from __future__ import annotations

from dataclasses import dataclass, field

from .dense_index import DenseChunkIndex
from .models import DenseHit, DenseSearchFilters
from .query_rewrite import build_alias_queries


@dataclass(slots=True)
class DenseSearchResult:
    """Dense 检索的最小聚合结果。"""

    hits: list[DenseHit] = field(default_factory=list)
    original_hit_count: int = 0
    rewrite_queries: list[str] = field(default_factory=list)
    rewrite_policy_version: str = "alias_v1"


class DenseRetrievalService:
    """原 query 优先、alias 补充的 dense 检索编排层。"""

    def __init__(self, index: DenseChunkIndex, min_original_hits: int = 3) -> None:
        self._index = index
        self._min_original_hits = min_original_hits

    def search(
        self,
        query_text: str,
        limit: int,
        filters: DenseSearchFilters | None = None,
    ) -> DenseSearchResult:
        """先查原 query，命中不足时再触发 alias 查询。"""

        original_hits = self._index.search(
            query_text=query_text,
            limit=limit,
            filters=filters,
            query_variant="original",
        )
        merged_hits = list(original_hits)
        seen_chunk_ids = {hit.chunk_id for hit in original_hits}
        triggered_rewrite_queries: list[str] = []

        if len(original_hits) < self._min_original_hits:
            for rewrite_query in build_alias_queries(query_text):
                triggered_rewrite_queries.append(rewrite_query.query_text)
                rewrite_hits = self._index.search(
                    query_text=rewrite_query.query_text,
                    limit=limit,
                    filters=filters,
                    query_variant=rewrite_query.rewrite_type,
                )
                for hit in rewrite_hits:
                    if hit.chunk_id in seen_chunk_ids:
                        continue
                    seen_chunk_ids.add(hit.chunk_id)
                    merged_hits.append(hit)
                    if len(merged_hits) >= limit:
                        break
                if len(merged_hits) >= limit:
                    break

        return DenseSearchResult(
            hits=merged_hits[:limit],
            original_hit_count=len(original_hits),
            rewrite_queries=triggered_rewrite_queries,
            rewrite_policy_version="alias_v1",
        )
