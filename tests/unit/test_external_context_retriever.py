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
            query="Who benefits from the Red Sea disruption?",
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"event": "Red Sea disruption"},
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
            title="Event background",
            source="bocha",
            publish_date="2026-07-02",
            url="https://example.com/a",
            snippet="Route disruption intensified.",
            company_names=[],
            company_codes=[],
            themes=["shipping"],
        )
        result = ExternalContextResult(
            items=[item],
            summary_hint="Event context collected.",
            supporting_points=["Detours increased."],
            evidence_refs=["bocha:item_001"],
            candidate_hints=["shipping"],
            source_status={"bocha_used": True},
        )
        plan = ContextRetrievalPlan(
            mode="event_primary",
            steps=[{"source": "event_search", "budget": 1}],
            allow_local_rag=False,
        )

        self.assertEqual(result.items[0].source, "bocha")
        self.assertEqual(plan.mode, "event_primary")
        self.assertFalse(plan.allow_local_rag)


class _StubEventProvider:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = 0

    def search_event_context(self, **kwargs):
        del kwargs
        self.calls += 1
        return self.result


class _StubDisclosureProvider:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = 0

    def search(self, **kwargs):
        del kwargs
        self.calls += 1
        return self.result


class _StubPlanner:
    def build_plan(self, *, strategy_payload, router_payload):
        del router_payload
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ContextRetrievalPlan,
        )

        strategy = strategy_payload.get("strategy", "event_primary")
        if strategy == "dual_primary":
            steps = [
                {"source": "event_search", "budget": 1},
                {"source": "disclosure_search", "budget": 1},
            ]
        elif strategy == "disclosure_primary":
            steps = [{"source": "disclosure_search", "budget": 1}]
        else:
            steps = [{"source": "event_search", "budget": 1}]

        return ContextRetrievalPlan(
            mode=strategy,
            steps=steps,
            allow_local_rag=False,
        )


class DualSourceExternalContextRetrieverTest(unittest.TestCase):
    def test_event_primary_retrieve_event_context_uses_event_source_only(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ExternalContextResult,
        )
        from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
            DualSourceExternalContextRetriever,
        )

        event_provider = _StubEventProvider(
            ExternalContextResult(
                summary_hint="Event background",
                evidence_refs=["bocha:1"],
                supporting_points=["Event point"],
            )
        )
        disclosure_provider = _StubDisclosureProvider(
            ExternalContextResult(
                summary_hint="Disclosure background",
                evidence_refs=["cninfo:1"],
                supporting_points=["Disclosure point"],
            )
        )

        retriever = DualSourceExternalContextRetriever(
            planner=_StubPlanner(),
            event_search_provider=event_provider,
            disclosure_search_provider=disclosure_provider,
        )

        result = retriever.retrieve_event_context(
            query="What happened in the Red Sea disruption?",
            event="Red Sea disruption",
            themes=["shipping"],
            time_scope="recent",
            limit=3,
            strategy="event_primary",
        )

        self.assertEqual(event_provider.calls, 1)
        self.assertEqual(disclosure_provider.calls, 0)
        self.assertEqual(result["summary_hint"], "Event background")
        self.assertEqual(result["evidence_refs"], ["bocha:1"])

    def test_disclosure_primary_retrieve_event_context_uses_disclosure_source_only(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ExternalContextResult,
        )
        from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
            DualSourceExternalContextRetriever,
        )

        event_provider = _StubEventProvider(
            ExternalContextResult(
                summary_hint="Event background",
                evidence_refs=["bocha:1"],
            )
        )
        disclosure_provider = _StubDisclosureProvider(
            ExternalContextResult(
                summary_hint="Disclosure background",
                evidence_refs=["cninfo:1"],
                supporting_points=["Disclosure point"],
            )
        )

        retriever = DualSourceExternalContextRetriever(
            planner=_StubPlanner(),
            event_search_provider=event_provider,
            disclosure_search_provider=disclosure_provider,
        )

        result = retriever.retrieve_event_context(
            query="What does CATL's expansion disclosure imply?",
            event="CATL expansion disclosure",
            themes=["battery"],
            time_scope="recent",
            limit=3,
            strategy="disclosure_primary",
        )

        self.assertEqual(event_provider.calls, 0)
        self.assertEqual(disclosure_provider.calls, 1)
        self.assertEqual(result["summary_hint"], "Disclosure background")
        self.assertEqual(result["evidence_refs"], ["cninfo:1"])

    def test_retrieve_event_context_merges_planned_sources(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ExternalContextResult,
        )
        from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
            DualSourceExternalContextRetriever,
        )

        retriever = DualSourceExternalContextRetriever(
            planner=_StubPlanner(),
            event_search_provider=_StubEventProvider(
                ExternalContextResult(
                    summary_hint="Event background",
                    evidence_refs=["bocha:1"],
                    supporting_points=["Event point"],
                )
            ),
            disclosure_search_provider=_StubDisclosureProvider(
                ExternalContextResult(
                    summary_hint="Disclosure background",
                    evidence_refs=["cninfo:1"],
                    supporting_points=["Disclosure point"],
                    candidate_hints=["COSCO"],
                )
            ),
        )

        result = retriever.retrieve_event_context(
            query="Who benefits from the Red Sea disruption?",
            event="Red Sea disruption",
            themes=["shipping"],
            time_scope="recent",
            limit=3,
            strategy="dual_primary",
        )

        self.assertEqual(result["source_status"]["mode"], "dual_primary")
        self.assertEqual(result["source_status"]["allow_local_rag"], False)
        self.assertEqual(result["evidence_refs"], ["bocha:1", "cninfo:1"])
        self.assertEqual(result["candidate_hints"], ["COSCO"])
        self.assertIn("Event background", result["summary_hint"])
        self.assertIn("Disclosure background", result["summary_hint"])

    def test_discover_candidates_uses_disclosure_provider_query(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ExternalContextResult,
        )
        from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
            DualSourceExternalContextRetriever,
        )

        retriever = DualSourceExternalContextRetriever(
            planner=_StubPlanner(),
            event_search_provider=_StubEventProvider(ExternalContextResult()),
            disclosure_search_provider=_StubDisclosureProvider(
                ExternalContextResult(
                    candidate_hints=["COSCO", "China Merchants"],
                    evidence_refs=["cninfo:2"],
                    source_status={"cninfo_used": True},
                )
            ),
        )

        result = retriever.discover_candidates(
            query="Who benefits from the Red Sea disruption?",
            event_context={"event": "Red Sea disruption", "themes": ["shipping"]},
            limit=1,
        )

        self.assertEqual(result["candidates"], ["COSCO", "China Merchants"])
        self.assertEqual(result["evidence_refs"], ["cninfo:2"])


if __name__ == "__main__":
    unittest.main()
