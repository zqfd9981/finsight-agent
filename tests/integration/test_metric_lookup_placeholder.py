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
    def test_metric_lookup_request_returns_routing_planning_and_execution_trace(self) -> None:
        payload = handle_analysis_turn(
            AnalysisRequest(
                query="宁德时代 2024 年净利润是多少？",
                include_trace=True,
            )
        )

        self.assertEqual(payload["session_id"], "sess_stub")
        self.assertEqual(payload["response"]["response_type"], "success")
        self.assertEqual(
            [block["block_type"] for block in payload["trace_blocks"]],
            ["routing", "planning", "execution"],
        )
        self.assertEqual(
            payload["trace_blocks"][0]["payload_summary"]["intent"],
            "metric_lookup",
        )
        self.assertEqual(
            payload["trace_blocks"][1]["payload_summary"]["stage_count"],
            2,
        )

    def test_evidence_lookup_request_returns_execution_trace_and_success_response(self) -> None:
        payload = handle_analysis_turn(
            AnalysisRequest(
                query="把中远海能受益逻辑的证据展开一下",
                session_id="sess_existing",
                include_trace=True,
            )
        )

        self.assertEqual(payload["session_id"], "sess_existing")
        self.assertEqual(payload["response"]["response_type"], "success")
        self.assertIn(
            "execution",
            [block["block_type"] for block in payload["trace_blocks"]],
        )


if __name__ == "__main__":
    unittest.main()
