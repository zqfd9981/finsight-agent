"""stage runner 端到端：compute 路径接线（detect_compute_intent → query_via_compute → ComputedResult）。

绕过 router LLM，直接喂 RouterResult(intent=metric_lookup) 给 stage runner，
验证 Tier 1b 在 stage 层的正确接入：compute 命中走 ComputedResult，不命中回落 Assembler。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for _p in (str(REPO_ROOT), str(BACKEND_SRC_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer  # noqa: E402
from finsight_agent.capabilities.structured_data.models import MetricRecord  # noqa: E402
from finsight_agent.capabilities.structured_data.repository import MetricRepository  # noqa: E402
from finsight_agent.capabilities.structured_data.service import StructuredDataService  # noqa: E402
from finsight_agent.control_plane.orchestrator.stage_runners.query_structured_data import (  # noqa: E402
    run_query_structured_data_stage,
)
from shared.contracts.analysis_request import AnalysisRequest  # noqa: E402
from shared.contracts.router_result import RouterResult  # noqa: E402

_ALIASES_PATH = REPO_ROOT / "var" / "data" / "structured_data" / "metric_aliases.json"


def _record(company, code, value) -> MetricRecord:
    return MetricRecord(
        company_name=company, company_code=code, metric_name="net_profit",
        metric_label="净利润", time_scope="期末余额", period_end="2024-12-31",
        value=value, unit="亿元", currency="CNY", source_type="annual_report",
        source_document_id="d", source_table_id="t", source_caption="c",
        confidence="high", statement_type="consolidated", source_section="income_statement",
    )


class ComputeStageRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._db_path = Path(self._tmp.name) / "metrics.db"
        self._repo = MetricRepository(sqlite_path=self._db_path)
        self._normalizer = MetricNormalizer(aliases_path=_ALIASES_PATH)
        self._service = StructuredDataService(
            metric_repository=self._repo, normalizer=self._normalizer
        )

    def _run(self, query: str, entities: dict):
        request = AnalysisRequest(query=query, session_id="test")
        router_result = RouterResult(intent="metric_lookup", entities=entities)
        result = run_query_structured_data_stage(
            request=request,
            router_result=router_result,
            stage_constraints={},
            execution_state={},
            structured_data_service=self._service,
        )
        return dict(result.output_payload.get("structured_result", {}))

    def test_compute_avg_hits_computed_path(self) -> None:
        """含'平均'关键词 → 走 compute 路径，via=compute。"""
        self._repo.save_records([
            _record("A公司", "000001", "100"),
            _record("B公司", "000002", "300"),
        ])
        entities = {
            "company": [],  # 所有公司
            "metric": [{"standard_name": "net_profit", "raw": "净利润", "metric_type": "direct"}],
            "time_scope": [{"raw": "2024年", "period_end": "2024-12-31", "fiscal_year": 2024}],
        }
        structured = self._run("所有公司2024净利润平均值", entities)
        self.assertTrue(structured.get("computed"))
        self.assertEqual(structured.get("via"), "compute")
        self.assertEqual(structured["rows"][0]["value"], 200.0)

    def test_no_compute_keyword_falls_through_to_assembler(self) -> None:
        """无计算关键词 → compute 不命中，回落 Assembler 主路径（行形状）。"""
        self._repo.save_records([
            _record("A公司", "000001", "100"),
            _record("B公司", "000002", "300"),
        ])
        entities = {
            "company": [{"standard_name": "A公司", "raw": "A公司", "stock_code": "000001"},
                        {"standard_name": "B公司", "raw": "B公司", "stock_code": "000002"}],
            "metric": [{"standard_name": "net_profit", "raw": "净利润", "metric_type": "direct"}],
            "time_scope": [{"raw": "2024年", "period_end": "2024-12-31", "fiscal_year": 2024}],
        }
        structured = self._run("A公司和B公司2024净利润分别是多少", entities)
        self.assertNotIn("computed", structured)  # 不是 compute 结果
        self.assertEqual(structured.get("via"), "assembler")
        self.assertTrue(structured.get("is_multi"))

    def test_compute_insufficient_data_falls_through(self) -> None:
        """CAGR 数据不足 → query_via_compute 返回 None → 回落 Assembler 返回原始行。"""
        self._repo.save_records([_record("A公司", "000001", "100")])
        entities = {
            "company": [{"standard_name": "A公司", "raw": "A公司", "stock_code": "000001"}],
            "metric": [{"standard_name": "net_profit", "raw": "净利润", "metric_type": "direct"}],
            "time_scope": [{"raw": "2024年", "period_end": "2024-12-31", "fiscal_year": 2024}],
        }
        # CAGR 但只有 1 期数据 → compute 降级 → assembler 返回该行
        structured = self._run("A公司近3年净利润复合增长率", entities)
        # compute 不命中（数据不足），回落 assembler
        self.assertNotIn("computed", structured)


if __name__ == "__main__":
    unittest.main()
