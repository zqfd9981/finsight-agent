from __future__ import annotations

from typing import TypeAlias, TypedDict


class EvidenceOverviewItem(TypedDict):
    evidence_id: str
    excerpt: str
    company_name: str
    doc_type: str


class EvidenceOverviewBlock(TypedDict):
    block_type: str
    title: str
    items: list[EvidenceOverviewItem]


ReportBlock: TypeAlias = EvidenceOverviewBlock
