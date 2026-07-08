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

from finsight_agent.control_plane.session.repository import SessionRepository
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.analysis_stream_event import AnalysisStreamEvent
from shared.contracts.final_response import FinalResponse
from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext


class RecordingRouterService:
    def __init__(self) -> None:
        self.last_session_context: SessionContext | None = None

    def route(self, query: str, session_context: SessionContext | None = None) -> RouterResult:
        self.last_session_context = session_context
        if "evidence" in query.lower() or "expand" in query.lower():
            return RouterResult(
                intent="evidence_lookup",
                follow_up_type="drilldown" if session_context else "none",
                confidence="high",
                entities={
                    "target": "COSCO",
                    "claim": "COSCO may benefit from rate elasticity",
                },
                needs=["rag_retrieval"],
                constraints={"preferred_output": "report"},
            )
        return RouterResult(
            intent="metric_lookup",
            follow_up_type="none",
            confidence="high",
            entities={
                "company": "CATL",
                "metric": "net_profit",
                "time_scope": "2024_annual",
            },
            needs=["structured_data_query"],
            constraints={"preferred_output": "brief_answer"},
        )


class StubPlannerService:
    def build_plan(
        self,
        router_result: RouterResult,
        strategy_payload: dict[str, str] | None = None,
    ) -> Plan:
        del strategy_payload
        if router_result.intent == "evidence_lookup":
            return Plan(
                plan_id="plan_evidence_lookup_v1",
                intent="evidence_lookup",
                stages=["retrieve_evidence", "synthesize_report"],
                stage_constraints={},
                response_mode="report",
            )
        return Plan(
            plan_id="plan_metric_lookup_v1",
            intent="metric_lookup",
            stages=["query_structured_data", "synthesize_brief_answer"],
            stage_constraints={},
            response_mode="brief_answer",
        )


class StubOrchestratorService:
    def execute(
        self,
        *,
        request: AnalysisRequest,
        router_result: RouterResult,
        plan: Plan,
        session_context: SessionContext | None,
        event_callback=None,
    ):
        from finsight_agent.control_plane.orchestrator.models import OrchestrationResult

        del session_context
        if router_result.intent == "evidence_lookup":
            if event_callback is not None:
                event_callback(
                    AnalysisStreamEvent(
                        event_type="stage_started",
                        run_id="run_stub",
                        stage_name="retrieve_evidence",
                        status="running",
                        message="Retrieve evidence started",
                        started_at="2026-07-08T00:00:00Z",
                    )
                )
            response = FinalResponse(
                response_type="success",
                session_id=request.session_id or "",
                summary="Retrieved 1 evidence item for deeper review.",
                report_blocks=[
                    {
                        "block_type": "evidence_overview",
                        "title": "Evidence Overview",
                        "items": [
                            {
                                "evidence_id": "ev_001",
                                "excerpt": "COSCO may benefit from higher shipping rates.",
                                "company_name": "COSCO",
                                "doc_type": "annual_report",
                            }
                        ],
                    }
                ],
            )
            result = OrchestrationResult(
                session_id=request.session_id or "",
                router_result=router_result,
                plan=plan,
                final_response=response,
            )
            result.stage_observations.append(
                type(
                    "ObservationStub",
                    (),
                    {
                        "stage_name": "retrieve_evidence",
                        "output_summary": {"evidence_refs": ["ev_001"]},
                    },
                )()
            )
            if event_callback is not None:
                event_callback(
                    AnalysisStreamEvent(
                        event_type="stage_finished",
                        run_id="run_stub",
                        stage_name="retrieve_evidence",
                        status="success",
                        message="Retrieve evidence finished",
                        started_at="2026-07-08T00:00:00Z",
                        finished_at="2026-07-08T00:00:01Z",
                        duration_ms=1000,
                    )
                )
            return result

        return OrchestrationResult(
            session_id=request.session_id or "",
            router_result=router_result,
            plan=plan,
            final_response=FinalResponse(
                response_type="success",
                session_id=request.session_id or "",
                summary="CATL 2024 net profit was 52.0 billion RMB.",
                next_actions=["Ask about the YoY change drivers."],
            ),
        )


