from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.control_plane.orchestrator.models import (
    OrchestrationResult,
    StageExecutionResult,
)
from finsight_agent.control_plane.orchestrator.observation_builder import (
    build_stage_observation,
)


class OrchestratorModelsTest(unittest.TestCase):
    def test_stage_execution_result_exposes_expected_fields(self) -> None:
        result = StageExecutionResult(
            stage_name="retrieve_evidence",
            status="partial",
            output_payload={"chunks": 2},
            confidence_signals={"coverage": "medium"},
            evidence_refs=["doc:1", "doc:2"],
            degraded_reason="news_search_timeout",
            user_summary="已拿到部分证据。",
        )

        self.assertEqual(result.stage_name, "retrieve_evidence")
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.output_payload, {"chunks": 2})
        self.assertEqual(result.confidence_signals, {"coverage": "medium"})
        self.assertEqual(result.evidence_refs, ["doc:1", "doc:2"])
        self.assertEqual(result.degraded_reason, "news_search_timeout")
        self.assertEqual(result.user_summary, "已拿到部分证据。")

    def test_build_stage_observation_maps_internal_result_to_contract(self) -> None:
        result = StageExecutionResult(
            stage_name="retrieve_evidence",
            status="success",
            output_payload={"top_k": 3, "matches": ["a", "b"]},
            confidence_signals={"coverage": "high"},
            evidence_refs=["chunk:1"],
            degraded_reason=None,
            user_summary="已检索到关键证据。",
        )

        observation = build_stage_observation(
            stage_result=result,
            observation_id="obs_001",
            input_summary={"query": "红海事件利好谁"},
        )

        self.assertEqual(observation.version, "v1")
        self.assertEqual(observation.observation_id, "obs_001")
        self.assertEqual(observation.stage_name, "retrieve_evidence")
        self.assertEqual(observation.status, "success")
        self.assertEqual(observation.input_summary, {"query": "红海事件利好谁"})
        self.assertEqual(observation.key_outputs, {"top_k": 3, "matches": ["a", "b"]})
        self.assertEqual(observation.confidence_signals, {"coverage": "high"})
        self.assertEqual(observation.evidence_refs, ["chunk:1"])
        self.assertEqual(observation.notes, "已检索到关键证据。")

    def test_orchestration_result_starts_with_empty_observations_and_trace_blocks(self) -> None:
        result = OrchestrationResult(session_id="sess_001")

        self.assertEqual(result.session_id, "sess_001")
        self.assertEqual(result.stage_observations, [])
        self.assertEqual(result.trace_blocks, [])


if __name__ == "__main__":
    unittest.main()
