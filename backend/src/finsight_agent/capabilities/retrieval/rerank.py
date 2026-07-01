from __future__ import annotations

from .models import FusedHit, RerankedHit


def rerank_hits(
    hits: list[FusedHit],
    query_text: str,
    top_n: int = 20,
) -> list[RerankedHit]:
    """对融合后的 top N child chunks 做轻量精排。"""

    normalized_query = query_text.strip()
    if not normalized_query:
        return []

    reranked: list[RerankedHit] = []
    for hit in hits[:top_n]:
        score = _compute_overlap_score(normalized_query, hit.chunk_text)
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


def _compute_overlap_score(query_text: str, chunk_text: str) -> float:
    """用字符集合重叠做首版轻量 rerank 分数。"""

    query_chars = {character for character in query_text if not character.isspace()}
    if not query_chars:
        return 0.0
    chunk_chars = {character for character in chunk_text if not character.isspace()}
    overlap = query_chars & chunk_chars
    return len(overlap) / len(query_chars)
