from __future__ import annotations

from .dense_retrieval_service import DenseSearchResult
from .models import RetrievalResult, RetrievalTrace
from .sparse_retrieval_service import SparseSearchResult


def build_retrieval_trace(
    *,
    original_query: str,
    normalized_query: str,
    sparse_result: SparseSearchResult,
    dense_result: DenseSearchResult,
    fused_hit_count: int,
    reranked_hit_count: int,
    final_evidence_count: int,
    parent_expand_attempted: bool,
    parent_expand_fallback_count: int,
) -> RetrievalTrace:
    """构造轻量结构化 retrieval trace，供程序侧稳定消费。"""

    rewrite_queries = _merge_rewrite_queries(
        sparse_result.triggered_rewrite_queries,
        dense_result.rewrite_queries,
    )
    return RetrievalTrace(
        original_query=original_query,
        normalized_query=normalized_query,
        rewrite_queries=rewrite_queries,
        sparse_hit_count=len(sparse_result.hits),
        dense_hit_count=len(dense_result.hits),
        fused_hit_count=fused_hit_count,
        reranked_hit_count=reranked_hit_count,
        final_evidence_count=final_evidence_count,
        sparse_rewrite_triggered=bool(sparse_result.triggered_rewrite_queries),
        dense_rewrite_triggered=bool(dense_result.rewrite_queries),
        parent_expand_attempted=parent_expand_attempted,
        parent_expand_fallback_count=parent_expand_fallback_count,
    )


def build_retrieval_notes(
    *,
    sparse_result: SparseSearchResult,
    dense_result: DenseSearchResult,
    parent_expand_fallback_count: int,
) -> list[str]:
    """生成面向人工快速阅读的 notes 摘要。"""

    notes: list[str] = []
    if sparse_result.triggered_rewrite_queries:
        notes.append(
            f"sparse rewrite: {', '.join(sparse_result.triggered_rewrite_queries)}"
        )
    if dense_result.rewrite_queries:
        notes.append(f"dense rewrite: {', '.join(dense_result.rewrite_queries)}")
    if parent_expand_fallback_count > 0:
        notes.append(
            f"parent expand fallback used for {parent_expand_fallback_count} evidence item(s)"
        )
    return notes


def attach_trace_to_result(
    result: RetrievalResult,
    trace: RetrievalTrace,
    notes: list[str],
) -> RetrievalResult:
    """把 trace 和 notes 回填到统一 RetrievalResult。"""

    result.retrieval_trace = trace
    result.retrieval_notes = list(notes)
    return result


def _merge_rewrite_queries(
    sparse_queries: list[str],
    dense_queries: list[str],
) -> list[str]:
    """保序去重合并 rewrite 查询。"""

    merged: list[str] = []
    seen: set[str] = set()
    for query in [*sparse_queries, *dense_queries]:
        normalized = query.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged
