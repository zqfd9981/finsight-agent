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

from finsight_agent.control_plane.orchestrator.service import OrchestratorService
from finsight_agent.control_plane.session.repository import SessionRepository
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.evaluation.event_eval.replay import replay_event_cases
from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from tests.integration.test_event_impact_analysis_flow import (
    _StubPlannerService,
    _StubRetrievalFacade,
    _StubRouterService,
    _StubStrategyClassifier,
    _StubTargetAnalysisService,
)


class _EvalExternalContextRetriever:
    def retrieve_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
        strategy: str,
    ) -> dict[str, object] | None:
        del query, event, themes, time_scope, limit
        return {
            "summary_hint": "The disruption increased freight-rate sensitivity.",
            "supporting_points": [
                "Detour expectations rose.",
                "Shipping-chain tightness improved rate elasticity.",
            ],
            "evidence_refs": ["ext_ctx_001"],
            "source_status": {
                "mode": strategy,
                "allow_local_rag": False,
            },
        }

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        del query, event_context, limit
        return {
            "candidates": ["COSCO", "China Merchants"],
            "evidence_refs": ["ext_candidate_001"],
            "source_status": {"mode": "dual_primary"},
        }


class EventAnalysisReplaySmokeTest(unittest.TestCase):
    def test_replay_event_cases_returns_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "cases.jsonl"
            fixture_path.write_text(
                '{"case_id":"dual_001","query":"Which A-share shipping stocks benefit from the Red Sea disruption?","expected_intent":"event_impact_analysis","expected_strategy":"dual_primary","allow_degraded":true,"min_target_count":1,"expected_target_keywords":["COSCO"],"notes":"smoke"}\n',
                encoding="utf-8",
            )

            service = WorkbenchBackendApiService(
                router_service=_StubRouterService(),
                planner_service=_StubPlannerService(),
                orchestrator_service=OrchestratorService(
                    retrieval_facade=_StubRetrievalFacade(),
                    external_context_retriever=_EvalExternalContextRetriever(),
                    target_analysis_service=_StubTargetAnalysisService(),
                ),
                session_service=SessionService(
                    repository=SessionRepository(storage_dir=Path(temp_dir) / "sessions")
                ),
                retrieval_strategy_classifier=_StubStrategyClassifier(strategy="dual_primary"),
            )

            records = replay_event_cases(fixture_path, service=service)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].result.actual_intent, "event_impact_analysis")
        self.assertEqual(records[0].result.actual_strategy, "dual_primary")
        self.assertTrue(records[0].checks)


if __name__ == "__main__":
    unittest.main()
