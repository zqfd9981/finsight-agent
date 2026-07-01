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
from shared.contracts.final_response import FinalResponse
from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext


class RecordingRouterService:
    def __init__(self) -> None:
        self.last_session_context: SessionContext | None = None

    def route(self, query: str, session_context: SessionContext | None = None) -> RouterResult:
        self.last_session_context = session_context
        if "证据" in query or "展开" in query:
            return RouterResult(
                intent="evidence_lookup",
                follow_up_type="drilldown" if session_context else "none",
                confidence="high",
                entities={
                    "target": "中远海能",
                    "claim": "中远海能受益逻辑",
                },
                needs=["rag_retrieval"],
                constraints={"preferred_output": "report"},
            )
        return RouterResult(
            intent="metric_lookup",
            follow_up_type="none",
            confidence="high",
            entities={
                "company": "宁德时代",
                "metric": "net_profit",
                "time_scope": "2024_annual",
            },
            needs=["structured_data_query"],
            constraints={"preferred_output": "brief_answer"},
        )


class StubPlannerService:
    def build_plan(self, router_result: RouterResult) -> Plan:
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
    ):
        from finsight_agent.control_plane.orchestrator.models import OrchestrationResult

        del session_context
        if router_result.intent == "evidence_lookup":
            response = FinalResponse(
                response_type="success",
                session_id=request.session_id or "",
                summary="已检索到 1 条证据，可用于继续研判。",
                report_blocks=[
                    {
                        "block_type": "evidence_overview",
                        "title": "证据概览",
                        "items": [
                            {
                                "evidence_id": "ev_001",
                                "excerpt": "中远海能受益于运价上涨。",
                                "company_name": "中远海能",
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
            return result

        return OrchestrationResult(
            session_id=request.session_id or "",
            router_result=router_result,
            plan=plan,
            final_response=FinalResponse(
                response_type="success",
                session_id=request.session_id or "",
                summary="宁德时代 2024 年净利润为 520 亿元。",
                next_actions=["可继续追问同比变化原因。"],
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
                    "company": "宁德时代",
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
                    query="宁德时代 2024 年净利润是多少？",
                    session_id="sess_metric",
                ),
                router_result=router_result,
                plan=plan,
                session_context=None,
            )

            snapshot = service.build_snapshot(
                request=AnalysisRequest(
                    query="宁德时代 2024 年净利润是多少？",
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
        self.assertEqual(loaded_context.active_topic, "宁德时代 2024_annual net_profit")
        self.assertEqual(loaded_context.active_candidates, ["宁德时代"])


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
                AnalysisRequest(query="宁德时代 2024 年净利润是多少？")
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
                AnalysisRequest(query="宁德时代 2024 年净利润是多少？")
            )
            follow_up = service.build_response(
                AnalysisRequest(
                    query="继续展开一下同比变化原因。",
                    query_mode="follow_up",
                    session_id=first_turn.session_id,
                )
            )

        self.assertEqual(follow_up.session_id, first_turn.session_id)
        self.assertIsNotNone(router_service.last_session_context)
        assert router_service.last_session_context is not None
        self.assertEqual(
            router_service.last_session_context.active_topic,
            "宁德时代 2024_annual net_profit",
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
                AnalysisRequest(query="宁德时代 2024 年净利润是多少？")
            )
            service.build_response(
                AnalysisRequest(
                    query="继续展开一下同比变化原因。",
                    query_mode="follow_up",
                    session_id=first_turn.session_id,
                )
            )
            loaded = repository.load(first_turn.session_id)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertIn("上一轮已完成宁德时代 2024 年净利润查询", loaded.context.history_summary)
        self.assertIn("已围绕中远海能受益逻辑继续展开", loaded.context.history_summary)

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
                    query="把中远海能受益逻辑的证据展开一下",
                    query_mode="follow_up",
                    session_id="sess_missing",
                )
            )

        self.assertEqual(envelope.session_id, "sess_missing")
        self.assertIsNone(router_service.last_session_context)


if __name__ == "__main__":
    unittest.main()
