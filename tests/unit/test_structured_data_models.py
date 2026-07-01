from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.models import (
    MetricLookupResult,
    MetricQuery,
    MetricRecord,
)


class StructuredDataModelsTest(unittest.TestCase):
    def test_metric_query_defaults_to_allow_external_fallback(self) -> None:
        query = MetricQuery(
            company_name="宁德时代",
            metric_name="net_profit",
            time_scope="2024_annual",
        )

        self.assertEqual(query.company_name, "宁德时代")
        self.assertTrue(query.allow_external_fallback)

    def test_metric_record_keeps_source_trace_fields(self) -> None:
        record = MetricRecord(
            company_name="宁德时代",
            company_code="300750",
            metric_name="net_profit",
            metric_label="归属于上市公司股东的净利润",
            time_scope="2024_annual",
            period_end="2024-12-31",
            value="507.45",
            unit="亿元",
            currency="CNY",
            source_type="local_filing_table",
            source_document_id="300750_annual_report_2024_20250315",
            source_table_id="table_000001",
            source_caption="主要会计数据",
            confidence="high",
        )

        self.assertEqual(record.source_type, "local_filing_table")
        self.assertEqual(record.source_table_id, "table_000001")

    def test_metric_lookup_result_supports_degraded_response(self) -> None:
        result = MetricLookupResult.degraded(
            company_name="宁德时代",
            metric_name="revenue",
            time_scope="2025_annual",
            notes=["当前未找到对应期间数据"],
        )

        self.assertTrue(result.is_degraded)
        self.assertEqual(result.value, "")
        self.assertIn("当前未找到对应期间数据", result.notes)


if __name__ == "__main__":
    unittest.main()
