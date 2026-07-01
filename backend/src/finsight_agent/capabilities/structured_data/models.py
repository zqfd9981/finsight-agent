from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MetricQuery:
    """结构化指标查询的内部标准对象。"""

    company_name: str
    metric_name: str
    time_scope: str
    allow_external_fallback: bool = True


@dataclass(slots=True)
class MetricRecord:
    """本地指标库中的标准记录。"""

    company_name: str
    company_code: str
    metric_name: str
    metric_label: str
    time_scope: str
    period_end: str
    value: str
    unit: str
    currency: str
    source_type: str
    source_document_id: str
    source_table_id: str
    source_caption: str
    confidence: str


@dataclass(slots=True)
class MetricLookupResult:
    """统一结构化指标查询结果。"""

    company_name: str
    metric_name: str
    time_scope: str
    value: str
    unit: str
    source_type: str
    source_summary: str
    matched_by: str
    confidence: str
    is_degraded: bool = False
    notes: list[str] = field(default_factory=list)

    @classmethod
    def degraded(
        cls,
        *,
        company_name: str,
        metric_name: str,
        time_scope: str,
        notes: list[str],
    ) -> "MetricLookupResult":
        return cls(
            company_name=company_name,
            metric_name=metric_name,
            time_scope=time_scope,
            value="",
            unit="",
            source_type="unavailable",
            source_summary="",
            matched_by="none",
            confidence="low",
            is_degraded=True,
            notes=notes,
        )
