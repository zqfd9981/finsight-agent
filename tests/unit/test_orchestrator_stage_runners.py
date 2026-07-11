from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.capabilities.retrieval.models import (
    CitationRecord,
    EvidenceItem,
    RetrievalResult,
    RetrievalScoreBreakdown,
)
from finsight_agent.control_plane.orchestrator.models import StageExecutionResult
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.report_block import EvidenceOverviewBlock, EvidenceOverviewItem
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.enums.stage_name import StageName


class _StubStructuredDataService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def query_metric_lookup(
        self,
        company: str,
        metric: str,
        time_scope: str,
    ) -> dict[str, str]:
        self.calls.append((company, metric, time_scope))
        return {
            "company": company,
            "metric": metric,
            "time_scope": time_scope,
            "value": "123.45",
        }


class _StubRetrievalFacade:
    def __init__(self, retrieval_result: RetrievalResult) -> None:
        self.retrieval_result = retrieval_result
        self.calls: list[dict[str, object]] = []

    def retrieve_evidence(
        self,
        raw_query: str,
        limit: int = 5,
        company_code: str | None = None,
        doc_type: str | None = None,
        report_year: int | None = None,
    ) -> RetrievalResult:
        self.calls.append(
            {
                "raw_query": raw_query,
                "limit": limit,
                "company_code": company_code,
                "doc_type": doc_type,
                "report_year": report_year,
            }
        )
        return self.retrieval_result


class _StubExternalContextRetriever:
    def __init__(
        self,
        *,
        event_context_payload: dict[str, object] | None = None,
        candidate_discovery_payload: dict[str, object] | None = None,
    ) -> None:
        self.event_context_payload = event_context_payload
        self.candidate_discovery_payload = candidate_discovery_payload
        self.event_calls: list[dict[str, object]] = []
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
        self.event_calls.append(
            {
                "query": query,
                "event": event,
                "themes": themes,
                "time_scope": time_scope,
                "limit": limit,
                "strategy": strategy,
            }
        )
        return self.event_context_payload

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
        return self.candidate_discovery_payload


class _StubTargetAnalysisService:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
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
        return self.payload


class _StubLlmClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def complete_json(self, *, prompt_name: str, variables: dict[str, object]) -> dict[str, object]:
        del prompt_name, variables
        return self.payload


def _build_router_result(**overrides: object) -> RouterResult:
    payload = {
        "intent": "metric_lookup",
        "follow_up_type": "none",
        "confidence": "high",
        "entities": {
            "company": "CATL",
            "metric": "revenue",
            "time_scope": "2024Q1",
        },
        "needs": [],
        "constraints": {},
    }
    payload.update(overrides)
    return RouterResult(**payload)


def _build_request(
    query: str = "CATL 2024Q1 revenue?",
    session_id: str | None = "sess_001",
) -> AnalysisRequest:
    return AnalysisRequest(
        query=query,
        session_id=session_id,
        query_mode="first_turn",
    )


def _build_retrieval_result() -> RetrievalResult:
    return RetrievalResult(
        request_id="req_001",
        normalized_claim="shipping rates moved after the event",
        evidence_items=[
            EvidenceItem(
                evidence_id="evd_001",
                rank=1,
                support_strength="high",
                matched_chunk_id="chunk_001",
                matched_parent_id="parent_001",
                excerpt="Shipping rates moved materially during the event window.",
                parent_context="The report linked freight pricing to route disruptions.",
                citation=CitationRecord(
                    document_id="doc_001",
                    page_start=12,
                    page_end=12,
                    page_anchor=12,
                ),
                retrieval_scores=RetrievalScoreBreakdown(
                    sparse_score=1.2,
                    dense_score=0.8,
                    rrf_score=0.6,
                    rerank_score=0.9,
                ),
                company_code="600000",
                company_name="Example Shipping",
                doc_type="annual_report",
                section_path=["Management Discussion"],
            )
        ],
    )


