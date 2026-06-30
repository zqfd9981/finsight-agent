from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SampleCompany:
    """样本股池中的单家公司记录。"""

    company_code: str
    company_name: str
    segment: str
    subsegment: str
    priority: str
    theme_tags: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(slots=True)
class FilingRecord:
    """统一后的披露文档元数据记录。"""

    source_name: str
    market: str
    company_code: str
    company_name: str
    title: str
    publish_date: str
    source_doc_type: str
    pdf_url: str
    announcement_id: str | None = None


@dataclass(slots=True)
class ClassifiedFiling:
    """标题筛选后的文档分类结果。"""

    normalized_doc_type: str
    announcement_type: str | None = None
    report_year: int | None = None
