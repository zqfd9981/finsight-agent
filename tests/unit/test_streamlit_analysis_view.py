from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from frontend.streamlit_app.pages.analysis_view import (
    build_analysis_view_model,
    build_stream_timeline_view,
)
from shared.contracts.analysis_stream_event import AnalysisStreamEvent
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
                answer_markdown="这是用户最终会看到的完整回答。",
                report_blocks=[
                    {
                        "block_type": "evidence_overview",
                        "title": "关键证据",
                        "items": [
                            {
                                "evidence_id": "ev_001",
                                "excerpt": "运价弹性推动业绩弹性。",
                                "company_name": "中远海能",
                                "doc_type": "annual_report",
                            }
                        ],
                    }
                ],
                uncertainty_notes=["证据数量有限"],
                next_actions=["可继续追问更具体时间段。"],
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
        self.assertEqual(model["answer_markdown"], "这是用户最终会看到的完整回答。")
        self.assertEqual(model["intent"], "event_impact_analysis")
        self.assertEqual(model["strategy"], "dual_primary")
        self.assertEqual(model["evidence_ref_count"], 3)
        self.assertEqual(model["report_blocks"][0]["title"], "关键证据")
        self.assertEqual(model["uncertainty_notes"], ["证据数量有限"])
        self.assertEqual(model["next_actions"], ["可继续追问更具体时间段。"])

    def test_build_stream_timeline_view_tracks_running_and_completed_stages(self) -> None:
        view = build_stream_timeline_view(
            [
                AnalysisStreamEvent(
                    event_type="run_started",
                    run_id="run_001",
                    stage_name="",
                    status="running",
                    message="Analysis started",
                    started_at="2026-07-08T00:00:00Z",
                ),
                AnalysisStreamEvent(
                    event_type="stage_started",
                    run_id="run_001",
                    stage_name="routing",
                    status="running",
                    message="Routing started",
                    started_at="2026-07-08T00:00:00Z",
                ),
                AnalysisStreamEvent(
                    event_type="stage_finished",
                    run_id="run_001",
                    stage_name="routing",
                    status="success",
                    message="Routing finished",
                    started_at="2026-07-08T00:00:00Z",
                    finished_at="2026-07-08T00:00:10Z",
                    duration_ms=10,
                ),
                AnalysisStreamEvent(
                    event_type="stage_started",
                    run_id="run_001",
                    stage_name="stage_planning",
                    status="running",
                    message="Stage planning started",
                    started_at="2026-07-08T00:00:10Z",
                ),
            ]
        )

        self.assertEqual(view["current_stage"], "stage_planning")
        self.assertEqual(view["completed_count"], 1)
        self.assertEqual(view["stages"][0]["status"], "success")
        self.assertEqual(view["stages"][1]["status"], "running")


if __name__ == "__main__":
    unittest.main()
