from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.builder import StructuredMetricIndexBuilder
from finsight_agent.capabilities.structured_data.repository import MetricRepository


class MetricBuilderTest(unittest.TestCase):
    def test_rebuild_reads_tables_jsonl_and_writes_metric_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parsed_root = Path(temp_dir) / "parsed"
            storage_root = Path(temp_dir) / "metric_store"
            filing_dir = parsed_root / "300750_宁德时代" / "annual" / "2024"
            filing_dir.mkdir(parents=True)

            (filing_dir / "document.json").write_text(
                json.dumps(
                    {
                        "document_id": "300750_annual_report_2024_20250315",
                        "company_name": "宁德时代",
                        "company_code": "300750",
                        "doc_type": "annual_report",
                        "report_year": 2024,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (filing_dir / "tables.jsonl").write_text(
                json.dumps(
                    {
                        "table_id": "table_001",
                        "document_id": "300750_annual_report_2024_20250315",
                        "page_start": 12,
                        "page_end": 12,
                        "order_in_document": 1,
                        "section_path": ["第二节 公司简介和主要财务指标"],
                        "caption_text": "主要会计数据",
                        "table_text": "营业收入 512.30",
                        "table_markdown": "| 指标 | 2024年 |\n| --- | --- |\n| 营业收入 | 512.30 |",
                        "parser_source": "pdfplumber",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            builder = StructuredMetricIndexBuilder(
                parsed_filings_root=parsed_root,
                storage_dir=storage_root,
            )
            builder.rebuild()
            records = MetricRepository(storage_dir=storage_root).load_records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].metric_name, "revenue")


if __name__ == "__main__":
    unittest.main()
