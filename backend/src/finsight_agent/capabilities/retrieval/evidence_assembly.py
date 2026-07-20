from __future__ import annotations

from .citation_builder import build_citation_record, build_parent_context
from .models import EvidenceItem, RerankedHit, RetrievalScoreBreakdown
from .parent_context_loader import ParentChunkRecord


def assemble_evidence_item(
    rank: int,
    hit: RerankedHit,
    parent_record: ParentChunkRecord | None,
) -> tuple[EvidenceItem, bool]:
    """把单条 reranked hit 组装成对外 EvidenceItem。"""

    used_fallback = parent_record is None
    parent_context = (
        parent_record.chunk_text
        if parent_record is not None
        else build_parent_context(hit.chunk_text)
    )

    evidence = EvidenceItem(
        evidence_id=f"evidence_{rank:04d}",
        rank=rank,
        support_strength=classify_support_strength(hit),
        matched_chunk_id=hit.chunk_id,
        matched_parent_id=hit.parent_id,
        excerpt=_normalize_excerpt(hit.chunk_text),
        parent_context=parent_context,
        citation=build_citation_record(
            document_id=hit.document_id,
            page_start=hit.page_start,
            page_end=hit.page_end,
            page_anchor=hit.page_anchor,
        ),
        retrieval_scores=RetrievalScoreBreakdown(
            sparse_score=hit.sparse_score,
            dense_score=hit.dense_score,
            rrf_score=hit.rrf_score,
            rerank_score=hit.rerank_score,
        ),
        company_code=hit.company_code,
        company_name=hit.company_name,
        doc_type=hit.doc_type,
        section_path=list(hit.section_path),
        report_year=str(hit.report_year or ""),
    )
    return evidence, used_fallback


def classify_support_strength(hit: RerankedHit) -> str:
    """显式分层支持度，便于后续独立调整阈值。"""

    rerank_score = hit.rerank_score
    dense_score = hit.dense_score if hit.dense_score is not None else 0.0
    sparse_score = hit.sparse_score if hit.sparse_score is not None else 0.0

    if rerank_score >= 0.85 and (dense_score >= 0.65 or sparse_score >= 2.5):
        return "strong"
    if rerank_score >= 0.6 and (dense_score >= 0.35 or sparse_score >= 1.2):
        return "partial"
    if rerank_score >= 0.08 or dense_score >= 0.08 or sparse_score >= 0.2:
        return "weak"
    return "unsupported"


def _normalize_excerpt(chunk_text: str) -> str:
    """把命中 child 文本压成更适合直接展示的摘要片段。"""

    return " ".join(chunk_text.split())
