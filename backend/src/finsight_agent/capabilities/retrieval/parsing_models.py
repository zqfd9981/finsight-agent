from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ParsedElement:
    """标准化后的结构元素。"""

    element_id: str
    document_id: str
    element_type: str
    page_start: int
    page_end: int
    order_in_document: int
    section_path: list[str] = field(default_factory=list)
    text: str = ""
    parser_source: str = ""
    confidence: float | None = None
    bbox: dict[str, float] | None = None
    related_table_id: str | None = None


@dataclass(slots=True)
class ParsedTable:
    """标准化后的表格记录。"""

    table_id: str
    document_id: str
    page_start: int
    page_end: int
    order_in_document: int
    section_path: list[str] = field(default_factory=list)
    caption_text: str = ""
    table_text: str = ""
    table_markdown: str = ""
    parser_source: str = ""
    confidence: float | None = None
    bbox: dict[str, float] | None = None
    table_type_hint: str | None = None
    related_metric_hints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParseReport:
    """单份文档的解析过程报告。"""

    document_id: str
    status: str
    primary_parser: str
    parser_version: str
    fallback_used: bool
    fallback_parser: str | None = None
    page_count: int = 0
    parsed_element_count: int = 0
    parsed_table_count: int = 0
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0


@dataclass(slots=True)
class ParsedDocumentArtifact:
    """单份文档的解析产物聚合对象。"""

    document: dict[str, object]
    elements: list[ParsedElement] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    parse_report: ParseReport | None = None


@dataclass(slots=True)
class ChunkRecord:
    """父子块统一记录结构。"""

    chunk_id: str
    document_id: str
    chunk_level: str
    parent_id: str | None
    chunk_text: str
    page_start: int
    page_end: int
    page_anchor: int
    section_path: list[str] = field(default_factory=list)
    element_ids: list[str] = field(default_factory=list)
    order_in_document: int = 0
    source_parser: str = ""
    created_from_parser_version: str = ""


@dataclass(slots=True)
class ChunkReport:
    """单份文档的切块报告。"""

    document_id: str
    chunker_version: str
    parent_count: int
    child_count: int
    warnings: list[str] = field(default_factory=list)
    generated_at: str = ""
