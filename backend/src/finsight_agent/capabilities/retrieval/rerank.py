from __future__ import annotations

from collections.abc import Mapping

from finsight_agent.capabilities.rerank import (
    RerankCandidate,
    build_default_reranker,
)

from .models import FusedHit, RerankedHit


def rerank_hits(
    hits: list[FusedHit],
    query_text: str,
    top_n: int = 20,
    reranker=None,
) -> list[RerankedHit]:
    """Rerank fused hits with a shared lightweight reranker."""

    normalized_query = query_text.strip()
    if not normalized_query:
        return []

    resolved_reranker = reranker or build_default_reranker()
    truncated_hits = hits[:top_n]
    candidates = [
        RerankCandidate(
            id=str(index),
            title=" ".join(
                part
                for part in (
                    hit.company_name,
                    hit.doc_type,
                    " / ".join(hit.section_path[:2]),
                )
                if part
            ).strip(),
            text=hit.chunk_text,
            metadata={
                "company_code": hit.company_code,
                "company_name": hit.company_name,
                "doc_type": hit.doc_type,
                "publish_date": hit.publish_date,
            },
        )
        for index, hit in enumerate(truncated_hits)
    ]
    ranked_scores = resolved_reranker.rerank(
        query=normalized_query,
        profile="local_rag",
        candidates=candidates,
        top_n=top_n,
    )
    score_map = {
        str(result["id"]) if isinstance(result, Mapping) else result.id: result
        for result in ranked_scores
    }

    reranked: list[RerankedHit] = []
    for index, hit in enumerate(truncated_hits):
        score_entry = score_map.get(str(index))
        score = _read_score(score_entry)
        reranked.append(
            RerankedHit(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                parent_id=hit.parent_id,
                company_code=hit.company_code,
                company_name=hit.company_name,
                doc_type=hit.doc_type,
                report_year=hit.report_year,
                publish_date=hit.publish_date,
                page_start=hit.page_start,
                page_end=hit.page_end,
                page_anchor=hit.page_anchor,
                section_path=list(hit.section_path),
                chunk_text=hit.chunk_text,
                sparse_rank=hit.sparse_rank,
                dense_rank=hit.dense_rank,
                sparse_score=hit.sparse_score,
                dense_score=hit.dense_score,
                rrf_score=hit.rrf_score,
                rerank_score=score,
                matched_by=list(hit.matched_by),
            )
        )
    return sorted(
        reranked,
        key=lambda item: (item.rerank_score, item.rrf_score),
        reverse=True,
    )


def _read_score(score_entry: object) -> float:
    if score_entry is None:
        return 0.0
    if isinstance(score_entry, Mapping):
        return float(score_entry.get("score") or 0.0)
    return float(getattr(score_entry, "score", 0.0))
