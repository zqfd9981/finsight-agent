from __future__ import annotations

from finsight_agent.capabilities.retrieval.parsing_models import ParsedTable

from .models import MetricRecord
from .normalizer import normalize_metric_name, normalize_numeric_text, normalize_time_scope


class MetricExtractor:
    """从财报表格中提取首版核心指标。"""

    def extract_from_tables(
        self,
        *,
        company_name: str,
        company_code: str,
        doc_type: str,
        report_year: int,
        tables: list[ParsedTable],
    ) -> list[MetricRecord]:
        time_scope = normalize_time_scope(doc_type=doc_type, report_year=report_year)
        period_end = (
            f"{report_year}-12-31" if doc_type == "annual_report" else f"{report_year}-06-30"
        )
        records: list[MetricRecord] = []

        for table in tables:
            rows = _parse_markdown_rows(table.table_markdown)
            for cells in rows:
                if len(cells) < 2:
                    continue
                metric_label = cells[0]
                metric_name = normalize_metric_name(metric_label)
                if metric_name is None:
                    continue
                value = normalize_numeric_text(cells[1])
                records.append(
                    MetricRecord(
                        company_name=company_name,
                        company_code=company_code,
                        metric_name=metric_name,
                        metric_label=metric_label,
                        time_scope=time_scope,
                        period_end=period_end,
                        value=value,
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id=table.document_id,
                        source_table_id=table.table_id,
                        source_caption=table.caption_text,
                        confidence="high",
                    )
                )

        return records


def _parse_markdown_rows(markdown: str) -> list[list[str]]:
    """把最基础的 Markdown 表格文本拆成行单元。"""

    rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if all(set(cell) <= {"-"} for cell in cells if cell):
            continue
        if cells[0] == "指标":
            continue
        rows.append(cells)
    return rows
