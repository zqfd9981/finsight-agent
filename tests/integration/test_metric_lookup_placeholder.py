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

from backend.apps.api.analysis_turns import handle_analysis_turn
from finsight_agent.control_plane.session.repository import SessionRepository
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from shared.contracts.analysis_request import AnalysisRequest


class MetricLookupIntegrationTest(unittest.TestCase):
    def test_metric_lookup_request_returns_routing_planning_and_execution_trace(self) -> None:
        payload = handle_analysis_turn(
            AnalysisRequest(
                query="宁德时代 2024 年净利润是多少？",
                include_trace=True,
            )
        )

        self.assertTrue(payload["session_id"].startswith("sess_"))
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

    def test_first_turn_persists_session_snapshot_and_follow_up_reuses_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = WorkbenchBackendApiService(
                session_service=SessionService(
                    repository=SessionRepository(storage_dir=temp_dir)
                )
            )
            first_turn = service.build_response(
                AnalysisRequest(query="宁德时代 2024 年净利润是多少？")
            )
            repository = SessionRepository(storage_dir=temp_dir)
            snapshot = repository.load(first_turn.session_id)
            follow_up = service.build_response(
                AnalysisRequest(
                    query="继续展开一下同比变化原因。",
                    query_mode="follow_up",
                    session_id=first_turn.session_id,
                )
            )

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.context.active_candidates, ["宁德时代"])
        self.assertEqual(follow_up.session_id, first_turn.session_id)

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
