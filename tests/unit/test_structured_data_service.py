from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.models import MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.capabilities.structured_data.service import StructuredDataService


class StructuredDataServiceTest(unittest.TestCase):
    def test_query_metric_lookup_reads_local_metric_record_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(storage_dir=temp_dir)
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="net_profit",
                        metric_label="归母净利润",
                        time_scope="2024_annual",
                        period_end="2024-12-31",
                        value="507.45",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_001",
                        source_table_id="table_001",
                        source_caption="主要会计数据",
                        confidence="high",
                    )
                ]
            )
            service = StructuredDataService(metric_repository=repository)

            result = service.query_metric_lookup(
                company="宁德时代",
                metric="net_profit",
                time_scope="2024_annual",
            )

        self.assertEqual(result["value"], "507.45")
        self.assertEqual(result["source_type"], "local_filing_table")
        self.assertFalse(result["is_degraded"])

    def test_query_metric_lookup_returns_degraded_result_when_no_source_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = StructuredDataService(
                metric_repository=MetricRepository(storage_dir=temp_dir)
            )
            result = service.query_metric_lookup(
                company="宁德时代",
                metric="operating_cash_flow",
                time_scope="2025_annual",
            )

        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["value"], "")
        self.assertIn("当前未找到对应指标数据", result["notes"])


if __name__ == "__main__":
    unittest.main()
