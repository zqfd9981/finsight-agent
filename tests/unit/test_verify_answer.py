from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for _candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from finsight_agent.control_plane.orchestrator.stage_runners.verify_answer import (
    run_verify_answer_stage,
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


class VerifyAnswerTest(unittest.TestCase):
    def test_neutral_when_llm_unavailable(self) -> None:
        result = run_verify_answer_stage(
            request=_request(),
            router_result=_router_result(),
            execution_state={},
            llm_client=None,
            answer_text="贵州茅台 2024 年毛利率为 91.6%。",
        )
        verification = result.output_payload["verification"]
        self.assertIsNone(verification["answered"])
        self.assertEqual(verification["confidence"], "unknown")

    def test_structured_output_when_llm_available(self) -> None:
        llm = _FakeLlmClient(
            {
                "answered": True,
                "confidence": "high",
                "gaps": [],
                "suggested_follow_ups": ["再看看负债率"],
            }
        )
        result = run_verify_answer_stage(
            request=_request(),
            router_result=_router_result(),
            execution_state={},
            llm_client=llm,
            answer_text="贵州茅台 2024 年毛利率为 91.6%。",
        )
        verification = result.output_payload["verification"]
        self.assertTrue(verification["answered"])
        self.assertEqual(verification["confidence"], "high")
        self.assertEqual(verification["suggested_follow_ups"], ["再看看负债率"])
        self.assertEqual(result.stage_name, StageName.VERIFY_ANSWER.value)

    def test_noop_without_answer_text(self) -> None:
        llm = _FakeLlmClient({"answered": True, "confidence": "high"})
        result = run_verify_answer_stage(
            request=_request(),
            router_result=_router_result(),
            execution_state={},
            llm_client=llm,
            answer_text="",
        )
        # 无答案文本时不调 LLM
        self.assertEqual(llm.calls, 0)


if __name__ == "__main__":
    unittest.main()
