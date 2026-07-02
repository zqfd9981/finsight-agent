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
from finsight_agent.control_plane.orchestrator.service import OrchestratorService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.final_response import FinalResponse
from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode


class StubStructuredDataService:
    def query_metric_lookup(
        self,
        company: str,
        metric: str,
        time_scope: str,
    ) -> dict[str, str]:
        return {
            "company": "宁德时代",
            "metric": metric,
            "time_scope": time_scope,
            "value": "123.45 亿元",
        }


class StubReportingService:
    def build_brief_response(self, session_id: str, summary: str) -> FinalResponse:
        return FinalResponse(
            response_type="success",
            session_id=session_id,
            summary=summary,
        )

    def build_report_response(
        self,
        session_id: str,
        summary: str,
        report_blocks: list[dict[str, object]],
        uncertainty_notes: list[str],
        next_actions: list[str],
    ) -> FinalResponse:
        return FinalResponse(
            response_type="success",
            session_id=session_id,
            summary=summary,
            report_blocks=report_blocks,
            uncertainty_notes=uncertainty_notes,
            next_actions=next_actions,
        )


class StubRetrievalFacade:
    def __init__(self) -> None:
        self.closed = False
        self.calls: list[dict[str, object]] = []

    def retrieve_evidence(
        self,
        raw_query: str,
        limit: int = 5,
        company_code: str | None = None,
        doc_type: str | None = None,
        report_year: int | None = None,
    ):
        from finsight_agent.capabilities.retrieval.models import RetrievalResult

        self.calls.append({"raw_query": raw_query, "limit": limit})
        return RetrievalResult(
            request_id="retrieval_001",
            normalized_claim=raw_query,
            evidence_items=[],
        )

    def close(self) -> None:
        self.closed = True


class StubExternalContextRetriever:
    def __init__(self) -> None:
        self.context_calls: list[dict[str, object]] = []
        self.discovery_calls: list[dict[str, object]] = []

    def retrieve_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> dict[str, object] | None:
        self.context_calls.append(
            {
                "query": query,
                "event": event,
                "themes": themes,
                "time_scope": time_scope,
                "limit": limit,
            }
        )
        return {
            "summary_hint": "红海局势升级导致绕航预期升温。",
            "supporting_points": ["航线扰动可能推升运价。"],
            "evidence_refs": ["ext_001"],
        }

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        self.discovery_calls.append(
            {
                "query": query,
                "event_context": event_context,
                "limit": limit,
            }
        )
        return {
            "candidates": ["中远海能", "招商轮船"],
            "evidence_refs": ["ext_002"],
        }


class StubTargetAnalysisService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def analyze_targets(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        candidate_pool: list[str],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "query": query,
                "event_context": event_context,
                "candidate_pool": list(candidate_pool),
            }
        )
        return {
            "target_scope": ["中远海能", "招商轮船"],
            "ranked_targets": [
                {
                    "target": "中远海能",
                    "target_type": "company",
                    "impact_direction": "positive",
                    "reasoning_summary": "若绕航持续，油运弹性可能更明显。",
                    "confidence": "medium",
                }
            ],
            "open_questions": ["后续仍需核对运价持续性。"],
            "confidence": "medium",
            "analysis_mode": "llm_constrained",
        }


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
            input_summary={"query": "红海事件利好谁？"},
        )

        self.assertEqual(observation.version, "v1")
        self.assertEqual(observation.observation_id, "obs_001")
        self.assertEqual(observation.stage_name, "retrieve_evidence")
        self.assertEqual(observation.status, "success")
        self.assertEqual(observation.input_summary, {"query": "红海事件利好谁？"})
        self.assertEqual(observation.key_outputs, {"top_k": 3, "matches": ["a", "b"]})
        self.assertEqual(observation.confidence_signals, {"coverage": "high"})
        self.assertEqual(observation.evidence_refs, ["chunk:1"])
        self.assertEqual(observation.notes, "已检索到关键证据。")

    def test_orchestration_result_starts_with_empty_observations_and_trace_blocks(self) -> None:
        result = OrchestrationResult(session_id="sess_001")

        self.assertEqual(result.session_id, "sess_001")
        self.assertEqual(result.stage_observations, [])
        self.assertEqual(result.trace_blocks, [])


class OrchestratorServiceExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = OrchestratorService(
            structured_data_service=StubStructuredDataService(),
            reporting_service=StubReportingService(),
            retrieval_facade=StubRetrievalFacade(),
            external_context_retriever=StubExternalContextRetriever(),
            target_analysis_service=StubTargetAnalysisService(),
        )

    def test_execute_metric_lookup_plan_runs_two_stages_and_returns_final_response(self) -> None:
        router_result = RouterResult(
            intent=Intent.METRIC_LOOKUP.value,
            follow_up_type=FollowUpType.NONE.value,
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
            intent=Intent.METRIC_LOOKUP.value,
            stages=["query_structured_data", "synthesize_brief_answer"],
            stage_constraints={
                "query_structured_data": {"time_hint": "2024_annual"},
                "synthesize_brief_answer": {"preferred_output": "brief_answer"},
            },
            response_mode=ResponseMode.BRIEF_ANSWER.value,
        )

        result = self.service.execute(
            request=AnalysisRequest(
                query="宁德时代 2024 年净利润是多少？",
                session_id="sess_001",
                include_trace=True,
            ),
            router_result=router_result,
            plan=plan,
            session_context=None,
        )

        self.assertIsNotNone(result.final_response)
        self.assertEqual(result.final_response.response_type, "success")
        self.assertEqual(len(result.stage_observations), 2)
        self.assertEqual(result.stage_observations[0].stage_name, "query_structured_data")
        self.assertEqual(result.stage_observations[1].stage_name, "synthesize_brief_answer")
        self.assertEqual(result.trace_blocks[-1].block_type, "execution")

    def test_execute_out_of_scope_plan_short_circuits_without_stage_execution(self) -> None:
        router_result = RouterResult(
            intent=Intent.OUT_OF_SCOPE.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={"query": "预测一下比亚迪下周股价走势"},
            needs=[],
            constraints={
                "preferred_output": "guardrail",
                "reason_code": "out_of_scope_request",
            },
        )
        plan = Plan(
            plan_id="plan_out_of_scope_v1",
            intent=Intent.OUT_OF_SCOPE.value,
            stages=[],
            stage_constraints={
                "guardrail": {
                    "preferred_output": "guardrail",
                    "reason_code": "out_of_scope_request",
                }
            },
            response_mode=ResponseMode.BRIEF_ANSWER.value,
        )

        result = self.service.execute(
            request=AnalysisRequest(
                query="预测一下比亚迪下周股价走势",
                session_id="sess_001",
                include_trace=True,
            ),
            router_result=router_result,
            plan=plan,
            session_context=None,
        )

        self.assertIsNone(result.final_response)
        self.assertIsNotNone(result.guardrail_response)
        self.assertEqual(result.guardrail_response.response_type, "guardrail")
        self.assertEqual(result.stage_observations, [])

    def test_execute_event_impact_analysis_runs_four_stages_and_returns_report(self) -> None:
        router_result = RouterResult(
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={
                "event": "红海局势升级",
                "themes": ["航运"],
                "time_scope": "recent",
            },
            needs=["news_search"],
            constraints={"preferred_output": "report"},
        )
        plan = Plan(
            plan_id="plan_event_impact_analysis_v1",
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            stages=[
                "collect_event_context",
                "analyze_targets",
                "retrieve_evidence",
                "synthesize_report",
            ],
            stage_constraints={
                "collect_event_context": {"retrieval_budget": 3},
                "analyze_targets": {"candidate_discovery_budget": 1},
                "retrieve_evidence": {"retrieval_budget": 4},
                "synthesize_report": {"preferred_output": "report"},
            },
            response_mode=ResponseMode.REPORT.value,
        )

        result = self.service.execute(
            request=AnalysisRequest(
                query="红海局势升级利好哪些 A 股航运公司？",
                session_id="sess_001",
                include_trace=True,
            ),
            router_result=router_result,
            plan=plan,
            session_context=None,
        )

        self.assertIsNotNone(result.final_response)
        self.assertEqual(result.final_response.response_type, "success")
        self.assertEqual(
            [item.stage_name for item in result.stage_observations],
            [
                "collect_event_context",
                "analyze_targets",
                "retrieve_evidence",
                "synthesize_report",
            ],
        )
        self.assertIn("中远海能", result.final_response.summary)
        self.assertEqual(result.trace_blocks[-1].block_type, "execution")

    def test_execute_metric_lookup_plan_does_not_build_retrieval_facade(self) -> None:
        retrieval_factory_calls: list[str] = []

        def build_retrieval_facade_stub() -> StubRetrievalFacade:
            retrieval_factory_calls.append("built")
            return StubRetrievalFacade()

        service = OrchestratorService(
            structured_data_service=StubStructuredDataService(),
            reporting_service=StubReportingService(),
            retrieval_facade_factory=build_retrieval_facade_stub,
        )
        router_result = RouterResult(
            intent=Intent.METRIC_LOOKUP.value,
            follow_up_type=FollowUpType.NONE.value,
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
            intent=Intent.METRIC_LOOKUP.value,
            stages=["query_structured_data", "synthesize_brief_answer"],
            stage_constraints={
                "query_structured_data": {"time_hint": "2024_annual"},
                "synthesize_brief_answer": {"preferred_output": "brief_answer"},
            },
            response_mode=ResponseMode.BRIEF_ANSWER.value,
        )

        service.execute(
            request=AnalysisRequest(
                query="宁德时代 2024 年净利润是多少？",
                session_id="sess_001",
            ),
            router_result=router_result,
            plan=plan,
            session_context=None,
        )

        self.assertEqual(retrieval_factory_calls, [])

    def test_execute_evidence_plan_closes_owned_retrieval_facade_after_execution(self) -> None:
        retrieval_facade = StubRetrievalFacade()

        def build_retrieval_facade_stub() -> StubRetrievalFacade:
            return retrieval_facade

        service = OrchestratorService(
            reporting_service=StubReportingService(),
            retrieval_facade_factory=build_retrieval_facade_stub,
        )
        router_result = RouterResult(
            intent=Intent.EVIDENCE_LOOKUP.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={
                "target": "中远海能",
                "claim": "把中远海能受益逻辑的证据展开一下",
            },
            needs=["rag_retrieval"],
            constraints={"preferred_output": "report", "retrieval_budget": 3},
        )
        plan = Plan(
            plan_id="plan_evidence_lookup_v1",
            intent=Intent.EVIDENCE_LOOKUP.value,
            stages=["retrieve_evidence", "synthesize_report"],
            stage_constraints={
                "retrieve_evidence": {"retrieval_budget": 3},
                "synthesize_report": {"preferred_output": "report"},
            },
            response_mode=ResponseMode.REPORT.value,
        )

        result = service.execute(
            request=AnalysisRequest(
                query="把中远海能受益逻辑的证据展开一下",
                session_id="sess_001",
            ),
            router_result=router_result,
            plan=plan,
            session_context=None,
        )

        self.assertIsNotNone(result.final_response)
        self.assertTrue(retrieval_facade.closed)


if __name__ == "__main__":
    unittest.main()
