from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.parsing_models import ParsedTable
from finsight_agent.capabilities.structured_data.extractor import MetricExtractor


class MetricExtractorTest(unittest.TestCase):
    def test_extract_annual_revenue_and_net_profit_from_main_financial_table(self) -> None:
        table = ParsedTable(
            table_id="table_001",
            document_id="300750_annual_report_2024_20250315",
            page_start=12,
            page_end=12,
            order_in_document=1,
            section_path=["第二节 公司简介和主要财务指标"],
            caption_text="主要会计数据",
            table_text="营业收入 512.30 归属于上市公司股东的净利润 507.45",
            table_markdown=(
                "| 指标 | 2024年 | 2023年 |\n"
                "| 营业收入 | 512.30 | 400.92 |\n"
                "| 归属于上市公司股东的净利润 | 507.45 | 441.21 |"
            ),
            parser_source="pdfplumber",
        )

        records = MetricExtractor().extract_from_tables(
            company_name="宁德时代",
            company_code="300750",
            doc_type="annual_report",
            report_year=2024,
            tables=[table],
        )

        self.assertEqual(
            {record.metric_name for record in records},
            {"revenue", "net_profit"},
        )
        self.assertEqual(records[0].time_scope, "2024_annual")
        revenue_record = next(record for record in records if record.metric_name == "revenue")
        self.assertEqual(revenue_record.value, "512.30")
        self.assertEqual(revenue_record.source_table_id, "table_001")


if __name__ == "__main__":
    unittest.main()
