from __future__ import annotations

from .models import DenseHit, FusedHit, SparseChunkHit


def rrf_fuse(
    sparse_hits: list[SparseChunkHit],
    dense_hits: list[DenseHit],
    rank_constant: int = 60,
) -> list[FusedHit]:
    """按 chunk_id 做 RRF 融合，保留 sparse / dense 排名信息。"""

    fused: dict[str, FusedHit] = {}

    for index, hit in enumerate(sparse_hits, start=1):
        chunk = fused.get(hit.chunk_id)
        score = 1.0 / (rank_constant + index)
        if chunk is None:
            chunk = FusedHit(
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
            )
            fused[hit.chunk_id] = chunk
        chunk.sparse_rank = index
        chunk.sparse_score = hit.bm25_score
        chunk.rrf_score += score
        if "sparse" not in chunk.matched_by:
            chunk.matched_by.append("sparse")

    for index, hit in enumerate(dense_hits, start=1):
        chunk = fused.get(hit.chunk_id)
        score = 1.0 / (rank_constant + index)
        if chunk is None:
            chunk = FusedHit(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                parent_id=hit.parent_id,
                company_code=hit.company_code,
                company_name=hit.company_name,
                doc_type=hit.doc_type,
                report_year=str(hit.report_year),
                publish_date=hit.publish_date,
                page_start=hit.page_start,
                page_end=hit.page_end,
                page_anchor=hit.page_anchor,
                section_path=list(hit.section_path),
                chunk_text=hit.chunk_text,
            )
            fused[hit.chunk_id] = chunk
        chunk.dense_rank = index
        chunk.dense_score = hit.dense_score
        chunk.rrf_score += score
        if "dense" not in chunk.matched_by:
            chunk.matched_by.append("dense")

    return sorted(fused.values(), key=lambda item: item.rrf_score, reverse=True)
