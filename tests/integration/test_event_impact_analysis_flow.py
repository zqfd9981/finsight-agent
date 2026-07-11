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

from finsight_agent.capabilities.retrieval.models import (
    CitationRecord,
    EvidenceItem,
    RetrievalResult,
    RetrievalScoreBreakdown,
)
from finsight_agent.control_plane.orchestrator.service import OrchestratorService
from finsight_agent.control_plane.session.repository import SessionRepository
from finsight_agent.control_plane.session.service import SessionService
from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent


class _StubRouterService:
    def route(self, query: str, session_context) -> RouterResult:
        del query, session_context
        return RouterResult(
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={
                "event": "Red Sea disruption",
                "themes": ["shipping"],
                "time_scope": "recent",
            },
            needs=["news_search", "rag_retrieval"],
            constraints={"preferred_output": "report"},
        )


class _StubStrategyClassifier:
    def __init__(self, strategy: str = "dual_primary") -> None:
        self.strategy = strategy
        self.calls: list[dict[str, object]] = []

    def classify(self, *, query, router_payload, session_topic):
        self.calls.append(
            {
                "query": query,
                "router_payload": router_payload,
                "session_topic": session_topic,
            }
        )
        return {
            "strategy": self.strategy,
            "confidence": "high",
            "reason": "test_classifier",
        }


class _StubRetrievalFacade:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def retrieve_evidence(
        self,
        raw_query: str,
        limit: int = 5,
        company_code: str | None = None,
        doc_type: str | None = None,
        report_year: int | None = None,
    ) -> RetrievalResult:
        del company_code, doc_type, report_year
        self.calls.append({"raw_query": raw_query, "limit": limit})
        return RetrievalResult(
            request_id="retrieval_event_001",
            normalized_claim=raw_query,
            evidence_items=[
                EvidenceItem(
                    evidence_id="evd_event_001",
                    rank=1,
                    support_strength="high",
                    matched_chunk_id="chunk_001",
                    matched_parent_id="parent_001",
                    excerpt="Freight pricing improved after the disruption.",
                    parent_context="Industry commentary linked route risk to rate elasticity.",
                    citation=CitationRecord(
                        document_id="doc_001",
                        page_start=3,
                        page_end=3,
                        page_anchor=3,
                    ),
                    retrieval_scores=RetrievalScoreBreakdown(
                        sparse_score=1.0,
                        dense_score=0.9,
                        rrf_score=0.7,
                        rerank_score=0.95,
                    ),
                    company_code="600026",
                    company_name="COSCO",
                    doc_type="industry_note",
                    section_path=["Event Impact"],
                )
            ],
        )

    def close(self) -> None:
        return None


class _StubExternalContextRetriever:
    def __init__(self) -> None:
        self.event_calls: list[dict[str, object]] = []

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
        return {
            "summary_hint": "The disruption increased freight-rate sensitivity.",
            "supporting_points": [
                "Detour expectations rose.",
                "Shipping chains tightened."
            ],
            "evidence_refs": ["ext_ctx_001"],
            "source_status": {
                "mode": strategy,
                "allow_local_rag": False,
            },
            "candidate_hints": ["COSCO", "China Merchants"],
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
        }


class _StubTargetAnalysisService:
    def analyze_targets(
        self,
        *,
        query: str,
        event_context: dict[str, object],
        candidate_pool: list[str],
    ) -> dict[str, object]:
        del query, event_context, candidate_pool
        return {
            "target_scope": ["COSCO", "China Merchants"],
            "ranked_targets": [
                {
                    "target": "COSCO",
                    "target_type": "company",
                    "impact_direction": "positive",
                    "reasoning_summary": "Rate elasticity is more direct for shipping carriers.",
                    "confidence": "medium",
                }
            ],
            "open_questions": ["Duration of rate support still needs confirmation."],
            "confidence": "medium",
            "analysis_mode": "llm_constrained",
        }


class EventImpactAnalysisFlowIntegrationTest(unittest.TestCase):
    def test_event_impact_analysis_uses_classifier_before_planning_and_returns_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            classifier = _StubStrategyClassifier(strategy="dual_primary")
            external_context_retriever = _StubExternalContextRetriever()
            workbench_service = WorkbenchBackendApiService(
                router_service=_StubRouterService(),
                orchestrator_service=OrchestratorService(
                    retrieval_facade=_StubRetrievalFacade(),
                    external_context_retriever=external_context_retriever,
                    target_analysis_service=_StubTargetAnalysisService(),
                ),
                session_service=SessionService(
                    repository=SessionRepository(storage_dir=Path(temp_dir) / "sessions")
                ),
                retrieval_strategy_classifier=classifier,
            )

            envelope = workbench_service.build_response(
                AnalysisRequest(
                    query="Which A-share shipping companies benefit from the Red Sea disruption?",
                    include_trace=True,
                )
            )

        self.assertEqual(envelope.response.response_type, "success")
        self.assertIn("Retrieved", envelope.response.summary)
        self.assertTrue(envelope.response.report_blocks)
        self.assertEqual(envelope.response.report_blocks[0]["block_type"], "evidence_overview")
        self.assertEqual(
            [block.block_type for block in envelope.trace_blocks],
            ["routing", "stage_planning", "execution"],
        )
        self.assertEqual(classifier.calls[0]["router_payload"]["intent"], "event_impact_analysis")
        self.assertEqual(external_context_retriever.event_calls[0]["strategy"], "dual_primary")
        self.assertEqual(
            envelope.trace_blocks[1].payload_summary["stages"],
            [
                "collect_event_context",
                "analyze_targets",
                "retrieve_evidence",
                "synthesize_answer",
            ],
        )
        self.assertEqual(envelope.trace_blocks[1].payload_summary["strategy"], "dual_primary")


if __name__ == "__main__":
    unittest.main()
