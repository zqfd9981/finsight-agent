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
    def test_build_debug_view_model_groups_trace_blocks(self) -> None:
        envelope = AnalysisResponseEnvelope(
            response=FinalResponse(response_type="success", summary="ok"),
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


if __name__ == "__main__":
    unittest.main()
