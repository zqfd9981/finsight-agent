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
        self.assertIn("company", result.entities)
        self.assertIn("metric", result.entities)
        self.assertIn("time_scope", result.entities)

    def test_router_classifies_event_impact_analysis(self) -> None:
        result = self.router.route(
            query="红海局势升级利好哪些A股航运股？",
            session_context=None,
        )

        self.assertEqual(result.intent, Intent.EVENT_IMPACT_ANALYSIS.value)
        self.assertIn("event", result.entities)
        self.assertIn("themes", result.entities)
        self.assertTrue(result.entities["themes"])

    def test_router_classifies_evidence_lookup_as_drilldown(self) -> None:
        session_context = SessionContext(
            session_id="sess_001",
            active_topic="红海航运扰动对A股航运链的影响",
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
        self.assertIn("claim", result.entities)

    def test_planner_builds_metric_lookup_fast_path(self) -> None:
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

        plan = self.planner.build_plan(router_result)

        self.assertEqual(
            plan.stages,
            [
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.SYNTHESIZE_BRIEF_ANSWER.value,
            ],
        )
        self.assertEqual(plan.response_mode, ResponseMode.BRIEF_ANSWER.value)

    def test_planner_builds_event_primary_path(self) -> None:
        router_result = RouterResult(
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={
                "event": "红海局势升级",
                "themes": ["航运"],
                "time_scope": "recent",
            },
            needs=["news_search", "concept_mapping", "rag_retrieval"],
            constraints={"time_hint": "recent", "preferred_output": "report"},
        )

        plan = self.planner.build_plan(
            router_result,
            strategy_payload={
                "strategy": "event_primary",
                "confidence": "high",
                "reason": "test",
            },
        )

        self.assertEqual(
            plan.stages,
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.SYNTHESIZE_EVENT_ANSWER.value,
            ],
        )
        self.assertEqual(
            plan.stage_constraints["collect_event_context"]["strategy"],
            "event_primary",
        )
        self.assertEqual(plan.response_mode, ResponseMode.BRIEF_ANSWER.value)

    def test_planner_builds_disclosure_primary_path(self) -> None:
        router_result = RouterResult(
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={
                "event": "宁德时代扩产公告",
                "themes": ["电池"],
                "time_scope": "recent",
            },
            needs=["disclosure_search", "rag_retrieval"],
            constraints={"time_hint": "recent", "preferred_output": "report"},
        )

        plan = self.planner.build_plan(
            router_result,
            strategy_payload={
                "strategy": "disclosure_primary",
                "confidence": "high",
                "reason": "test",
            },
        )

        self.assertEqual(
            plan.stages,
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
        )
        self.assertEqual(
            plan.stage_constraints["collect_event_context"]["strategy"],
            "disclosure_primary",
        )
        self.assertEqual(plan.response_mode, ResponseMode.REPORT.value)

    def test_planner_builds_dual_primary_path(self) -> None:
        router_result = RouterResult(
            intent=Intent.EVENT_IMPACT_ANALYSIS.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={
                "event": "红海局势升级",
                "themes": ["航运"],
                "time_scope": "recent",
            },
            needs=["news_search", "concept_mapping", "rag_retrieval"],
            constraints={"time_hint": "recent", "preferred_output": "report"},
        )

        plan = self.planner.build_plan(
            router_result,
            strategy_payload={
                "strategy": "dual_primary",
                "confidence": "high",
                "reason": "test",
            },
        )

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
            plan.stage_constraints["collect_event_context"]["strategy"],
            "dual_primary",
        )
        self.assertEqual(plan.response_mode, ResponseMode.REPORT.value)

    def test_planner_builds_evidence_lookup_short_plan(self) -> None:
        router_result = RouterResult(
            intent=Intent.EVIDENCE_LOOKUP.value,
            follow_up_type=FollowUpType.DRILLDOWN.value,
            confidence="high",
            entities={"target": "中远海能", "claim": "把证据展开"},
            needs=["rag_retrieval"],
            constraints={"preferred_output": "report", "retrieval_budget": 4},
        )

        plan = self.planner.build_plan(router_result)

        self.assertEqual(
            plan.stages,
            [
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
        )
        self.assertEqual(plan.response_mode, ResponseMode.REPORT.value)

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
            ),
            strategy_payload={"strategy": "dual_primary", "confidence": "high", "reason": "test"},
        )

        self.assertEqual(
            plan.stages,
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_REPORT.value,
            ],
        )


class FakeLlmClient:
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)

    def complete_json(self, *, prompt_name: str, variables: dict[str, object]) -> dict:
        del prompt_name, variables
        return self._responses.pop(0)


if __name__ == "__main__":
    unittest.main()