class SessionServiceTest(unittest.TestCase):
    def test_load_context_returns_none_for_missing_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = SessionService(repository=SessionRepository(storage_dir=temp_dir))

            context = service.load_context("sess_missing")

        self.assertIsNone(context)

    def test_service_builds_and_saves_snapshot_from_successful_turn(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)
            service = SessionService(repository=repository)
            router_result = RouterResult(
                intent="metric_lookup",
                follow_up_type="none",
                confidence="high",
                entities={
                    "company": "CATL",
                    "metric": "net_profit",
                    "time_scope": "2024_annual",
                },
                needs=["structured_data_query"],
                constraints={"preferred_output": "brief_answer"},
            )
            plan = Plan(
                plan_id="plan_metric_lookup_v1",
                intent="metric_lookup",
                stages=["query_structured_data", "synthesize_brief_answer"],
                stage_constraints={},
                response_mode="brief_answer",
            )
            orchestration_result = StubOrchestratorService().execute(
                request=AnalysisRequest(
                    query="CATL 2024 net profit?",
                    session_id="sess_metric",
                ),
                router_result=router_result,
                plan=plan,
                session_context=None,
            )

            snapshot = service.build_snapshot(
                request=AnalysisRequest(
                    query="CATL 2024 net profit?",
                    session_id="sess_metric",
                ),
                router_result=router_result,
                plan=plan,
                orchestration_result=orchestration_result,
            )
            assert snapshot is not None
            service.save_snapshot(snapshot)
            loaded_context = service.load_context("sess_metric")

        self.assertIsNotNone(loaded_context)
        assert loaded_context is not None
        self.assertEqual(loaded_context.active_topic, "CATL 2024_annual net_profit")
        self.assertEqual(loaded_context.active_candidates, [])


class WorkbenchSessionFlowTest(unittest.TestCase):
    def test_workbench_generates_session_id_for_first_turn_and_saves_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)
            session_service = SessionService(repository=repository)
            service = WorkbenchBackendApiService(
                router_service=RecordingRouterService(),
                planner_service=StubPlannerService(),
                orchestrator_service=StubOrchestratorService(),
                session_service=session_service,
            )

            envelope = service.build_response(
                AnalysisRequest(query="CATL 2024 net profit?")
            )

            loaded = repository.load(envelope.session_id)

        self.assertIsInstance(envelope, AnalysisResponseEnvelope)
        self.assertTrue(envelope.session_id.startswith("sess_"))
        self.assertIsNotNone(loaded)

    def test_workbench_loads_existing_session_context_for_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)
            session_service = SessionService(repository=repository)
            router_service = RecordingRouterService()
            service = WorkbenchBackendApiService(
                router_service=router_service,
                planner_service=StubPlannerService(),
                orchestrator_service=StubOrchestratorService(),
                session_service=session_service,
            )

            first_turn = service.build_response(
                AnalysisRequest(query="CATL 2024 net profit?")
            )
            follow_up = service.build_response(
                AnalysisRequest(
                    query="Expand the YoY change drivers.",
                    query_mode="follow_up",
                    session_id=first_turn.session_id,
                )
            )

        self.assertEqual(follow_up.session_id, first_turn.session_id)
        self.assertIsNotNone(router_service.last_session_context)
        assert router_service.last_session_context is not None
        self.assertEqual(
            router_service.last_session_context.active_topic,
            "CATL 2024_annual net_profit",
        )

    def test_workbench_persists_rolling_summary_after_follow_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)
            session_service = SessionService(repository=repository)
            service = WorkbenchBackendApiService(
                router_service=RecordingRouterService(),
                planner_service=StubPlannerService(),
                orchestrator_service=StubOrchestratorService(),
                session_service=session_service,
            )

            first_turn = service.build_response(
                AnalysisRequest(query="CATL 2024 net profit?")
            )
            service.build_response(
                AnalysisRequest(
                    query="Expand the YoY change drivers.",
                    query_mode="follow_up",
                    session_id=first_turn.session_id,
                )
            )
            loaded = repository.load(first_turn.session_id)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIn("CATL", loaded.context.history_summary)
        self.assertIn("COSCO", loaded.context.history_summary)

    def test_workbench_degrades_when_session_snapshot_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)
            session_service = SessionService(repository=repository)
            router_service = RecordingRouterService()
            service = WorkbenchBackendApiService(
                router_service=router_service,
                planner_service=StubPlannerService(),
                orchestrator_service=StubOrchestratorService(),
                session_service=session_service,
            )

            envelope = service.build_response(
                AnalysisRequest(
                    query="Expand the evidence for COSCO.",
                    query_mode="follow_up",
                    session_id="sess_missing",
                )
            )

        self.assertEqual(envelope.session_id, "sess_missing")
        self.assertIsNone(router_service.last_session_context)

    def test_stream_response_events_emits_run_lifecycle_and_final_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = SessionRepository(storage_dir=temp_dir)
            session_service = SessionService(repository=repository)
            service = WorkbenchBackendApiService(
                router_service=RecordingRouterService(),
                planner_service=StubPlannerService(),
                orchestrator_service=StubOrchestratorService(),
                session_service=session_service,
            )

            events = list(
                service.stream_response_events(
                    AnalysisRequest(query="Expand the evidence for COSCO.")
                )
            )

        self.assertEqual(events[0].event_type, "run_started")
        self.assertEqual(events[1].stage_name, "routing")
        self.assertEqual(events[2].stage_name, "routing")
        self.assertEqual(events[3].stage_name, "planning")
        self.assertEqual(events[4].stage_name, "planning")
        self.assertEqual(events[-1].event_type, "run_finished")
        self.assertEqual(events[-1].final_response["response_type"], "success")
        self.assertIn("response_envelope", events[-1].payload)


if __name__ == "__main__":
    unittest.main()
