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

from finsight_agent.capabilities.structured_data.models import MetricQuery, MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository


class MetricRepositoryTest(unittest.TestCase):
    def test_find_exact_time_scope_match(self) -> None:
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

            result = repository.find_best_match(
                MetricQuery(
                    company_name="宁德时代",
                    metric_name="net_profit",
                    time_scope="2024_annual",
                )
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.value, "507.45")

    def test_find_latest_returns_latest_available_period(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(storage_dir=temp_dir)
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="revenue",
                        metric_label="营业收入",
                        time_scope="2023_annual",
                        period_end="2023-12-31",
                        value="400.92",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_2023",
                        source_table_id="table_2023",
                        source_caption="主要会计数据",
                        confidence="high",
                    ),
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="revenue",
                        metric_label="营业收入",
                        time_scope="2024_annual",
                        period_end="2024-12-31",
                        value="512.30",
                        unit="亿元",
                        currency="CNY",
                        source_type="local_filing_table",
                        source_document_id="doc_2024",
                        source_table_id="table_2024",
                        source_caption="主要会计数据",
                        confidence="high",
                    ),
                ]
            )

            result = repository.find_best_match(
                MetricQuery(
                    company_name="宁德时代",
                    metric_name="revenue",
                    time_scope="latest",
                )
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.time_scope, "2024_annual")


if __name__ == "__main__":
    unittest.main()
