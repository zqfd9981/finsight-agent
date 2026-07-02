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
from shared.contracts.plan import Plan
from shared.contracts.router_result import RouterResult
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode


class _StubRouterService:
    def route(self, query: str, session_context) -> RouterResult:
        del query, session_context
        return RouterResult(
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={
                "event": "红海局势升级",
                "themes": ["航运"],
                "time_scope": "recent",
            },
            needs=["news_search", "rag_retrieval"],
            constraints={"preferred_output": "report"},
        )


class _StubPlannerService:
    def build_plan(self, router_result: RouterResult) -> Plan:
        del router_result
        return Plan(
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
                    excerpt="红海局势升级后，绕航预期推升了航运运价弹性。",
                    parent_context="行业跟踪材料指出航运链条可能受益于运价上行。",
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
                    company_name="中远海能",
                    doc_type="industry_note",
                    section_path=["事件影响分析"],
                )
            ],
        )

    def close(self) -> None:
        return None


class _StubExternalContextRetriever:
    def retrieve_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> dict[str, object] | None:
        del query, event, themes, time_scope, limit
        return {
            "summary_hint": "红海局势升级导致绕航和运价上行预期升温。",
            "supporting_points": ["航线扰动加剧", "油运与航运链景气弹性提升"],
            "evidence_refs": ["ext_ctx_001"],
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
            "candidates": ["中远海能", "招商轮船"],
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
            "target_scope": ["中远海能", "招商轮船"],
            "ranked_targets": [
                {
                    "target": "中远海能",
                    "target_type": "company",
                    "impact_direction": "positive",
                    "reasoning_summary": "油运运价弹性与绕航逻辑更直接相关。",
                    "confidence": "medium",
                }
            ],
            "open_questions": ["仍需跟踪运价上行的持续性。"],
            "confidence": "medium",
            "analysis_mode": "llm_constrained",
        }


class EventImpactAnalysisFlowIntegrationTest(unittest.TestCase):
    def test_event_impact_analysis_returns_report_with_targets_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbench_service = WorkbenchBackendApiService(
                router_service=_StubRouterService(),
                planner_service=_StubPlannerService(),
                orchestrator_service=OrchestratorService(
                    retrieval_facade=_StubRetrievalFacade(),
                    external_context_retriever=_StubExternalContextRetriever(),
                    target_analysis_service=_StubTargetAnalysisService(),
                ),
                session_service=SessionService(
                    repository=SessionRepository(storage_dir=Path(temp_dir) / "sessions")
                ),
            )

            envelope = workbench_service.build_response(
                AnalysisRequest(
                    query="红海局势升级利好哪些 A 股航运公司？",
                    include_trace=True,
                )
            )

        self.assertEqual(envelope.response.response_type, "success")
        self.assertIn("中远海能", envelope.response.summary)
        self.assertTrue(envelope.response.report_blocks)
        self.assertEqual(envelope.response.report_blocks[0]["block_type"], "evidence_overview")
        self.assertEqual(
            [block.block_type for block in envelope.trace_blocks],
            ["routing", "planning", "execution"],
        )


if __name__ == "__main__":
    unittest.main()
