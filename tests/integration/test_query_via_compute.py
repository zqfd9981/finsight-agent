"""路径② query_via_compute 集成测试：取数 + Python 计算。

覆盖 TODO Tier 1b 的核心场景：聚合(avg)、增长(yoy/cagr)、连续增长(consecutive)，
以及数据不足/词表未命中的降级（返回 None 回落 Assembler）。
"""
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

from finsight_agent.capabilities.structured_data.compute_intent import detect_compute_intent  # noqa: E402
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer  # noqa: E402
from finsight_agent.capabilities.structured_data.models import ComputePlan, MetricRecord  # noqa: E402
from finsight_agent.capabilities.structured_data.repository import MetricRepository  # noqa: E402
from finsight_agent.capabilities.structured_data.service import StructuredDataService  # noqa: E402

_ALIASES_PATH = REPO_ROOT / "var" / "data" / "structured_data" / "metric_aliases.json"


def _record(**overrides) -> MetricRecord:
    defaults = dict(
        company_name="宁德时代", company_code="300750", metric_name="net_profit",
        metric_label="净利润", time_scope="期末余额", period_end="2024-12-31",
        value="441.21", unit="亿元", currency="CNY",
        source_type="annual_report", source_document_id="doc_001",
        source_table_id="table_001", source_caption="主要会计数据",
        confidence="high", statement_type="consolidated", source_section="income_statement",
    )
    defaults.update(overrides)
    return MetricRecord(**defaults)


class QueryViaComputeIntegrationTest(unittest.TestCase):
    """路径② 取数+计算集成测试。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._db_path = Path(self._tmp.name) / "metrics.db"
        self._repo = MetricRepository(sqlite_path=self._db_path)
        self._normalizer = MetricNormalizer(aliases_path=_ALIASES_PATH)
        self._service = StructuredDataService(
            metric_repository=self._repo, normalizer=self._normalizer
        )

    def _save(self, records: list[MetricRecord]) -> None:
        self._repo.save_records(records)

    def _plan(self, **kw) -> ComputePlan:
        defaults = dict(
            op="avg", metric="net_profit", metric_raw="净利润",
            companies=["300750"], company_names=["宁德时代"],
            periods=["2024-12-31"], years=0,
        )
        defaults.update(kw)
        return ComputePlan(**defaults)

    # ---- 聚合 ----

    def test_avg_across_all_companies(self) -> None:
        """所有公司净利润平均值：plan.companies 空 → service 用 None 全公司。"""
        self._save([
            _record(company_name="A", company_code="000001", value="100", unit="亿元"),
            _record(company_name="B", company_code="000002", value="200", unit="亿元"),
            _record(company_name="C", company_code="000003", value="300", unit="亿元"),
        ])
        plan = self._plan(op="avg", companies=[], company_names=[],
                          periods=["2024-12-31"])
        result = self._service.query_via_compute(plan)
        self.assertIsNotNone(result)
        self.assertEqual(result.via, "compute")
        self.assertEqual(result.kind, "aggregate")
        self.assertEqual(result.rows[0]["value"], 200.0)
        self.assertEqual(len(result.underlying_records), 3)

    def test_sum_single_company_multi_period(self) -> None:
        self._save([
            _record(period_end="2023-12-31", value="100"),
            _record(period_end="2024-12-31", value="200"),
        ])
        plan = self._plan(op="sum", periods=["2023-12-31", "2024-12-31"])
        result = self._service.query_via_compute(plan)
        self.assertIsNotNone(result)
        self.assertEqual(result.rows[0]["value"], 300.0)

    # ---- 增长 ----

    def test_yoy(self) -> None:
        self._save([
            _record(period_end="2023-12-31", value="100"),
            _record(period_end="2024-12-31", value="120"),
        ])
        plan = self._plan(op="yoy", periods=["2023-12-31", "2024-12-31"])
        result = self._service.query_via_compute(plan)
        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "growth")
        self.assertEqual(result.rows[0]["value"], 20.0)

    def test_cagr_three_years(self) -> None:
        # 3 年 CAGR：100 → 133.1 over 3 years = 10%
        self._save([
            _record(period_end="2021-12-31", value="100"),
            _record(period_end="2022-12-31", value="110"),
            _record(period_end="2023-12-31", value="121"),
            _record(period_end="2024-12-31", value="133.1"),
        ])
        plan = self._plan(op="cagr", years=3,
                          periods=["2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31"])
        result = self._service.query_via_compute(plan)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.rows[0]["value"], 10.0, places=2)

    def test_consecutive_growth_true(self) -> None:
        self._save([
            _record(period_end="2022-12-31", value="100"),
            _record(period_end="2023-12-31", value="110"),
            _record(period_end="2024-12-31", value="121"),
        ])
        plan = self._plan(op="consecutive_growth", years=2,
                          periods=["2022-12-31", "2023-12-31", "2024-12-31"])
        result = self._service.query_via_compute(plan)
        self.assertIsNotNone(result)
        self.assertEqual(result.kind, "consecutive")
        self.assertEqual(result.rows[0]["value"], "是")

    # ---- 降级 ----

    def test_insufficient_data_returns_none(self) -> None:
        """CAGR 数据不足 → None，stage runner 回落 Assembler 返回原始行。"""
        self._save([_record(period_end="2024-12-31", value="100")])
        plan = self._plan(op="cagr", years=3, periods=["2024-12-31"])
        result = self._service.query_via_compute(plan)
        self.assertIsNone(result)

    def test_metric_not_in_vocab_returns_none(self) -> None:
        """metric key 不在受控词表 → None（不让坏 key 进计算）。"""
        plan = self._plan(op="avg", metric="bogus_metric_xyz", metric_raw="假指标")
        result = self._service.query_via_compute(plan)
        self.assertIsNone(result)

    def test_empty_db_returns_none(self) -> None:
        plan = self._plan(op="avg")
        result = self._service.query_via_compute(plan)
        self.assertIsNone(result)

    # ---- 端到端：compute_intent → query_via_compute ----

    def test_end_to_end_avg_via_intent(self) -> None:
        """从 query 文本 → detect_compute_intent → query_via_compute 全链路。"""
        self._save([
            _record(company_name="A", company_code="000001", value="100"),
            _record(company_name="B", company_code="000002", value="300"),
        ])
        entities = {
            "company": [],  # "所有公司"
            "metric": [{"standard_name": "net_profit", "raw": "净利润", "metric_type": "direct"}],
            "time_scope": [{"raw": "2024年", "period_end": "2024-12-31", "fiscal_year": 2024}],
        }
        plan = detect_compute_intent("所有公司2024净利润平均值", entities)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.op, "avg")
        result = self._service.query_via_compute(plan)
        self.assertIsNotNone(result)
        self.assertEqual(result.rows[0]["value"], 200.0)


if __name__ == "__main__":
    unittest.main()
