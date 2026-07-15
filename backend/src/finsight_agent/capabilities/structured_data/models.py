from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MetricQuery:
    """结构化指标查询的内部标准对象。"""

    company_name: str
    metric_name: str
    time_scope: str
    allow_external_fallback: bool = True
    # 归一化前的原始中文 metric（如"净利润"），用于精确未命中时做 metric_label LIKE 兜底
    metric_label_raw: str = ""
    # 6 位 A 股代码（新格式 router 输出），DB 用 company_code 精确匹配；
    # 空字符串则 fallback 到 company_name LIKE 匹配
    company_code: str = ""
    # period_end 日期（YYYY-MM-DD），新格式 router 输出，DB 用 period_end 字段精确匹配；
    # 空字符串或 "latest" 走最新报告期排序
    period_end: str = ""


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
    # 报表口径：consolidated（合并）/ parent_only（母公司）/ unknown
    statement_type: str = "unknown"
    # 来源章节：balance_sheet/income_statement/cash_flow_statement/notes/equity_statement/unknown
    # 用于查询时区分三表 vs 注释表，避免同名 key 碰撞
    source_section: str = "unknown"


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
