from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for _candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from finsight_agent.control_plane.orchestrator.models import StageExecutionResult
from finsight_agent.control_plane.orchestrator.stage_runners.reflect_and_requery import (
    run_reflect_and_requery_stage,
)
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName


class _FakeLlmClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def complete_json(self, *, prompt_name, variables):
        self.calls += 1
        return self._payload


class _FakeStructuredData:
    def __init__(self, lookup_result):
        self._r = dict(lookup_result)

    def query_metric_lookup(self, company, metric, time_scope):
        return dict(self._r)


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        query="贵州茅台 2024 年毛利率", query_mode="first_turn", session_id="s1"
    )


def _router_result() -> RouterResult:
    return RouterResult(
        intent="metric_lookup",
        follow_up_type="none",
        confidence="high",
        entities={},
        needs=[],
        constraints={},
    )


class ReflectAndRequeryTest(unittest.TestCase):
    def test_noop_when_not_degraded(self) -> None:
        qsd = StageExecutionResult(
            stage_name=StageName.QUERY_STRUCTURED_DATA.value,
            status="success",
            output_payload={
                "structured_result": {
                    "company": "贵州茅台",
                    "metric": "毛利率",
                    "is_degraded": False,
                }
            },
        )
        execution_state = {StageName.QUERY_STRUCTURED_DATA.value: qsd}
        result = run_reflect_and_requery_stage(
            request=_request(),
            router_result=_router_result(),
            execution_state=execution_state,
            structured_data_service=_FakeStructuredData({"value": "1", "unit": "亿"}),
            llm_client=_FakeLlmClient({"need_requery": True}),
        )
        self.assertFalse(result.output_payload["need_requery"])
        self.assertEqual(result.output_payload["ingredient_results"], [])
        # 未降级时不应触发 LLM 反思
        self.assertEqual(result.status, "success")

    def test_noop_when_llm_unavailable(self) -> None:
        qsd = StageExecutionResult(
            stage_name=StageName.QUERY_STRUCTURED_DATA.value,
            status="success",
            output_payload={
                "structured_result": {
                    "company": "贵州茅台",
                    "metric": "毛利率",
                    "is_degraded": True,
                }
            },
        )
        execution_state = {StageName.QUERY_STRUCTURED_DATA.value: qsd}
        # 无 llm_client：保持降级，不抛出
        result = run_reflect_and_requery_stage(
            request=_request(),
            router_result=_router_result(),
            execution_state=execution_state,
            structured_data_service=_FakeStructuredData({"value": "1"}),
            llm_client=None,
        )
        self.assertFalse(result.output_payload["need_requery"])
        self.assertEqual(result.output_payload["ingredient_results"], [])

    def test_requery_ingredients_when_degraded(self) -> None:
        qsd = StageExecutionResult(
            stage_name=StageName.QUERY_STRUCTURED_DATA.value,
            status="success",
            output_payload={
                "structured_result": {
                    "company": "贵州茅台",
                    "metric": "毛利率",
                    "is_degraded": True,
                }
            },
        )
        execution_state = {StageName.QUERY_STRUCTURED_DATA.value: qsd}
        llm = _FakeLlmClient(
            {
                "need_requery": True,
                "ingredient_metrics": ["revenue", "operating_cost"],
                "reasoning": "毛利率需营收与营业成本",
            }
        )
        sds = _FakeStructuredData({"value": "100", "unit": "亿元", "is_degraded": False})
        result = run_reflect_and_requery_stage(
            request=_request(),
            router_result=_router_result(),
            execution_state=execution_state,
            structured_data_service=sds,
            llm_client=llm,
        )
        ingredients = result.output_payload["ingredient_results"]
        self.assertEqual(len(ingredients), 2)
        self.assertTrue(result.output_payload["need_requery"])
        self.assertEqual(ingredients[0]["metric"], "revenue")


if __name__ == "__main__":
    unittest.main()
