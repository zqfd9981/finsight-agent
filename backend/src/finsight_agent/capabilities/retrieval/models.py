from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DenseSearchRequest:
    """Dense 语义检索的最小请求对象。"""

    query_text: str
    limit: int = 10
    company_code: str | None = None
    doc_type: str | None = None
    report_year: int | None = None


@dataclass(slots=True)
class DenseSearchFilters:
    """Dense 检索支持的最小 metadata 过滤条件。"""

    company_code: str | None = None
    doc_type: str | None = None
    report_year: int | None = None


@dataclass(slots=True)
class DenseHit:
    """Dense 检索命中的 child chunk 结果。"""

    chunk_id: str
    document_id: str
    parent_id: str
    company_code: str
    company_name: str
    doc_type: str
    report_year: int
    publish_date: str
    page_start: int
    page_end: int
    page_anchor: int | None
    section_path: list[str] = field(default_factory=list)
    chunk_text: str = ""
    dense_score: float = 0.0
    query_variant: str = "original"


@dataclass(slots=True)
class SparseSearchFilters:
    """SQLite FTS5 首版支持的最小 metadata 过滤条件。"""

    company_code: str | None = None
    doc_type: str | None = None


@dataclass(slots=True)
class SparseChunkHit:
    """稀疏检索命中的 child chunk 回表结果。"""

    chunk_id: str
    document_id: str
    parent_id: str | None
    company_code: str
    company_name: str
    doc_type: str
    report_year: str
    publish_date: str
    page_start: int
    page_end: int
    page_anchor: int
    section_path: list[str] = field(default_factory=list)
    chunk_text: str = ""
    bm25_score: float = 0.0


@dataclass(slots=True)
class FusedHit:
    """RRF 融合后的 child 命中结果。"""

    chunk_id: str
    document_id: str
    parent_id: str | None
    company_code: str
    company_name: str
    doc_type: str
    report_year: str
    publish_date: str
    page_start: int
    page_end: int
    page_anchor: int | None
    section_path: list[str] = field(default_factory=list)
    chunk_text: str = ""
    sparse_rank: int | None = None
    dense_rank: int | None = None
    sparse_score: float | None = None
    dense_score: float | None = None
    rrf_score: float = 0.0
    matched_by: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RerankedHit:
    """重排后的 child 命中结果。"""

    chunk_id: str
    document_id: str
    parent_id: str | None
    company_code: str
    company_name: str
    doc_type: str
    report_year: str
    publish_date: str
    page_start: int
    page_end: int
    page_anchor: int | None
    section_path: list[str] = field(default_factory=list)
    chunk_text: str = ""
    sparse_rank: int | None = None
    dense_rank: int | None = None
    sparse_score: float | None = None
    dense_score: float | None = None
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    matched_by: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RetrievalScoreBreakdown:
    """对外暴露的检索分数摘要。"""

    sparse_score: float | None = None
    dense_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


@dataclass(slots=True)
class CitationRecord:
    """证据引用定位。"""

    document_id: str
    page_start: int
    page_end: int
    page_anchor: int | None


@dataclass(slots=True)
class EvidenceItem:
    """对外返回的证据项。"""

    evidence_id: str
    rank: int
    support_strength: str
    matched_chunk_id: str
    matched_parent_id: str | None
    excerpt: str
    parent_context: str
    citation: CitationRecord
    retrieval_scores: RetrievalScoreBreakdown
    company_code: str
    company_name: str
    doc_type: str
    section_path: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RetrievalTrace:
    """检索链路追踪信息。"""

    original_query: str
    normalized_query: str
    rewrite_queries: list[str] = field(default_factory=list)
    sparse_hit_count: int = 0
    dense_hit_count: int = 0
    fused_hit_count: int = 0
    reranked_hit_count: int = 0
    final_evidence_count: int = 0
    sparse_rewrite_triggered: bool = False
    dense_rewrite_triggered: bool = False
    parent_expand_attempted: bool = False
    parent_expand_fallback_count: int = 0


@dataclass(slots=True)
class RetrievalResult:
    """统一的 retrieval facade 输出。"""

    request_id: str
    normalized_claim: str
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    retrieval_notes: list[str] = field(default_factory=list)
    retrieval_trace: RetrievalTrace | None = None
