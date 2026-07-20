from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, "backend/src")

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.control_plane.orchestrator.models import StageExecutionResult
from finsight_agent.control_plane.orchestrator.stage_runners.synthesize_answer import (
    run_synthesize_answer_stage,
)
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.stage_name import StageName

# 用固化 JSON 让 brief writer 走无网路径，避免单测触碰 LLM。
_BRIEF_FIXTURE = '{"answer_markdown":"毛利率约 40%。","answer_confidence":"medium"}'


def _build_request(session_id: str = "sess_recovery") -> AnalysisRequest:
    return AnalysisRequest(
        query="某公司的毛利率是多少",
        session_id=session_id,
    )


def _build_router_result() -> RouterResult:
    return RouterResult(
        intent="metric_lookup",
        follow_up_type="none",
        confidence="high",
        entities={
            "company": "Foo",
            "metric": {"raw": "毛利率"},
            "time_scope": "2024",
        },
        needs=["structured_data"],
        constraints={},
    )


def _degraded_structured_result() -> dict:
    return {
        "company": "Foo",
        "metric": "gross_margin",
        "time_scope": "2024",
        "is_degraded": True,
        "notes": ["暂无直接数据"],
    }


class SynthesizeBriefRecoverySummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["FINSIGHT_BRIEF_ANSWER_JSON"] = _BRIEF_FIXTURE

    def tearDown(self) -> None:
        os.environ.pop("FINSIGHT_BRIEF_ANSWER_JSON", None)

    def _run(self, reflect_payload: dict) -> str:
        execution_state = {
            StageName.QUERY_STRUCTURED_DATA.value: StageExecutionResult(
                stage_name=StageName.QUERY_STRUCTURED_DATA.value,
                status="success",
                output_payload={"structured_result": _degraded_structured_result()},
            ),
            StageName.REFLECT_AND_REQUERY.value: StageExecutionResult(
                stage_name=StageName.REFLECT_AND_REQUERY.value,
                status="success",
                output_payload=reflect_payload,
            ),
        }
        result = run_synthesize_answer_stage(
            request=_build_request(),
            router_result=_build_router_result(),
            stage_constraints={
                "response_mode": "brief_answer",
                "preferred_output": "brief_answer",
            },
            execution_state=execution_state,
            reporting_service=ReportingService(),
        )
        return result.output_payload["final_response"].summary

    def test_degraded_with_usable_ingredients_does_not_claim_miss(self) -> None:
        summary = self._run(
            {
                "ingredient_results": [
                    {"metric": "revenue", "value": "100", "unit": "亿元", "is_degraded": False},
                    {"metric": "operating_cost", "value": "60", "unit": "亿元", "is_degraded": False},
                ],
            }
        )
        # 关键断言：恢复成功时 summary 不得误报"未命中"，应标注"推导"
        self.assertNotIn("暂未命中", summary)
        self.assertNotIn("未找到对应指标数据", summary)
        self.assertIn("推导", summary)

    def test_degraded_with_ingredients_but_all_degraded_still_claims_miss(self) -> None:
        # 原料补查到但自身也降级 → 视为未成功恢复，summary 仍如实标注"未命中"
        summary = self._run(
            {
                "ingredient_results": [
                    {"metric": "revenue", "value": "", "unit": "", "is_degraded": True},
                ],
            }
        )
        self.assertIn("暂未命中", summary)

    def test_degraded_without_ingredients_claims_miss(self) -> None:
        summary = self._run({"ingredient_results": []})
        self.assertIn("暂未命中", summary)


if __name__ == "__main__":
    unittest.main()
