from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from frontend.streamlit_app.pages.eval_view import build_eval_view_model
from frontend.streamlit_app.state.models import (
    EventReplayRecordView,
    EventReplayResultView,
    EventReplayRunView,
    EventReplaySummaryView,
)


class StreamlitEvalViewTest(unittest.TestCase):
    def test_build_eval_view_model_filters_failed_records(self) -> None:
        replay = EventReplayRunView(
            summary=EventReplaySummaryView(total=2, pass_count=1, warn_count=0, fail_count=1),
            records=[
                EventReplayRecordView(
                    case_id="dual_001",
                    query="红海局势升级利好哪些A股航运股？",
                    result=EventReplayResultView(
                        case_id="dual_001",
                        query="红海局势升级利好哪些A股航运股？",
                        actual_intent="event_impact_analysis",
                        actual_strategy="dual_primary",
                        response_type="success",
                        degraded=False,
                        target_count=2,
                        evidence_ref_count=3,
                        summary="ok",
                        failure_reason=None,
                        target_keywords=["中远海能"],
                    ),
                    checks=[{"check_name": "intent_match", "status": "pass", "message": "ok"}],
                ),
                EventReplayRecordView(
                    case_id="event_weak_001",
                    query="最近这个事件利好谁？",
                    result=EventReplayResultView(
                        case_id="event_weak_001",
                        query="最近这个事件利好谁？",
                        actual_intent="event_impact_analysis",
                        actual_strategy="event_primary",
                        response_type="degraded",
                        degraded=True,
                        target_count=0,
                        evidence_ref_count=0,
                        summary="当前只能确认事件背景。",
                        failure_reason=None,
                        target_keywords=[],
                    ),
                    checks=[
                        {
                            "check_name": "target_count",
                            "status": "fail",
                            "message": "target_count < 1",
                        }
                    ],
                ),
            ],
        )

        model = build_eval_view_model(replay, status_filter="fail")

        self.assertEqual(model["summary"]["fail"], 1)
        self.assertEqual(len(model["records"]), 1)
        self.assertEqual(model["records"][0]["case_id"], "event_weak_001")


if __name__ == "__main__":
    unittest.main()
