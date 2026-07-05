from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.evaluation.event_eval.models import EventEvalCase
from finsight_agent.evaluation.event_eval.replay import build_replay_result
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.final_response import FinalResponse
from shared.contracts.trace_block import TraceBlock


class EventEvalReplayTest(unittest.TestCase):
    def test_build_replay_result_extracts_strategy_and_targets(self) -> None:
        case = EventEvalCase(
            case_id="dual_001",
            query="红海局势升级利好哪些A股航运股？",
            expected_intent="event_impact_analysis",
            expected_strategy="dual_primary",
            allow_degraded=True,
            min_target_count=1,
        )
        envelope = AnalysisResponseEnvelope(
            session_id="sess_001",
            response=FinalResponse(
                response_type="success",
                summary="中远海能、招商轮船等标的可能受益。",
                report_blocks=[],
            ),
            trace_blocks=[
                TraceBlock(
                    block_type="routing",
                    title="路由结果",
                    status="success",
                    payload_summary={"intent": "event_impact_analysis"},
                ),
                TraceBlock(
                    block_type="execution",
                    title="执行结果",
                    status="success",
                    payload_summary={
                        "stage_statuses": {
                            "collect_event_context": "success",
                            "analyze_targets": "success",
                        },
                        "stage_observations": [
                            {
                                "stage_name": "collect_event_context",
                                "key_outputs": {"strategy": "dual_primary"},
                                "evidence_refs": ["ext_001"],
                            },
                            {
                                "stage_name": "analyze_targets",
                                "key_outputs": {
                                    "target_scope": ["中远海能", "招商轮船"]
                                },
                                "evidence_refs": [],
                            },
                        ],
                    },
                ),
            ],
        )

        result = build_replay_result(case, envelope)

        self.assertEqual(result.actual_strategy, "dual_primary")
        self.assertEqual(result.target_count, 2)
        self.assertEqual(result.evidence_ref_count, 1)


if __name__ == "__main__":
    unittest.main()
