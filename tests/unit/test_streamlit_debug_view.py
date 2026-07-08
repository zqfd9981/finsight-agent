from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from frontend.streamlit_app.pages.debug_view import build_debug_view_model
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.final_response import FinalResponse
from shared.contracts.trace_block import TraceBlock


class StreamlitDebugViewTest(unittest.TestCase):
    def test_build_debug_view_model_groups_trace_blocks_and_response(self) -> None:
        envelope = AnalysisResponseEnvelope(
            response=FinalResponse(
                response_type="success",
                summary="ok",
                answer_markdown="完整回答正文",
                report_blocks=[
                    {
                        "block_type": "evidence_overview",
                        "title": "关键证据",
                        "items": [],
                    }
                ],
                uncertainty_notes=["证据有限"],
                next_actions=["继续追问"],
            ),
            trace_blocks=[
                TraceBlock(
                    block_type="routing",
                    title="Routing",
                    status="success",
                    payload_summary={"intent": "event_impact_analysis"},
                ),
                TraceBlock(
                    block_type="planning",
                    title="Planning",
                    status="success",
                    payload_summary={
                        "stages": ["collect_event_context", "analyze_targets"]
                    },
                ),
                TraceBlock(
                    block_type="execution",
                    title="Execution",
                    status="degraded",
                    payload_summary={
                        "stage_statuses": {
                            "collect_event_context": "success",
                            "analyze_targets": "degraded",
                        },
                        "stage_observations": [
                            {
                                "stage_name": "collect_event_context",
                                "status": "success",
                                "key_outputs": {"strategy": "dual_primary"},
                            },
                            {
                                "stage_name": "analyze_targets",
                                "status": "degraded",
                                "key_outputs": {"target_scope": []},
                            },
                        ],
                    },
                ),
            ],
        )

        model = build_debug_view_model(envelope)

        self.assertEqual(model["routing"]["intent"], "event_impact_analysis")
        self.assertEqual(model["planning"]["stages"][0], "collect_event_context")
        self.assertEqual(
            model["execution"]["stage_statuses"]["analyze_targets"], "degraded"
        )
        self.assertEqual(model["stages"][1]["stage_name"], "analyze_targets")
        self.assertEqual(model["final_response"]["summary"], "ok")
        self.assertEqual(model["final_response"]["answer_markdown"], "完整回答正文")
        self.assertEqual(model["final_response"]["report_blocks"][0]["title"], "关键证据")
        self.assertEqual(model["final_response"]["uncertainty_notes"], ["证据有限"])


if __name__ == "__main__":
    unittest.main()
