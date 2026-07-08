from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class ContextRetrievalPlannerTest(unittest.TestCase):
    def test_event_primary_plan_uses_event_search_only(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_planner import (
            ContextRetrievalPlanner,
        )

        planner = ContextRetrievalPlanner()

        plan = planner.build_plan(
            strategy_payload={"strategy": "event_primary", "confidence": "medium"},
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"event": "红海局势升级", "themes": ["航运"]},
            },
        )

        self.assertEqual(plan.mode, "event_primary")
        self.assertEqual(
            [step["source"] for step in plan.steps],
            ["event_search"],
        )
        self.assertFalse(any("when" in step for step in plan.steps))
        self.assertFalse(plan.allow_local_rag)

    def test_disclosure_primary_plan_uses_disclosure_search_only(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_planner import (
            ContextRetrievalPlanner,
        )

        planner = ContextRetrievalPlanner()

        plan = planner.build_plan(
            strategy_payload={"strategy": "disclosure_primary", "confidence": "medium"},
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"event": "宁德时代扩产公告", "themes": ["锂电"]},
            },
        )

        self.assertEqual(plan.mode, "disclosure_primary")
        self.assertEqual(
            [step["source"] for step in plan.steps],
            ["disclosure_search"],
        )
        self.assertFalse(any("when" in step for step in plan.steps))
        self.assertFalse(plan.allow_local_rag)

    def test_dual_primary_plan_uses_two_primary_sources_without_default_rag(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_planner import (
            ContextRetrievalPlanner,
        )

        planner = ContextRetrievalPlanner()

        plan = planner.build_plan(
            strategy_payload={"strategy": "dual_primary", "confidence": "high"},
            router_payload={"intent": "event_impact_analysis", "entities": {}},
        )

        self.assertEqual(plan.mode, "dual_primary")
        self.assertEqual(
            [step["source"] for step in plan.steps],
            ["event_search", "disclosure_search"],
        )
        self.assertFalse(plan.allow_local_rag)


if __name__ == "__main__":
    unittest.main()
