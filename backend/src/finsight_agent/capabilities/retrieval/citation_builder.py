from __future__ import annotations

from .models import CitationRecord


def build_citation_record(
    document_id: str,
    page_start: int,
    page_end: int,
    page_anchor: int | None,
) -> CitationRecord:
    """构造最小 citation 结构。"""

    return CitationRecord(
        document_id=document_id,
        page_start=page_start,
        page_end=page_end,
        page_anchor=page_anchor,
    )


def build_parent_context(chunk_text: str, max_chars: int = 180) -> str:
    """首版先用摘要截断模拟 parent expand 的上下文。"""

    normalized = chunk_text.strip()
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()}..."
