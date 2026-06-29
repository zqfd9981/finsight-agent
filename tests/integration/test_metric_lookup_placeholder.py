from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from backend.apps.api.analysis_turns import handle_analysis_turn
from shared.contracts.analysis_request import AnalysisRequest


class MetricLookupIntegrationTest(unittest.TestCase):
    def test_metric_lookup_request_returns_routing_trace(self) -> None:
        payload = handle_analysis_turn(
            AnalysisRequest(
                query="宁德时代 2024 年净利润是多少？",
                include_trace=True,
            )
        )

        self.assertEqual(payload["session_id"], "sess_stub")
        self.assertEqual(payload["response"]["response_type"], "success")
        self.assertEqual(payload["trace_blocks"][0]["block_type"], "routing")
        self.assertEqual(
            payload["trace_blocks"][0]["payload_summary"]["intent"],
            "metric_lookup",
        )
        self.assertEqual(len(payload["trace_blocks"]), 1)

    def test_follow_up_request_keeps_same_session_and_marks_drilldown(self) -> None:
        payload = handle_analysis_turn(
            AnalysisRequest(
                query="继续展开一下这个指标同比变化的原因。",
                query_mode="follow_up",
                session_id="sess_existing",
                include_trace=True,
            )
        )

        self.assertEqual(payload["session_id"], "sess_existing")
        self.assertEqual(
            payload["trace_blocks"][0]["payload_summary"]["follow_up_type"],
            "drilldown",
        )


if __name__ == "__main__":
    unittest.main()