class OrchestratorStageRunnersTest(unittest.TestCase):
    def test_target_analysis_service_rejects_invalid_ranked_targets_payload(self) -> None:
        from finsight_agent.control_plane.orchestrator.target_analysis import (
            TargetAnalysisService,
        )

        service = TargetAnalysisService(llm_client=_StubLlmClient({"target_scope": ["COSCO"]}))

        with self.assertRaises(ValueError):
            service.analyze_targets(
                query="Which A-share shippers benefit?",
                event_context={"event": "Red Sea disruption", "themes": ["shipping"]},
                candidate_pool=["COSCO"],
            )

    def test_collect_event_context_stage_merges_external_and_local_retrieval(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.collect_event_context import (
            run_collect_event_context_stage,
        )

        retrieval_result = _build_retrieval_result()
        facade = _StubRetrievalFacade(retrieval_result)
        external_retriever = _StubExternalContextRetriever(
            event_context_payload={
                "summary_hint": "Route disruptions tightened near-term freight expectations.",
                "supporting_points": ["Detours increased voyage distance."],
                "evidence_refs": ["ext_001"],
                "source_status": {"local_rag_needed": True},
            }
        )

        result = run_collect_event_context_stage(
            request=_build_request(query="Who benefits from the Red Sea disruption?"),
            router_result=_build_router_result(
                intent="event_impact_analysis",
                entities={
                    "event": "Red Sea disruption",
                    "themes": ["shipping", "energy"],
                    "time_scope": "recent",
                },
            ),
            stage_constraints={"retrieval_budget": 3, "strategy": "dual_primary"},
            execution_state={},
            retrieval_facade=facade,
            external_context_retriever=external_retriever,
        )

        self.assertEqual(result.stage_name, "collect_event_context")
        self.assertEqual(result.status, "success")
        event_context = result.output_payload["event_context"]
        self.assertEqual(event_context["event"], "Red Sea disruption")
        self.assertEqual(event_context["themes"], ["shipping", "energy"])
        self.assertIn("Route disruptions", event_context["context_summary"])
        self.assertEqual(result.output_payload["strategy"], "dual_primary")
        self.assertEqual(result.evidence_refs, ["ext_001", "evd_001"])
        self.assertEqual(external_retriever.event_calls[0]["strategy"], "dual_primary")
        self.assertEqual(len(facade.calls), 1)

    def test_collect_event_context_stage_skips_local_rag_when_external_context_is_sufficient(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.collect_event_context import (
            run_collect_event_context_stage,
        )

        facade = _StubRetrievalFacade(_build_retrieval_result())
        external_retriever = _StubExternalContextRetriever(
            event_context_payload={
                "summary_hint": "External context is already sufficient.",
                "supporting_points": ["Detour expectations remain elevated."],
                "evidence_refs": ["bocha:001", "cninfo:001"],
                "source_status": {
                    "mode": "dual_primary",
                    "allow_local_rag": False,
                },
            }
        )

        result = run_collect_event_context_stage(
            request=_build_request(query="Who benefits from the Red Sea disruption?"),
            router_result=_build_router_result(
                intent="event_impact_analysis",
                entities={
                    "event": "Red Sea disruption",
                    "themes": ["shipping", "energy"],
                    "time_scope": "recent",
                },
            ),
            stage_constraints={"retrieval_budget": 3, "strategy": "dual_primary"},
            execution_state={},
            retrieval_facade=facade,
            external_context_retriever=external_retriever,
        )

        self.assertEqual(result.stage_name, "collect_event_context")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.evidence_refs, ["bocha:001", "cninfo:001"])
        self.assertEqual(result.output_payload["source_status"]["local_evidence_count"], 0)
        self.assertEqual(result.output_payload["strategy"], "dual_primary")
        self.assertEqual(facade.calls, [])

    def test_analyze_targets_stage_returns_degraded_when_candidate_discovery_is_empty(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.analyze_targets import (
            run_analyze_targets_stage,
        )

        external_retriever = _StubExternalContextRetriever(
            candidate_discovery_payload={"candidates": []}
        )
        target_analysis_service = _StubTargetAnalysisService(
            {
                "target_scope": ["COSCO"],
                "ranked_targets": [
                    {
                        "target": "COSCO",
                        "target_type": "company",
                        "impact_direction": "positive",
                        "reasoning_summary": "Higher freight elasticity may help.",
                        "confidence": "medium",
                    }
                ],
            }
        )
        execution_state = {
            "collect_event_context": StageExecutionResult(
                stage_name="collect_event_context",
                status="success",
                output_payload={
                    "event_context": {
                        "event": "Red Sea disruption",
                        "themes": ["shipping"],
                        "time_scope": "recent",
                        "context_summary": "Context confirmed.",
                        "supporting_points": ["Rates may remain resilient."],
                        "evidence_refs": ["evd_001"],
                    },
                    "event_entities": {
                        "event": "Red Sea disruption",
                        "themes": ["shipping"],
                        "time_scope": "recent",
                    },
                },
                evidence_refs=["evd_001"],
            )
        }

        result = run_analyze_targets_stage(
            request=_build_request(query="Which A-share shippers benefit?"),
            router_result=_build_router_result(
                intent="event_impact_analysis",
                entities={
                    "event": "Red Sea disruption",
                    "themes": ["shipping"],
                    "time_scope": "recent",
                },
            ),
            stage_constraints={"candidate_discovery_budget": 1},
            execution_state=execution_state,
            session_context=SessionContext(session_id="sess_001"),
            external_context_retriever=external_retriever,
            target_analysis_service=target_analysis_service,
        )

        self.assertEqual(result.stage_name, "analyze_targets")
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.output_payload["target_scope"], [])
        self.assertEqual(result.output_payload["ranked_targets"], [])
        self.assertTrue(result.output_payload["open_questions"])
        self.assertEqual(len(external_retriever.discovery_calls), 1)
        self.assertEqual(target_analysis_service.calls, [])

    def test_query_structured_data_stage_returns_stage_execution_result(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.query_structured_data import (
            run_query_structured_data_stage,
        )

        service = _StubStructuredDataService()
        result = run_query_structured_data_stage(
            request=_build_request(),
            router_result=_build_router_result(),
            stage_constraints={"time_hint": "2024Q1"},
            execution_state={},
            structured_data_service=service,
        )

        self.assertIsInstance(result, StageExecutionResult)
        self.assertEqual(result.stage_name, "query_structured_data")
        self.assertEqual(result.status, "success")
        self.assertEqual(
            result.output_payload["structured_result"],
            {
                "company": "CATL",
                "metric": "revenue",
                "time_scope": "2024Q1",
                "value": "123.45",
            },
        )
        self.assertEqual(service.calls, [("CATL", "revenue", "2024Q1")])
        self.assertIn("CATL", result.user_summary or "")

    def test_synthesize_brief_answer_stage_builds_final_response(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.synthesize_answer import (
            run_synthesize_answer_stage,
        )

        execution_state = {
            "query_structured_data": StageExecutionResult(
                stage_name="query_structured_data",
                status="success",
                output_payload={
                    "structured_result": {
                        "company": "CATL",
                        "metric": "revenue",
                        "time_scope": "2024Q1",
                        "value": "123.45",
                    }
                },
            )
        }

        result = run_synthesize_answer_stage(
            request=_build_request(session_id="sess_brief"),
            router_result=_build_router_result(),
            stage_constraints={
                "response_mode": "brief_answer",
                "preferred_output": "brief_answer",
            },
            execution_state=execution_state,
            reporting_service=ReportingService(),
        )

        self.assertEqual(result.stage_name, "synthesize_answer")
        self.assertEqual(result.status, "success")
        final_response = result.output_payload["final_response"]
        self.assertEqual(final_response.session_id, "sess_brief")
        self.assertEqual(final_response.response_type, "success")
        self.assertIn("CATL", final_response.summary)
        self.assertIn("123.45", final_response.summary)

    def test_synthesize_event_answer_stage_builds_final_response(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.synthesize_answer import (
            run_synthesize_answer_stage,
        )

        execution_state = {
            StageName.COLLECT_EVENT_CONTEXT.value: StageExecutionResult(
                stage_name=StageName.COLLECT_EVENT_CONTEXT.value,
                status="success",
                output_payload={
                    "event_context": {
                        "event": "Red Sea disruption",
                        "context_summary": "Freight expectations tightened after route disruptions.",
                        "supporting_points": ["Voyage distances increased."],
                        "evidence_refs": ["ext_001"],
                    },
                    "source_status": {"mode": "event_primary"},
                    "strategy": "event_primary",
                },
            )
        }

        result = run_synthesize_answer_stage(
            request=_build_request(
                query="What changed in the Red Sea disruption background?",
                session_id="sess_event",
            ),
            router_result=_build_router_result(intent="event_impact_analysis"),
            stage_constraints={
                "response_mode": "event_answer",
                "preferred_output": "brief_answer",
            },
            execution_state=execution_state,
            reporting_service=ReportingService(),
        )

        self.assertEqual(result.stage_name, "synthesize_answer")
        self.assertEqual(result.status, "success")
        final_response = result.output_payload["final_response"]
        self.assertEqual(final_response.session_id, "sess_event")
        self.assertEqual(final_response.report_blocks, [])
        self.assertIn("Freight expectations tightened", final_response.summary)
        self.assertEqual(result.evidence_refs, ["ext_001"])

    def test_retrieve_evidence_stage_builds_query_in_fixed_order_and_deduplicates(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.retrieve_evidence import (
            run_retrieve_evidence_stage,
        )

        retrieval_result = _build_retrieval_result()
        facade = _StubRetrievalFacade(retrieval_result)
        result = run_retrieve_evidence_stage(
            request=_build_request(query="Show me the evidence"),
            router_result=_build_router_result(
                intent="evidence_lookup",
                entities={
                    "target": "shipping",
                    "claim": "the event impacted shipping rates",
                },
                constraints={"retrieval_budget": 3},
            ),
            stage_constraints={"retrieval_budget": 3, "target": "shipping"},
            execution_state={},
            retrieval_facade=facade,
        )

        self.assertEqual(result.stage_name, "retrieve_evidence")
        self.assertEqual(result.status, "success")
        self.assertIs(result.output_payload["retrieval_result"], retrieval_result)
        self.assertEqual(result.evidence_refs, ["evd_001"])
        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(facade.calls[0]["limit"], 3)
        self.assertEqual(
            facade.calls[0]["raw_query"],
            "Show me the evidence the event impacted shipping rates shipping",
        )

    def test_retrieve_evidence_stage_consumes_execution_state_context_in_order(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.retrieve_evidence import (
            run_retrieve_evidence_stage,
        )

        retrieval_result = _build_retrieval_result()
        facade = _StubRetrievalFacade(retrieval_result)
        execution_state = {
            "collect_event_context": StageExecutionResult(
                stage_name="collect_event_context",
                status="success",
                output_payload={
                    "event_context": {
                        "event": "Red Sea disruption",
                        "themes": ["shipping", "energy", "shipping"],
                        "time_scope": "2024Q1",
                    }
                },
            ),
            "analyze_targets": {
                "target_scope": ["ports", "shipping", "ports"],
            },
        }
        run_retrieve_evidence_stage(
            request=_build_request(query="Analyze Red Sea risk"),
            router_result=_build_router_result(
                intent="event_impact_analysis",
                entities={"target": "ports"},
            ),
            stage_constraints={"retrieval_budget": 4},
            execution_state=execution_state,
            retrieval_facade=facade,
        )

        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(
            facade.calls[0]["raw_query"],
            "Analyze Red Sea risk Red Sea disruption shipping energy 2024Q1 ports",
        )

    def test_retrieve_evidence_stage_prefers_stage_target_and_uses_event_context_in_order(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.retrieve_evidence import (
            run_retrieve_evidence_stage,
        )

        retrieval_result = _build_retrieval_result()
        facade = _StubRetrievalFacade(retrieval_result)
        run_retrieve_evidence_stage(
            request=_build_request(query="Analyze Red Sea risk"),
            router_result=_build_router_result(
                intent="event_impact_analysis",
                entities={
                    "event": "Red Sea disruption",
                    "themes": ["shipping", "energy", "shipping"],
                    "time_scope": "2024Q1",
                    "target": "ports",
                },
            ),
            stage_constraints={
                "retrieval_budget": 4,
                "target_scope": ["shipping", "ports", "shipping"],
                "target": "port operators",
            },
            execution_state={},
            retrieval_facade=facade,
        )

        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(
            facade.calls[0]["raw_query"],
            "Analyze Red Sea risk port operators Red Sea disruption shipping energy 2024Q1 ports",
        )

    def test_retrieve_evidence_stage_falls_back_to_router_target_when_stage_target_missing(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.retrieve_evidence import (
            run_retrieve_evidence_stage,
        )

        retrieval_result = _build_retrieval_result()
        facade = _StubRetrievalFacade(retrieval_result)
        run_retrieve_evidence_stage(
            request=_build_request(query="Continue finding evidence"),
            router_result=_build_router_result(
                intent="evidence_lookup",
                entities={"target": "offshore services"},
            ),
            stage_constraints={"retrieval_budget": 2},
            execution_state={},
            retrieval_facade=facade,
        )

        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(facade.calls[0]["limit"], 2)
        self.assertEqual(
            facade.calls[0]["raw_query"],
            "Continue finding evidence offshore services",
        )

    def test_synthesize_report_stage_builds_report_response_from_retrieval_result(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.synthesize_answer import (
            run_synthesize_answer_stage,
        )

        retrieval_result = _build_retrieval_result()
        execution_state = {
            "retrieve_evidence": StageExecutionResult(
                stage_name="retrieve_evidence",
                status="success",
                output_payload={"retrieval_result": retrieval_result},
                evidence_refs=["evd_001"],
            )
        }

        result = run_synthesize_answer_stage(
            request=_build_request(
                query="What evidence do we have?",
                session_id="sess_report",
            ),
            router_result=_build_router_result(intent="evidence_lookup"),
            stage_constraints={
                "response_mode": "report",
                "preferred_output": "report",
            },
            execution_state=execution_state,
            reporting_service=ReportingService(),
        )

        self.assertEqual(result.stage_name, "synthesize_answer")
        self.assertEqual(result.status, "success")
        final_response = result.output_payload["final_response"]
        self.assertEqual(final_response.session_id, "sess_report")
        self.assertEqual(final_response.response_type, "success")
        self.assertTrue(final_response.report_blocks)
        self.assertEqual(final_response.report_blocks[0]["block_type"], "evidence_overview")
        self.assertIn("Retrieved 1 evidence items", final_response.summary)
        first_item = final_response.report_blocks[0]["items"][0]
        self.assertEqual(first_item["evidence_id"], "evd_001")
        self.assertEqual(first_item["excerpt"], "Shipping rates moved materially during the event window.")
        self.assertEqual(first_item["company_name"], "Example Shipping")
        self.assertEqual(first_item["doc_type"], "annual_report")
        self.assertEqual(result.evidence_refs, ["evd_001"])

    def test_build_report_response_returns_minimal_final_response(self) -> None:
        service = ReportingService()
        result = service.build_report_response(
            session_id="sess_report_service",
            summary="Retrieved 1 evidence item.",
            report_blocks=[
                EvidenceOverviewBlock(
                    block_type="evidence_overview",
                    title="Evidence Overview",
                    items=[
                        EvidenceOverviewItem(
                            evidence_id="evd_001",
                            excerpt="Evidence 1",
                            company_name="Example Shipping",
                            doc_type="annual_report",
                        )
                    ],
                )
            ],
            uncertainty_notes=["Evidence coverage is still limited."],
            next_actions=["Narrow the time window."],
        )

        self.assertEqual(result.response_type, "success")
        self.assertEqual(result.session_id, "sess_report_service")
        self.assertEqual(result.summary, "Retrieved 1 evidence item.")
        self.assertEqual(result.report_blocks[0]["block_type"], "evidence_overview")
        self.assertEqual(result.uncertainty_notes, ["Evidence coverage is still limited."])
        self.assertEqual(result.next_actions, ["Narrow the time window."])

    def test_build_report_response_rejects_invalid_evidence_overview_block(self) -> None:
        service = ReportingService()

        with self.assertRaises(ValueError):
            service.build_report_response(
                session_id="sess_invalid",
                summary="Retrieved 1 evidence item.",
                report_blocks=[
                    {
                        "block_type": "evidence_overview",
                        "title": "Evidence Overview",
                    }
                ],
                uncertainty_notes=[],
                next_actions=[],
            )

    def test_build_report_response_populates_answer_markdown_from_llm(self) -> None:
        service = ReportingService(
            llm_client=_StubLlmClient(
                {
                    "answer_markdown": "This is the final answer.",
                    "answer_confidence": "high",
                }
            )
        )

        result = service.build_report_response(
            session_id="sess_answer",
            summary="Initial conclusion is ready.",
            report_blocks=[
                EvidenceOverviewBlock(
                    block_type="evidence_overview",
                    title="Evidence Overview",
                    items=[
                        EvidenceOverviewItem(
                            evidence_id="evd_001",
                            excerpt="Evidence 1",
                            company_name="Example Shipping",
                            doc_type="annual_report",
                        )
                    ],
                )
            ],
            uncertainty_notes=["Evidence is still limited."],
            next_actions=["Keep asking follow-ups."],
            final_answer_context={
                "query": "What changed in the Red Sea disruption?",
                "strategy": "event_primary",
                "event_evidence_count": 1,
                "company_evidence_count": 0,
            },
        )

        self.assertEqual(result.answer_markdown, "This is the final answer.")

    def test_build_brief_response_populates_answer_markdown(self) -> None:
        service = ReportingService(
            llm_client=_StubLlmClient(
                {
                    "answer_markdown": "CATL revenue in 2024Q1 was 123.45.",
                    "answer_confidence": "high",
                }
            )
        )

        result = service.build_brief_response(
            session_id="sess_brief_answer",
            summary="CATL revenue in 2024Q1 was 123.45.",
            final_answer_context={
                "query": "CATL 2024Q1 revenue?",
                "intent": "metric_lookup",
                "strategy": "structured_data",
            },
        )

        self.assertEqual(result.answer_markdown, "CATL revenue in 2024Q1 was 123.45.")


if __name__ == "__main__":
    unittest.main()
