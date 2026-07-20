from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.control_plane.orchestrator.stage_planner import resolve_stages
from finsight_agent.control_plane.router.service import RouterService
from shared.contracts.router_result import RouterResult
from shared.contracts.session_context import SessionContext
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent
from shared.enums.response_mode import ResponseMode
from shared.enums.stage_name import StageName


class FakeRouterLlm:
    """确定性 router LLM 桩：按 query 返回固化 payload，避免测试依赖实时 LLM。

    仅覆盖本文件三个分类测试用到的 query；其余返回通用 metric_lookup payload。
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def complete_json(self, prompt_name: str, variables: dict[str, object]) -> dict[str, object]:
        self.calls.append({"prompt_name": prompt_name, "variables": variables})
        query = str(variables.get("query", ""))
        return _ROUTER_FIXTURE_PAYLOADS.get(query, _METRIC_LOOKUP_PAYLOAD)


_METRIC_LOOKUP_PAYLOAD = {
    "intent": "metric_lookup",
    "follow_up_type": "none",
    "confidence": "high",
    "entities": {
        "company": {"raw": "宁德时代", "standard_name": "宁德时代", "stock_code": "300750"},
        "metric": {"raw": "净利润", "standard_name": "net_profit", "metric_type": "direct"},
        "time_scope": {"raw": "2024年", "period_end": "2024-12-31", "fiscal_year": 2024},
    },
    "needs": ["structured_data_query"],
    "constraints": {"preferred_output": "brief_answer"},
}

_ROUTER_FIXTURE_PAYLOADS = {
    "宁德时代 2024 年净利润是多少？": _METRIC_LOOKUP_PAYLOAD,
    "红海局势升级利好哪些A股航运股？": {
        "intent": "event_impact_analysis",
        "follow_up_type": "none",
        "confidence": "high",
        "entities": {"event": "红海局势升级", "themes": ["航运"], "time_scope": "recent"},
        "needs": ["news_search", "concept_mapping", "rag_retrieval"],
        "constraints": {"time_hint": "recent", "preferred_output": "report"},
    },
    "把中远海能受益逻辑的证据展开一下": {
        "intent": "evidence_lookup",
        "follow_up_type": "drilldown",
        "confidence": "high",
        "entities": {"target": "中远海能", "claim": "把中远海能受益逻辑的证据展开一下"},
        "needs": ["rag_retrieval"],
        "constraints": {"preferred_output": "report", "retrieval_budget": 4},
    },
}


class SemanticRoutingAndPlanningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = RouterService(llm_client=FakeRouterLlm())

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


class StagePlannerTest(unittest.TestCase):
    """覆盖 resolve_stages 的 7 种 (intent, strategy) 映射。"""

    def _make_event_router_result(self) -> RouterResult:
        return RouterResult(
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

    def test_resolve_stages_metric_lookup(self) -> None:
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

        stages, stage_constraints, response_mode = resolve_stages(router_result)

        self.assertEqual(
            stages,
            [
                StageName.QUERY_STRUCTURED_DATA.value,
                StageName.REFLECT_AND_REQUERY.value,
                StageName.SYNTHESIZE_ANSWER.value,
                StageName.VERIFY_ANSWER.value,
            ],
        )
        self.assertEqual(response_mode, ResponseMode.BRIEF_ANSWER.value)
        self.assertEqual(
            stage_constraints[StageName.SYNTHESIZE_ANSWER.value]["response_mode"],
            ResponseMode.BRIEF_ANSWER.value,
        )

    def test_resolve_stages_general_finance_qa(self) -> None:
        router_result = RouterResult(
            intent=Intent.GENERAL_FINANCE_QA.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={},
            needs=[],
            constraints={},
        )

        stages, stage_constraints, response_mode = resolve_stages(router_result)

        self.assertEqual(
            stages,
            [StageName.SYNTHESIZE_ANSWER.value, StageName.VERIFY_ANSWER.value],
        )
        self.assertEqual(response_mode, ResponseMode.DIRECT.value)
        self.assertEqual(
            stage_constraints[StageName.SYNTHESIZE_ANSWER.value]["response_mode"],
            ResponseMode.DIRECT.value,
        )

    def test_resolve_stages_event_impact_event_primary(self) -> None:
        stages, stage_constraints, response_mode = resolve_stages(
            self._make_event_router_result(),
            strategy_payload={
                "strategy": "event_primary",
                "confidence": "high",
                "reason": "test",
            },
        )

        self.assertEqual(
            stages,
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.SYNTHESIZE_ANSWER.value,
                StageName.VERIFY_ANSWER.value,
            ],
        )
        self.assertEqual(response_mode, ResponseMode.EVENT_ANSWER.value)
        self.assertEqual(
            stage_constraints[StageName.COLLECT_EVENT_CONTEXT.value]["strategy"],
            "event_primary",
        )
        self.assertEqual(
            stage_constraints[StageName.SYNTHESIZE_ANSWER.value]["response_mode"],
            ResponseMode.EVENT_ANSWER.value,
        )

    def test_resolve_stages_event_impact_disclosure_primary(self) -> None:
        stages, stage_constraints, response_mode = resolve_stages(
            self._make_event_router_result(),
            strategy_payload={
                "strategy": "disclosure_primary",
                "confidence": "high",
                "reason": "test",
            },
        )

        self.assertEqual(
            stages,
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_ANSWER.value,
                StageName.VERIFY_ANSWER.value,
            ],
        )
        self.assertEqual(response_mode, ResponseMode.REPORT.value)
        self.assertEqual(
            stage_constraints[StageName.COLLECT_EVENT_CONTEXT.value]["strategy"],
            "disclosure_primary",
        )
        self.assertEqual(
            stage_constraints[StageName.SYNTHESIZE_ANSWER.value]["response_mode"],
            ResponseMode.REPORT.value,
        )

    def test_resolve_stages_event_impact_dual_primary(self) -> None:
        stages, stage_constraints, response_mode = resolve_stages(
            self._make_event_router_result(),
            strategy_payload={
                "strategy": "dual_primary",
                "confidence": "high",
                "reason": "test",
            },
        )

        self.assertEqual(
            stages,
            [
                StageName.COLLECT_EVENT_CONTEXT.value,
                StageName.ANALYZE_TARGETS.value,
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_ANSWER.value,
                StageName.VERIFY_ANSWER.value,
            ],
        )
        self.assertEqual(response_mode, ResponseMode.REPORT.value)
        self.assertEqual(
            stage_constraints[StageName.COLLECT_EVENT_CONTEXT.value]["strategy"],
            "dual_primary",
        )
        self.assertEqual(
            stage_constraints[StageName.SYNTHESIZE_ANSWER.value]["response_mode"],
            ResponseMode.REPORT.value,
        )

    def test_resolve_stages_evidence_lookup(self) -> None:
        router_result = RouterResult(
            intent=Intent.EVIDENCE_LOOKUP.value,
            follow_up_type=FollowUpType.DRILLDOWN.value,
            confidence="high",
            entities={"target": "中远海能", "claim": "把证据展开"},
            needs=["rag_retrieval"],
            constraints={"preferred_output": "report", "retrieval_budget": 4},
        )

        stages, stage_constraints, response_mode = resolve_stages(router_result)

        self.assertEqual(
            stages,
            [
                StageName.RETRIEVE_EVIDENCE.value,
                StageName.SYNTHESIZE_ANSWER.value,
                StageName.VERIFY_ANSWER.value,
            ],
        )
        self.assertEqual(response_mode, ResponseMode.REPORT.value)
        self.assertEqual(
            stage_constraints[StageName.SYNTHESIZE_ANSWER.value]["response_mode"],
            ResponseMode.REPORT.value,
        )

    def test_resolve_stages_out_of_scope(self) -> None:
        router_result = RouterResult(
            intent=Intent.OUT_OF_SCOPE.value,
            follow_up_type=FollowUpType.NONE.value,
            confidence="high",
            entities={},
            needs=[],
            constraints={},
        )

        stages, stage_constraints, response_mode = resolve_stages(router_result)

        self.assertEqual(stages, [])
        self.assertEqual(response_mode, ResponseMode.BRIEF_ANSWER.value)
        self.assertNotIn(StageName.SYNTHESIZE_ANSWER.value, stage_constraints)


if __name__ == "__main__":
    unittest.main()
