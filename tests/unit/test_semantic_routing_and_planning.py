from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.control_plane.planner.service import PlannerService
from finsight_agent.control_plane.router.service import RouterService
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName


class SemanticRoutingAndPlanningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = RouterService()
        self.planner = PlannerService()

    def test_router_classifies_metric_lookup_with_entities(self) -> None:
        result = self.router.route(
            query="宁德时代 2024 年净利润是多少？",
            session_context=None,
        )

        self.assertEqual(result.intent, Intent.METRIC_LOOKUP.value)
        self.assertEqual(result.follow_up_type, FollowUpType.NONE.value)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.entities["company"], "宁德时代")
        self.assertEqual(result.entities["metric"], "net_profit")
        self.assertEqual(result.entities["time_scope"], "2024_annual")
        self.assertEqual(result.needs, ["structured_data_query"])
        self.assertEqual(result.constraints["preferred_output"], "brief_answer")

    def test_router_classifies_event_impact_analysis(self) -> None:
        result = self.router.route(
            query="红海局势升级利好哪些 A 股航运公司？",
            session_context=None,
        )

        self.assertEqual(result.intent, Intent.EVENT_IMPACT_ANALYSIS.value)
        self.assertEqual(result.follow_up_type, FollowUpType.NONE.value)
        self.assertEqual(result.entities["event"], "红海局势升级")
        self.assertIn("航运", result.entities["themes"])
        self.assertEqual(result.entities["time_scope"], "recent")
        self.assertEqual(
            result.needs,
            ["news_search", "concept_mapping", "rag_retrieval"],
        )
        self.assertEqual(result.constraints["time_hint"], "recent")
        self.assertEqual(result.constraints["preferred_output"], "report")

    def test_router_classifies_evidence_lookup_as_drilldown(self) -> None:
        session_context = SessionContext(
            session_id="sess_001",
            active_topic="红海航运扰动对 A 股航运链的影响",
            active_candidates=["中远海能"],
            history_summary="上一轮已经判断中远海能可能受益。",
            available_follow_ups=["drilldown", "compare", "expand"],
        )

        result = self.router.route(
            query="把中远海能受益逻辑的证据展开一下",
            session_context=session_context,
        )

        self.assertEqual(result.intent, Intent.EVIDENCE_LOOKUP.value)
        self.assertEqual(result.follow_up_type, FollowUpType.DRILLDOWN.value)
        self.assertEqual(result.entities["target"], "中远海能")
        self.assertIn("证据", result.entities["claim"])
        self.assertEqual(result.needs, ["rag_retrieval"])
        self.assertEqual(result.constraints["preferred_output"], "report")

    def test_router_marks_compare_follow_up_without_changing_intent_family(self) -> None:
        session_context = SessionContext(
            session_id="sess_001",
            active_topic="红海航运扰动对 A 股航运链的影响",
            active_candidates=["中远海能", "招商轮船"],
            history_summary="上一轮已经收敛到两家油运公司。",
            available_follow_ups=["compare", "drilldown"],
        )

        result = self.router.route(
            query="对比一下中远海能和招商轮船谁更受益",
            session_context=session_context,
        )

        self.assertEqual(result.follow_up_type, FollowUpType.COMPARE.value)
        self.assertEqual(result.intent, Intent.EVIDENCE_LOOKUP.value)
        self.assertEqual(result.entities["target"], "中远海能 vs 招商轮船")

    def test_router_marks_redirect_for_topic_switch(self) -> None:
        session_context = SessionContext(
            session_id="sess_001",
            active_topic="红海航运扰动对 A 股航运链的影响",
            history_summary="上一轮在讨论航运链。",
            available_follow_ups=["drilldown", "expand"],
        )

        result = self.router.route(
            query="顺便说说贵州茅台 2024 年营收是多少",
            session_context=session_context,
        )

        self.assertEqual(result.intent, Intent.METRIC_LOOKUP.value)
        self.assertEqual(result.follow_up_type, FollowUpType.REDIRECT.value)
        self.assertEqual(result.entities["company"], "贵州茅台")
        self.assertEqual(result.entities["metric"], "revenue")

    def test_router_marks_out_of_scope_for_price_prediction(self) -> None:
        result = self.router.route(
            query="预测一下比亚迪下周股价走势",
            session_context=None,
        )

        self.assertEqual(result.intent, Intent.OUT_OF_SCOPE.value)
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.needs, [])
        self.assertEqual(result.constraints["preferred_output"], "guardrail")

    def test_planner_builds_metric_lookup_fast_path(self) -> None:
        router_result = self.router.route(
            query="宁德时代 2024 年净利润是多少？",
            session_context=None,
        )

        plan = self.planner.build_plan(router_result)

        self.assertEqual(plan.intent, Intent.METRIC_LOOKUP.value)
        self.assertEqual(
            plan.stages,
            [
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ],
        )
        self.assertEqual(
            plan.stage_constraints["query_structured_data"]["time_hint"],
            "2024_annual",
        )
        self.assertEqual(
            plan.stage_constraints["synthesize_brief_answer"]["preferred_output"],
            "brief_answer",
        )
        self.assertEqual(plan.response_mode, ResponseMode.BRIEF_ANSWER.value)

    def test_planner_builds_event_analysis_full_plan(self) -> None:
        router_result = self.router.route(
            query="红海局势升级利好哪些 A 股航运公司？",
            session_context=None,
        )

        plan = self.planner.build_plan(router_result)

        self.assertEqual(plan.intent, Intent.EVENT_IMPACT_ANALYSIS.value)
        self.assertEqual(
            plan.stages,
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
        )
        self.assertEqual(
            plan.stage_constraints["collect_event_context"]["time_hint"],
            "recent",
        )
        self.assertEqual(
            plan.stage_constraints["collect_event_context"]["retrieval_budget"],
            3,
        )
        self.assertEqual(
            plan.stage_constraints["retrieve_evidence"]["retrieval_budget"],
            4,
        )
        self.assertEqual(plan.response_mode, ResponseMode.REPORT.value)

    def test_planner_builds_evidence_lookup_short_plan(self) -> None:
        session_context = SessionContext(
            session_id="sess_001",
            active_topic="红海航运扰动对 A 股航运链的影响",
            active_candidates=["中远海能"],
            history_summary="上一轮已经判断中远海能可能受益。",
            available_follow_ups=["drilldown"],
        )

        router_result = self.router.route(
            query="把中远海能受益逻辑的证据展开一下",
            session_context=session_context,
        )

        plan = self.planner.build_plan(router_result)

        self.assertEqual(plan.intent, Intent.EVIDENCE_LOOKUP.value)
        self.assertEqual(
            plan.stages,
            [
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
        )
        self.assertEqual(
            plan.stage_constraints["retrieve_evidence"]["retrieval_budget"],
            4,
        )
        self.assertEqual(plan.response_mode, ResponseMode.REPORT.value)

    def test_planner_marks_out_of_scope_without_regular_plan(self) -> None:
        router_result = self.router.route(
            query="预测一下比亚迪下周股价走势",
            session_context=None,
        )

        plan = self.planner.build_plan(router_result)

        self.assertEqual(plan.intent, Intent.OUT_OF_SCOPE.value)
        self.assertEqual(plan.stages, [])
        self.assertEqual(plan.response_mode, ResponseMode.BRIEF_ANSWER.value)
        self.assertEqual(plan.stage_constraints["guardrail"]["preferred_output"], "guardrail")

    def test_analysis_request_can_be_routed_using_frozen_request_fields(self) -> None:
        request = AnalysisRequest(
            query="继续展开一下这个指标同比变化的原因。",
            query_mode="follow_up",
            session_id="sess_stub",
            include_trace=True,
        )
        session_context = SessionContext(
            session_id=request.session_id or "",
            active_topic="宁德时代 2024 年净利润",
            active_candidates=["宁德时代"],
            history_summary="上一轮已返回净利润结果。",
            available_follow_ups=["drilldown", "expand"],
        )

        result = self.router.route(
            query=request.query,
            session_context=session_context,
        )

        self.assertEqual(result.follow_up_type, FollowUpType.DRILLDOWN.value)

    def test_router_prefers_llm_structured_result_when_available(self) -> None:
        llm_payload = {
            "intent": Intent.EVENT_IMPACT_ANALYSIS.value,
            "follow_up_type": FollowUpType.NONE.value,
            "confidence": "high",
            "entities": {
                "event": "红海局势升级",
                "themes": ["航运", "油运"],
                "time_scope": "recent",
            },
            "needs": ["news_search", "concept_mapping", "rag_retrieval"],
            "constraints": {
                "time_hint": "recent",
                "preferred_output": "report",
            },
        }
        router = RouterService(llm_client=FakeLlmClient([llm_payload]))

        result = router.route("宁德时代 2024 年净利润是多少？", session_context=None)

        self.assertEqual(result.intent, Intent.EVENT_IMPACT_ANALYSIS.value)
        self.assertEqual(result.entities["event"], "红海局势升级")

    def test_router_falls_back_to_rules_when_llm_unavailable(self) -> None:
        router = RouterService(llm_client=RaisingLlmClient())

        result = router.route("宁德时代 2024 年净利润是多少？", session_context=None)

        self.assertEqual(result.intent, Intent.METRIC_LOOKUP.value)
        self.assertEqual(result.entities["company"], "宁德时代")

    def test_planner_falls_back_when_llm_plan_changes_intent(self) -> None:
        llm_payload = {
            "plan_id": "plan_from_llm",
            "intent": Intent.EVIDENCE_LOOKUP.value,
            "stages": [
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
            "stage_constraints": {
                StageName.RETRIEVE_EVIDENCE.value: {"retrieval_budget": 2},
                StageName.SYNTHESIZE_REPORT.value: {"preferred_output": "report"},
            },
            "response_mode": ResponseMode.REPORT.value,
        }
        planner = PlannerService(llm_client=FakeLlmClient([llm_payload]))

        plan = planner.build_plan(
            RouterResult(
                intent=Intent.METRIC_LOOKUP.value,
                follow_up_type=FollowUpType.NONE.value,
                confidence="high",
                entities={"company": "宁德时代", "metric": "net_profit", "time_scope": "2024_annual"},
                needs=["structured_data_query"],
                constraints={"preferred_output": "brief_answer"},
            )
        )

        self.assertEqual(plan.intent, Intent.METRIC_LOOKUP.value)
        self.assertEqual(
            plan.stages,
            [
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ],
        )

    def test_planner_falls_back_when_llm_plan_is_invalid(self) -> None:
        planner = PlannerService(llm_client=FakeLlmClient([{"intent": "bad"}]))

        plan = planner.build_plan(
            RouterResult(
                intent=Intent.METRIC_LOOKUP.value,
                follow_up_type=FollowUpType.NONE.value,
                confidence="high",
                entities={"company": "宁德时代", "metric": "net_profit", "time_scope": "2024_annual"},
                needs=["structured_data_query"],
                constraints={"preferred_output": "brief_answer"},
            )
        )

        self.assertEqual(plan.intent, Intent.METRIC_LOOKUP.value)
        self.assertEqual(
            plan.stages,
            [
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ],
        )

    def test_planner_falls_back_when_llm_plan_changes_stage_shape(self) -> None:
        llm_payload = {
            "plan_id": "plan_from_llm",
            "intent": Intent.EVENT_IMPACT_ANALYSIS.value,
            "stages": [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
            "stage_constraints": {
                StageName.COLLECT_EVENT_CONTEXT.value: {
                    "time_hint": "recent",
                    "retrieval_budget": 2,
                },
                StageName.RETRIEVE_EVIDENCE.value: {"retrieval_budget": 2},
                StageName.SYNTHESIZE_REPORT.value: {"preferred_output": "report"},
            },
            "response_mode": ResponseMode.REPORT.value,
        }
        planner = PlannerService(llm_client=FakeLlmClient([llm_payload]))

        plan = planner.build_plan(
            RouterResult(
                intent=Intent.EVENT_IMPACT_ANALYSIS.value,
                follow_up_type=FollowUpType.NONE.value,
                confidence="high",
                entities={
                    "event": "red sea disruption",
                    "themes": ["shipping"],
                    "time_scope": "recent",
                },
                needs=["news_search", "concept_mapping", "rag_retrieval"],
                constraints={"time_hint": "recent", "preferred_output": "report"},
            )
        )

        self.assertEqual(plan.intent, Intent.EVENT_IMPACT_ANALYSIS.value)
        self.assertEqual(
            plan.stages,
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
        )

    def test_planner_accepts_safe_llm_constraints_when_stage_shape_matches(self) -> None:
        llm_payload = {
            "plan_id": "plan_from_llm",
            "intent": Intent.EVENT_IMPACT_ANALYSIS.value,
            "stages": [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
            "stage_constraints": {
                StageName.COLLECT_EVENT_CONTEXT.value: {
                    "time_hint": "recent",
                    "retrieval_budget": 2,
                },
                StageName.ANALYZE_TARGETS.value: {
                    "target_scope": ["shipping", "ports"],
                },
                StageName.RETRIEVE_EVIDENCE.value: {"retrieval_budget": 2},
                StageName.SYNTHESIZE_REPORT.value: {"preferred_output": "report"},
            },
            "response_mode": ResponseMode.REPORT.value,
        }
        planner = PlannerService(llm_client=FakeLlmClient([llm_payload]))

        plan = planner.build_plan(
            RouterResult(
                intent=Intent.EVENT_IMPACT_ANALYSIS.value,
                follow_up_type=FollowUpType.NONE.value,
                confidence="high",
                entities={
                    "event": "red sea disruption",
                    "themes": ["shipping"],
                    "time_scope": "recent",
                },
                needs=["news_search", "concept_mapping", "rag_retrieval"],
                constraints={"time_hint": "recent", "preferred_output": "report"},
            )
        )

        self.assertEqual(plan.plan_id, "plan_from_llm")
        self.assertEqual(
            plan.stage_constraints["collect_event_context"]["retrieval_budget"],
            2,
        )
        self.assertEqual(
            plan.stage_constraints["analyze_targets"]["target_scope"],
            ["shipping", "ports"],
        )

    def test_planner_falls_back_when_llm_plan_skips_required_metric_stage(self) -> None:
        llm_payload = {
            "plan_id": "plan_from_llm",
            "intent": Intent.METRIC_LOOKUP.value,
            "stages": [StageName.SYNTHESIZE_BRIEF_ANSWER.value],
            "stage_constraints": {
                StageName.SYNTHESIZE_BRIEF_ANSWER.value: {
                    "preferred_output": "brief_answer",
                }
            },
            "response_mode": ResponseMode.BRIEF_ANSWER.value,
        }
        planner = PlannerService(llm_client=FakeLlmClient([llm_payload]))

        plan = planner.build_plan(
            RouterResult(
                intent=Intent.METRIC_LOOKUP.value,
                follow_up_type=FollowUpType.NONE.value,
                confidence="high",
                entities={
                    "company": "瀹佸痉鏃朵唬",
                    "metric": "net_profit",
                    "time_scope": "2024_annual",
                },
                needs=["structured_data_query"],
                constraints={"preferred_output": "brief_answer"},
            )
        )

        self.assertEqual(plan.intent, Intent.METRIC_LOOKUP.value)
        self.assertEqual(
            plan.stages,
            [
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ],
        )


class FakeLlmClient:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)

    def complete_json(self, *, prompt_name: str, variables: dict[str, object]) -> dict:
        return self._responses.pop(0)


class RaisingLlmClient:
    def complete_json(self, *, prompt_name: str, variables: dict[str, object]) -> dict:
        raise RuntimeError("llm unavailable")


if __name__ == "__main__":
    unittest.main()
