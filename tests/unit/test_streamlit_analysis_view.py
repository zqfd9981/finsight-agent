from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from frontend.streamlit_app.pages.analysis_view import build_analysis_view_model
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.final_response import FinalResponse
from shared.contracts.trace_block import TraceBlock


class StreamlitAnalysisViewTest(unittest.TestCase):
    def test_build_analysis_view_model_extracts_core_fields(self) -> None:
        envelope = AnalysisResponseEnvelope(
            session_id="sess_demo",
            response=FinalResponse(
                response_type="success",
                session_id="sess_demo",
                summary="中远海能等标的受益于运价弹性。",
                report_blocks=[],
            ),
            trace_blocks=[
                TraceBlock(
                    block_type="routing",
                    title="Routing",
                    status="success",
                    payload_summary={"intent": "event_impact_analysis"},
                ),
                TraceBlock(
                    block_type="execution",
                    title="Execution",
                    status="success",
                    payload_summary={
                        "stage_observations": [
                            {
                                "stage_name": "collect_event_context",
                                "key_outputs": {"strategy": "dual_primary"},
                            },
                            {
                                "stage_name": "retrieve_evidence",
                                "key_outputs": {"evidence_ref_count": 3},
                            },
                        ]
                    },
                ),
            ],
        )

        model = build_analysis_view_model(envelope)

        self.assertEqual(model["summary"], "中远海能等标的受益于运价弹性。")
        self.assertEqual(model["intent"], "event_impact_analysis")
        self.assertEqual(model["strategy"], "dual_primary")
        self.assertEqual(model["evidence_ref_count"], 3)


if __name__ == "__main__":
    unittest.main()
