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


def _build_router_result(**overrides: object) -> RouterResult:
    payload = {
        "intent": "metric_lookup",
        "follow_up_type": "none",
        "confidence": "high",
        "entities": {
            "company": "宁德时代",
            "metric": "营收",
            "time_scope": "2024Q1",
        },
        "needs": [],
        "constraints": {},
    }
    payload.update(overrides)
    return RouterResult(**payload)


def _build_request(
    query: str = "宁德时代 2024Q1 营收是多少？",
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
        normalized_claim="红海事件对航运价格的影响",
        evidence_items=[
            EvidenceItem(
                evidence_id="evd_001",
                rank=1,
                support_strength="high",
                matched_chunk_id="chunk_001",
                matched_parent_id="parent_001",
                excerpt="运价指数在相关期间明显波动。",
                parent_context="年报披露了运价与业务量变化。",
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
                company_name="示例公司",
                doc_type="annual_report",
                section_path=["经营情况讨论与分析"],
            )
        ],
    )


class OrchestratorStageRunnersTest(unittest.TestCase):
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
                "company": "宁德时代",
                "metric": "营收",
                "time_scope": "2024Q1",
                "value": "123.45",
            },
        )
        self.assertEqual(service.calls, [("宁德时代", "营收", "2024Q1")])
        self.assertIn("宁德时代", result.user_summary or "")

    def test_synthesize_brief_answer_stage_builds_final_response(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.synthesize_brief_answer import (
            run_synthesize_brief_answer_stage,
        )

        execution_state = {
            "query_structured_data": StageExecutionResult(
                stage_name="query_structured_data",
                status="success",
                output_payload={
                    "structured_result": {
                        "company": "宁德时代",
                        "metric": "营收",
                        "time_scope": "2024Q1",
                        "value": "123.45",
                    }
                },
            )
        }

        result = run_synthesize_brief_answer_stage(
            request=_build_request(session_id="sess_brief"),
            router_result=_build_router_result(),
            stage_constraints={"preferred_output": "brief_answer"},
            execution_state=execution_state,
            reporting_service=ReportingService(),
        )

        self.assertEqual(result.stage_name, "synthesize_brief_answer")
        self.assertEqual(result.status, "success")
        final_response = result.output_payload["final_response"]
        self.assertEqual(final_response.session_id, "sess_brief")
        self.assertEqual(final_response.response_type, "success")
        self.assertIn("宁德时代", final_response.summary)
        self.assertIn("123.45", final_response.summary)

    def test_retrieve_evidence_stage_builds_query_in_fixed_order_and_deduplicates(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.retrieve_evidence import (
            run_retrieve_evidence_stage,
        )

        retrieval_result = _build_retrieval_result()
        facade = _StubRetrievalFacade(retrieval_result)
        result = run_retrieve_evidence_stage(
            request=_build_request(query="给我证据"),
            router_result=_build_router_result(
                intent="evidence_lookup",
                entities={
                    "target": "航运股",
                    "claim": "红海事件对航运运价有影响",
                },
                constraints={"retrieval_budget": 3},
            ),
            stage_constraints={"retrieval_budget": 3, "target": "航运股"},
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
            "给我证据 红海事件对航运运价有影响 航运股",
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
                        "event": "红海事件",
                        "themes": ["航运", "能源", "航运"],
                        "time_scope": "2024Q1",
                    }
                },
            ),
            "analyze_targets": {
                "target_scope": ["港口", "航运", "港口"],
            },
        }
        run_retrieve_evidence_stage(
            request=_build_request(query="分析红海风险"),
            router_result=_build_router_result(
                intent="event_impact_analysis",
                entities={"target": "港口"},
            ),
            stage_constraints={"retrieval_budget": 4},
            execution_state=execution_state,
            retrieval_facade=facade,
        )

        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(
            facade.calls[0]["raw_query"],
            "分析红海风险 红海事件 航运 能源 2024Q1 港口",
        )

    def test_retrieve_evidence_stage_prefers_stage_target_and_uses_event_context_in_order(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.retrieve_evidence import (
            run_retrieve_evidence_stage,
        )

        retrieval_result = _build_retrieval_result()
        facade = _StubRetrievalFacade(retrieval_result)
        run_retrieve_evidence_stage(
            request=_build_request(query="分析红海风险"),
            router_result=_build_router_result(
                intent="event_impact_analysis",
                entities={
                    "event": "红海事件",
                    "themes": ["航运", "能源", "航运"],
                    "time_scope": "2024Q1",
                    "target": "港口",
                },
            ),
            stage_constraints={
                "retrieval_budget": 4,
                "target_scope": ["航运", "港口", "航运"],
                "target": "港口股",
            },
            execution_state={},
            retrieval_facade=facade,
        )

        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(
            facade.calls[0]["raw_query"],
            "分析红海风险 港口股 红海事件 航运 能源 2024Q1 港口",
        )

    def test_retrieve_evidence_stage_falls_back_to_router_target_when_stage_target_missing(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.retrieve_evidence import (
            run_retrieve_evidence_stage,
        )

        retrieval_result = _build_retrieval_result()
        facade = _StubRetrievalFacade(retrieval_result)
        run_retrieve_evidence_stage(
            request=_build_request(query="继续找相关证据"),
            router_result=_build_router_result(
                intent="evidence_lookup",
                entities={"target": "出海服务"},
            ),
            stage_constraints={"retrieval_budget": 2},
            execution_state={},
            retrieval_facade=facade,
        )

        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(facade.calls[0]["limit"], 2)
        self.assertEqual(
            facade.calls[0]["raw_query"],
            "继续找相关证据 出海服务",
        )

    def test_synthesize_report_stage_builds_report_response_from_retrieval_result(self) -> None:
        from finsight_agent.control_plane.orchestrator.stage_runners.synthesize_report import (
            run_synthesize_report_stage,
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

        result = run_synthesize_report_stage(
            request=_build_request(
                query="红海事件有哪些证据？",
                session_id="sess_report",
            ),
            router_result=_build_router_result(intent="evidence_lookup"),
            stage_constraints={"preferred_output": "report"},
            execution_state=execution_state,
            reporting_service=ReportingService(),
        )

        self.assertEqual(result.stage_name, "synthesize_report")
        self.assertEqual(result.status, "success")
        final_response = result.output_payload["final_response"]
        self.assertEqual(final_response.session_id, "sess_report")
        self.assertEqual(final_response.response_type, "success")
        self.assertTrue(final_response.report_blocks)
        self.assertEqual(final_response.report_blocks[0]["block_type"], "evidence_overview")
        self.assertIn("已检索到", final_response.summary)
        first_item = final_response.report_blocks[0]["items"][0]
        self.assertEqual(first_item["evidence_id"], "evd_001")
        self.assertEqual(first_item["excerpt"], "运价指数在相关期间明显波动。")
        self.assertEqual(first_item["company_name"], "示例公司")
        self.assertEqual(first_item["doc_type"], "annual_report")
        self.assertEqual(result.evidence_refs, ["evd_001"])

    def test_build_report_response_returns_minimal_final_response(self) -> None:
        service = ReportingService()
        result = service.build_report_response(
            session_id="sess_report_service",
            summary="已检索到 1 条证据。",
            report_blocks=[
                EvidenceOverviewBlock(
                    block_type="evidence_overview",
                    title="证据概览",
                    items=[
                        EvidenceOverviewItem(
                            evidence_id="evd_001",
                            excerpt="证据 1",
                            company_name="示例公司",
                            doc_type="annual_report",
                        )
                    ],
                )
            ],
            uncertainty_notes=["证据数量有限"],
            next_actions=["可继续追问更具体时间段"],
        )

        self.assertEqual(result.response_type, "success")
        self.assertEqual(result.session_id, "sess_report_service")
        self.assertEqual(result.summary, "已检索到 1 条证据。")
        self.assertEqual(result.report_blocks[0]["block_type"], "evidence_overview")
        self.assertEqual(result.uncertainty_notes, ["证据数量有限"])
        self.assertEqual(result.next_actions, ["可继续追问更具体时间段"])

    def test_build_report_response_rejects_invalid_evidence_overview_block(self) -> None:
        service = ReportingService()

        with self.assertRaises(ValueError):
            service.build_report_response(
                session_id="sess_invalid",
                summary="已检索到 1 条证据。",
                report_blocks=[
                    {
                        "block_type": "evidence_overview",
                        "title": "证据概览",
                    }
                ],
                uncertainty_notes=[],
                next_actions=[],
            )


if __name__ == "__main__":
    unittest.main()
