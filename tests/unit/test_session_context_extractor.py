from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.control_plane.orchestrator.models import OrchestrationResult, StageExecutionResult
from finsight_agent.control_plane.session.extractor import SessionContextExtractor
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.final_response import FinalResponse
from shared.contracts.plan import Plan
from shared.contracts.report_block import EvidenceOverviewBlock, EvidenceOverviewItem
from shared.contracts.router_result import RouterResult


class SessionContextExtractorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.extractor = SessionContextExtractor()

    def test_extractor_builds_metric_lookup_context(self) -> None:
        request = AnalysisRequest(
            query="宁德时代 2024 年净利润是多少？",
            query_mode="first_turn",
            session_id="sess_metric",
        )
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
        orchestration_result = OrchestrationResult(
            session_id="sess_metric",
            router_result=router_result,
            plan=plan,
            final_response=FinalResponse(
                response_type="brief_answer",
                session_id="sess_metric",
                summary="宁德时代 2024 年净利润为 520 亿元。",
                next_actions=["可继续追问同比变化原因。"],
            ),
        )

        context = self.extractor.extract(
            request=request,
            router_result=router_result,
            plan=plan,
            orchestration_result=orchestration_result,
        )

        self.assertEqual(context.session_id, "sess_metric")
        self.assertEqual(context.active_topic, "宁德时代 2024_annual net_profit")
        self.assertEqual(context.active_candidates, ["宁德时代"])
        self.assertEqual(context.key_evidence_refs, [])
        self.assertIn("净利润查询", context.history_summary)
        self.assertEqual(context.available_follow_ups, ["drilldown", "expand"])

    def test_extractor_builds_evidence_lookup_context(self) -> None:
        request = AnalysisRequest(
            query="把中远海能受益逻辑的证据展开一下",
            query_mode="follow_up",
            session_id="sess_evidence",
        )
        router_result = RouterResult(
            intent="evidence_lookup",
            follow_up_type="drilldown",
            confidence="high",
            entities={
                "target": "中远海能 vs 招商轮船",
                "claim": "中远海能和招商轮船谁更受益",
            },
            needs=["rag_retrieval"],
            constraints={"preferred_output": "report"},
        )
        plan = Plan(
            plan_id="plan_evidence_lookup_v1",
            intent="evidence_lookup",
            stages=["retrieve_evidence", "synthesize_report"],
            stage_constraints={},
            response_mode="report",
        )
        orchestration_result = OrchestrationResult(
            session_id="sess_evidence",
            router_result=router_result,
            plan=plan,
            final_response=FinalResponse(
                response_type="report",
                session_id="sess_evidence",
                summary="已检索到 2 条证据，可用于继续研判。",
                report_blocks=[
                    EvidenceOverviewBlock(
                        block_type="evidence_overview",
                        title="证据概览",
                        items=[
                            EvidenceOverviewItem(
                                evidence_id="ev_001",
                                excerpt="中远海能受益于运价上行。",
                                company_name="中远海能",
                                doc_type="annual_report",
                            ),
                            EvidenceOverviewItem(
                                evidence_id="ev_002",
                                excerpt="招商轮船同样受益于油运景气。",
                                company_name="招商轮船",
                                doc_type="annual_report",
                            ),
                        ],
                    )
                ],
            ),
            stage_observations=[],
        )
        orchestration_result.stage_observations.append(
            self._build_stage_observation_result(["ev_001", "ev_002"])
        )

        context = self.extractor.extract(
            request=request,
            router_result=router_result,
            plan=plan,
            orchestration_result=orchestration_result,
        )

        self.assertEqual(context.session_id, "sess_evidence")
        self.assertEqual(context.active_topic, "中远海能和招商轮船谁更受益")
        self.assertEqual(context.active_candidates, ["中远海能", "招商轮船"])
        self.assertEqual(context.key_evidence_refs, ["ev_001", "ev_002"])
        self.assertIn("已补充关键证据引用", context.history_summary)
        self.assertEqual(context.available_follow_ups, ["compare", "drilldown", "expand"])

    def test_extractor_limits_candidate_and_evidence_counts(self) -> None:
        request = AnalysisRequest(
            query="展开一下这些公司的证据",
            query_mode="follow_up",
            session_id="sess_limit",
        )
        router_result = RouterResult(
            intent="evidence_lookup",
            follow_up_type="expand",
            confidence="high",
            entities={
                "target": "中远海能 vs 招商轮船 vs 宁德时代 vs 贵州茅台",
                "claim": "比较不同公司的受益逻辑",
            },
            needs=["rag_retrieval"],
            constraints={"preferred_output": "report"},
        )
        plan = Plan(
            plan_id="plan_evidence_lookup_v1",
            intent="evidence_lookup",
            stages=["retrieve_evidence", "synthesize_report"],
            stage_constraints={},
            response_mode="report",
        )
        orchestration_result = OrchestrationResult(
            session_id="sess_limit",
            router_result=router_result,
            plan=plan,
            final_response=FinalResponse(
                response_type="report",
                session_id="sess_limit",
                summary="已检索到多条证据。",
                report_blocks=[
                    EvidenceOverviewBlock(
                        block_type="evidence_overview",
                        title="证据概览",
                        items=[
                            EvidenceOverviewItem(
                                evidence_id=f"ev_00{i}",
                                excerpt=f"excerpt-{i}",
                                company_name=company_name,
                                doc_type="annual_report",
                            )
                            for i, company_name in enumerate(
                                ["中远海能", "招商轮船", "宁德时代", "贵州茅台", "比亚迪", "中国船舶"],
                                start=1,
                            )
                        ],
                    )
                ],
            ),
        )
        orchestration_result.stage_observations.append(
            self._build_stage_observation_result(
                ["ev_001", "ev_002", "ev_003", "ev_004", "ev_005", "ev_006"]
            )
        )

        context = self.extractor.extract(
            request=request,
            router_result=router_result,
            plan=plan,
            orchestration_result=orchestration_result,
        )

        self.assertEqual(context.active_candidates, ["中远海能", "招商轮船", "宁德时代"])
        self.assertEqual(
            context.key_evidence_refs,
            ["ev_001", "ev_002", "ev_003", "ev_004", "ev_005"],
        )

    def _build_stage_observation_result(self, evidence_refs: list[str]) -> object:
        return type(
            "ObservationStub",
            (),
            {
                "stage_name": "retrieve_evidence",
                "output_summary": {"evidence_refs": evidence_refs},
            },
        )()


if __name__ == "__main__":
    unittest.main()
