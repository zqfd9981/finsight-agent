from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class RetrievalStrategyClassifierContractTest(unittest.TestCase):
    def test_strategy_labels_and_default_are_stable(self) -> None:
        from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
            DEFAULT_RETRIEVAL_STRATEGY,
            RETRIEVAL_STRATEGIES,
            StubRetrievalStrategyClassifier,
        )

        self.assertEqual(
            RETRIEVAL_STRATEGIES,
            ("event_primary", "disclosure_primary", "dual_primary"),
        )
        self.assertEqual(DEFAULT_RETRIEVAL_STRATEGY, "event_primary")

        classifier = StubRetrievalStrategyClassifier()
        payload = classifier.classify(
            query="红海局势升级利好哪些A股航运股？",
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"event": "红海局势升级"},
            },
            session_topic="",
        )

        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(payload["reason"], "stub_fallback")


class ContextRetrievalModelsTest(unittest.TestCase):
    def test_context_result_and_plan_hold_structured_fields(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ContextRetrievalPlan,
            ExternalContextItem,
            ExternalContextResult,
        )

        item = ExternalContextItem(
            title="红海局势升级影响航线",
            source="gdelt",
            publish_date="2026-07-02",
            url="https://example.com/a",
            snippet="航线扰动加剧。",
            company_names=[],
            company_codes=[],
            themes=["航运"],
        )
        result = ExternalContextResult(
            items=[item],
            summary_hint="事件背景已提炼",
            supporting_points=["航线扰动加剧"],
            evidence_refs=["gdelt:item_001"],
            candidate_hints=["航运"],
            source_status={"gdelt_used": True},
        )
        plan = ContextRetrievalPlan(
            mode="event_primary",
            steps=[{"source": "event_search", "budget": 1}],
            allow_local_rag=False,
        )

        self.assertEqual(result.items[0].source, "gdelt")
        self.assertEqual(plan.mode, "event_primary")
        self.assertFalse(plan.allow_local_rag)


class _StubEventProvider:
    def __init__(self, result) -> None:
        self.result = result

    def search_event_context(self, **kwargs):
        del kwargs
        return self.result


class _StubDisclosureProvider:
    def __init__(self, result) -> None:
        self.result = result

    def search(self, **kwargs):
        del kwargs
        return self.result


class _StubPlanner:
    def build_plan(self, *, strategy_payload, router_payload):
        del strategy_payload, router_payload
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ContextRetrievalPlan,
        )

        return ContextRetrievalPlan(
            mode="dual_primary",
            steps=[
                {"source": "event_search", "budget": 1},
                {"source": "disclosure_search", "budget": 1},
            ],
            allow_local_rag=False,
        )


class _StubClassifier:
    def classify(self, *, query, router_payload, session_topic):
        del query, router_payload, session_topic
        return {"strategy": "dual_primary", "confidence": "high", "reason": "test"}


class DualSourceExternalContextRetrieverTest(unittest.TestCase):
    def test_retrieve_event_context_merges_planned_sources(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ExternalContextResult,
        )
        from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
            DualSourceExternalContextRetriever,
        )

        retriever = DualSourceExternalContextRetriever(
            classifier=_StubClassifier(),
            planner=_StubPlanner(),
            event_search_provider=_StubEventProvider(
                ExternalContextResult(
                    summary_hint="事件背景",
                    evidence_refs=["gdelt:1"],
                    supporting_points=["事件点1"],
                )
            ),
            disclosure_search_provider=_StubDisclosureProvider(
                ExternalContextResult(
                    summary_hint="公告背景",
                    evidence_refs=["cninfo:1"],
                    supporting_points=["公告点1"],
                    candidate_hints=["中远海能"],
                )
            ),
        )

        result = retriever.retrieve_event_context(
            query="红海局势升级利好哪些A股航运股？",
            event="红海局势升级",
            themes=["航运"],
            time_scope="recent",
            limit=3,
        )

        self.assertEqual(result["source_status"]["mode"], "dual_primary")
        self.assertEqual(result["evidence_refs"], ["gdelt:1", "cninfo:1"])
        self.assertEqual(result["candidate_hints"], ["中远海能"])

    def test_discover_candidates_uses_disclosure_provider_query(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ExternalContextResult,
        )
        from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
            DualSourceExternalContextRetriever,
        )

        retriever = DualSourceExternalContextRetriever(
            classifier=_StubClassifier(),
            planner=_StubPlanner(),
            event_search_provider=_StubEventProvider(ExternalContextResult()),
            disclosure_search_provider=_StubDisclosureProvider(
                ExternalContextResult(
                    candidate_hints=["中远海能", "招商轮船"],
                    evidence_refs=["cninfo:2"],
                    source_status={"cninfo_used": True},
                )
            ),
        )

        result = retriever.discover_candidates(
            query="红海局势升级利好哪些A股航运股？",
            event_context={"event": "红海局势升级", "themes": ["航运"]},
            limit=1,
        )

        self.assertEqual(result["candidates"], ["中远海能", "招商轮船"])
        self.assertEqual(result["evidence_refs"], ["cninfo:2"])


if __name__ == "__main__":
    unittest.main()
