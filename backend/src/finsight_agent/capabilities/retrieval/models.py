from __future__ import annotations

from dataclasses import dataclass, field


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
