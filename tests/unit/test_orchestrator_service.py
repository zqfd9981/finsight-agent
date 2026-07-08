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
from shared.contracts.analysis_stream_event import AnalysisStreamEvent
from shared.contracts.final_response import FinalResponse
from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName


class StubStructuredDataService:
    def query_metric_lookup(self, company: str, metric: str, time_scope: str) -> dict[str, str]:
        return {
            "company": company,
            "metric": metric,
            "time_scope": time_scope,
            "value": "123.45 亿元",
        }


class StubReportingService:
    def build_brief_response(
        self,
        session_id: str,
        summary: str,
        *,
        final_answer_context: dict[str, object] | None = None,
    ) -> FinalResponse:
        del final_answer_context
        return FinalResponse(
            response_type="success",
            session_id=session_id,
            summary=summary,
            answer_markdown=summary,
        )

    def build_report_response(
        self,
        session_id: str,
        summary: str,
        report_blocks: list[dict[str, object]],
        uncertainty_notes: list[str],
        next_actions: list[str],
        *,
        final_answer_context: dict[str, object] | None = None,
    ) -> FinalResponse:
        del final_answer_context
        return FinalResponse(
            response_type="success",
            session_id=session_id,
            summary=summary,
            answer_markdown=summary,
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

        del company_code, doc_type, report_year
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
        strategy: str,
    ) -> dict[str, object] | None:
        self.context_calls.append(
            {
                "query": query,
                "event": event,
                "themes": themes,
                "time_scope": time_scope,
                "limit": limit,
                "strategy": strategy,
            }
        )
        return {
            "summary_hint": "红海局势升级带动航运景气预期升温。",
            "supporting_points": ["航线扰动可能推升运价。"],
            "evidence_refs": ["ext_001"],
            "source_status": {"mode": strategy, "allow_local_rag": False},
            "candidate_hints": ["中远海能", "招商轮船"],
        }

    def discover_candidates(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        limit: int,
    ) -> dict[str, object] | None:
        self.discovery_calls.append(
            {"query": query, "event_context": event_context, "limit": limit}
        )
        return {
            "candidates": ["中远海能", "招商轮船"],
            "evidence_refs": ["ext_002"],
        }


class StubTargetAnalysisService:
    def analyze_targets(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        candidate_pool: list[str],
    ) -> dict[str, object]:
        del query, event_context
        return {
            "target_scope": list(candidate_pool[:2]) or ["中远海能"],
            "ranked_targets": [
                {
                    "target": "中远海能",
                    "target_type": "company",
                    "impact_direction": "positive",
                    "reasoning_summary": "油运弹性更直接。",
                    "confidence": "medium",
                }
            ],
            "open_questions": ["仍需验证运价持续性。"],
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
            degraded_reason="timeout",
            user_summary="已拿到部分证据。",
        )

        self.assertEqual(result.stage_name, "retrieve_evidence")
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.output_payload, {"chunks": 2})
        self.assertEqual(result.confidence_signals, {"coverage": "medium"})
        self.assertEqual(result.evidence_refs, ["doc:1", "doc:2"])
        self.assertEqual(result.degraded_reason, "timeout")
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

        self.assertEqual(observation.stage_name, "retrieve_evidence")
        self.assertEqual(observation.status, "success")
        self.assertEqual(observation.key_outputs, {"top_k": 3, "matches": ["a", "b"]})
        self.assertEqual(observation.evidence_refs, ["chunk:1"])

    def test_orchestration_result_starts_with_empty_observations_and_trace_blocks(self) -> None:
        result = OrchestrationResult(session_id="sess_001")
        self.assertEqual(result.stage_observations, [])
        self.assertEqual(result.trace_blocks, [])


class OrchestratorServiceExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.external_context_retriever = StubExternalContextRetriever()
        self.service = OrchestratorService(
            structured_data_service=StubStructuredDataService(),
            reporting_service=StubReportingService(),
            retrieval_facade=StubRetrievalFacade(),
            external_context_retriever=self.external_context_retriever,
            target_analysis_service=StubTargetAnalysisService(),
        )

    def test_service_builds_dual_source_external_context_retriever_by_default(self) -> None:
        service = OrchestratorService()
        self.assertEqual(
            service._external_context_retriever.__class__.__name__,
            "DualSourceExternalContextRetriever",
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
            stages=[
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ],
            stage_constraints={
                StageName.QUERY_STRUCTURED_DATA.value: {"time_hint": "2024_annual"},
                StageName.SYNTHESIZE_BRIEF_ANSWER.value: {
                    "preferred_output": "brief_answer"
                },
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
        self.assertEqual(
            [item.stage_name for item in result.stage_observations],
            [
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ],
        )

    def test_execute_event_primary_plan_returns_event_answer(self) -> None:
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
            plan_id="plan_event_impact_analysis_event_primary_v1",
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            stages=[
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.SYNTHESIZE_EVENT_ANSWER.value,
            ],
            stage_constraints={
                StageName.COLLECT_EVENT_CONTEXT.value: {
                    "retrieval_budget": 3,
                    "strategy": "event_primary",
                },
                StageName.SYNTHESIZE_EVENT_ANSWER.value: {
                    "preferred_output": "brief_answer"
                },
            },
            response_mode=ResponseMode.BRIEF_ANSWER.value,
        )

        result = self.service.execute(
            request=AnalysisRequest(
                query="红海局势升级对A股哪些板块有影响？",
                session_id="sess_001",
                include_trace=True,
            ),
            router_result=router_result,
            plan=plan,
            session_context=None,
        )

        self.assertIsNotNone(result.final_response)
        self.assertEqual(
            [item.stage_name for item in result.stage_observations],
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.SYNTHESIZE_EVENT_ANSWER.value,
            ],
        )
        self.assertEqual(
            self.external_context_retriever.context_calls[0]["strategy"],
            "event_primary",
        )

    def test_execute_dual_primary_plan_runs_four_stages_and_returns_report(self) -> None:
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
            plan_id="plan_event_impact_analysis_dual_primary_v1",
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            stages=[
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
            stage_constraints={
                StageName.COLLECT_EVENT_CONTEXT.value: {
                    "retrieval_budget": 3,
                    "strategy": "dual_primary",
                },
                StageName.ANALYZE_TARGETS.value: {"candidate_discovery_budget": 1},
                StageName.RETRIEVE_EVIDENCE.value: {"retrieval_budget": 4},
                StageName.SYNTHESIZE_REPORT.value: {"preferred_output": "report"},
            },
            response_mode=ResponseMode.REPORT.value,
        )

        result = self.service.execute(
            request=AnalysisRequest(
                query="红海局势升级利好哪些A股航运股？",
                session_id="sess_001",
                include_trace=True,
            ),
            router_result=router_result,
            plan=plan,
            session_context=None,
        )

        self.assertIsNotNone(result.final_response)
        self.assertEqual(
            [item.stage_name for item in result.stage_observations],
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
        )
        self.assertEqual(
            self.external_context_retriever.context_calls[0]["strategy"],
            "dual_primary",
        )

    def test_execute_emits_stage_started_and_finished_events(self) -> None:
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
            plan_id="plan_event_streaming_v1",
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            stages=[
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
            stage_constraints={
                StageName.COLLECT_EVENT_CONTEXT.value: {
                    "retrieval_budget": 3,
                    "strategy": "dual_primary",
                },
                StageName.ANALYZE_TARGETS.value: {"candidate_discovery_budget": 1},
                StageName.RETRIEVE_EVIDENCE.value: {"retrieval_budget": 4},
                StageName.SYNTHESIZE_REPORT.value: {"preferred_output": "report"},
            },
            response_mode=ResponseMode.REPORT.value,
        )
        captured: list[AnalysisStreamEvent] = []

        self.service.execute(
            request=AnalysisRequest(
                query="红海局势升级利好哪些A股航运股？",
                session_id="sess_001",
                include_trace=True,
            ),
            router_result=router_result,
            plan=plan,
            session_context=None,
            event_callback=captured.append,
        )

        stage_events = [
            (item.event_type, item.stage_name, item.status)
            for item in captured
            if item.event_type.startswith("stage_")
        ]
        self.assertEqual(
            stage_events,
            [
                ("stage_started", "collect_event_context", "running"),
                ("stage_finished", "collect_event_context", "success"),
                ("stage_started", "analyze_targets", "running"),
                ("stage_finished", "analyze_targets", "success"),
                ("stage_started", "retrieve_evidence", "running"),
                ("stage_finished", "retrieve_evidence", "success"),
                ("stage_started", "synthesize_report", "running"),
                ("stage_finished", "synthesize_report", "success"),
            ],
        )
        self.assertTrue(
            all(item.duration_ms is not None for item in captured if item.event_type == "stage_finished")
        )


if __name__ == "__main__":
    unittest.main()
