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

from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.models import MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.capabilities.structured_data.service import StructuredDataService


class _StubExternalMetricProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def lookup_metric(
        self,
        company_name: str,
        metric_name: str,
        time_scope: str,
    ) -> dict[str, object] | None:
        self.calls.append((company_name, metric_name, time_scope))
        return {
            "company_name": company_name,
            "metric_name": metric_name,
            "time_scope": time_scope,
            "value": "520.01",
            "unit": "亿元",
            "source_type": "external_api",
            "source_summary": "stub_external_provider",
            "matched_by": "external_provider",
            "confidence": "medium",
            "is_degraded": False,
            "notes": ["结果来自外部指标接口"],
        }


class StructuredDataServiceTest(unittest.TestCase):
    def test_query_metric_lookup_reads_local_metric_record_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(sqlite_path=Path(temp_dir) / "metrics.db")
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="net_profit",
                        metric_label="归母净利润",
                        time_scope="期末余额",
                        period_end="2024-12-31",
                        value="507.45",
                        unit="亿元",
                        currency="CNY",
                        source_type="annual_report",
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
                time_scope="期末余额",
            )

        self.assertEqual(result["value"], "507.45")
        self.assertEqual(result["source_type"], "annual_report")
        self.assertFalse(result["is_degraded"])

    def test_query_metric_lookup_normalizes_chinese_metric_before_query(self) -> None:
        """路由返回中文'净利润'，normalizer 映射到英文 key 'net_profit' 后命中 SQLite。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = MetricRepository(sqlite_path=Path(temp_dir) / "metrics.db")
            repository.save_records(
                [
                    MetricRecord(
                        company_name="宁德时代",
                        company_code="300750",
                        metric_name="net_profit",
                        metric_label="净利润",
                        time_scope="期末余额",
                        period_end="2024-12-31",
                        value="507.45",
                        unit="亿元",
                        currency="CNY",
                        source_type="annual_report",
                        source_document_id="doc_001",
                        source_table_id="table_001",
                        source_caption="主要会计数据",
                        confidence="high",
                    )
                ]
            )
            normalizer = MetricNormalizer(
                aliases_path=Path(temp_dir) / "aliases.json",
            )
            service = StructuredDataService(
                metric_repository=repository,
                normalizer=normalizer,
            )

            result = service.query_metric_lookup(
                company="宁德时代",
                metric="净利润",
                time_scope="2024-12-31",
            )

        self.assertFalse(result.get("is_degraded", True))
        self.assertEqual(result["value"], "507.45")

    def test_query_metric_lookup_returns_degraded_result_when_no_source_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = StructuredDataService(
                metric_repository=MetricRepository(
                    sqlite_path=Path(temp_dir) / "metrics.db"
                )
            )
            result = service.query_metric_lookup(
                company="宁德时代",
                metric="operating_cash_flow",
                time_scope="期末余额",
            )

        self.assertTrue(result["is_degraded"])
        self.assertEqual(result["value"], "")
        self.assertIn("当前未找到对应指标数据", result["notes"])

    def test_query_metric_lookup_uses_external_provider_after_local_miss(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            provider = _StubExternalMetricProvider()
            service = StructuredDataService(
                metric_repository=MetricRepository(
                    sqlite_path=Path(temp_dir) / "metrics.db"
                ),
                external_provider=provider,
            )

            result = service.query_metric_lookup(
                company="宁德时代",
                metric="revenue",
                time_scope="期末余额",
            )

        self.assertEqual(result["source_type"], "external_api")
        self.assertEqual(
            provider.calls,
            [("宁德时代", "revenue", "期末余额")],
        )


if __name__ == "__main__":
    unittest.main()
