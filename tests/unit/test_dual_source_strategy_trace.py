from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextResult,
)
from finsight_agent.control_plane.orchestrator.dual_source_context_retriever import (
    DualSourceExternalContextRetriever,
)


class _StubEventProvider:
    def __init__(self, result):
        self._result = result

    def search_event_context(self, **kwargs):
        del kwargs
        return self._result


class _StubDisclosureProvider:
    def __init__(self, result):
        self._result = result

    def search(self, **kwargs):
        del kwargs
        return self._result


class _StubPlanner:
    def build_plan(self, *, strategy_payload, router_payload):
        del router_payload
        mode = strategy_payload.get("strategy", "event_primary")
        if mode == "dual_primary":
            steps = [
                {"source": "event_search", "budget": 1},
                {"source": "disclosure_search", "budget": 1},
            ]
        elif mode == "disclosure_primary":
            steps = [{"source": "disclosure_search", "budget": 1}]
        else:
            steps = [{"source": "event_search", "budget": 1}]

        return type(
            "Plan",
            (),
            {"mode": mode, "steps": steps, "allow_local_rag": False},
        )()


class DualSourceStrategyTraceTest(unittest.TestCase):
    def test_source_status_reflects_upstream_dual_primary_strategy(self) -> None:
        retriever = DualSourceExternalContextRetriever(
            planner=_StubPlanner(),
            event_search_provider=_StubEventProvider(
                ExternalContextResult(summary_hint="Event background", evidence_refs=["bocha:1"])
            ),
            disclosure_search_provider=_StubDisclosureProvider(
                ExternalContextResult(candidate_hints=["COSCO"], evidence_refs=["cninfo:1"])
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
        status = result["source_status"]
        self.assertEqual(status["mode"], "dual_primary")
        self.assertEqual(status["allow_local_rag"], False)

    def test_source_status_reflects_upstream_event_primary_strategy(self) -> None:
        retriever = DualSourceExternalContextRetriever(
            planner=_StubPlanner(),
            event_search_provider=_StubEventProvider(
                ExternalContextResult(summary_hint="Event background", evidence_refs=["bocha:1"])
            ),
            disclosure_search_provider=_StubDisclosureProvider(
                ExternalContextResult(evidence_refs=["cninfo:1"])
            ),
        )
        result = retriever.retrieve_event_context(
            query="What happened in the Red Sea disruption?",
            event="Red Sea disruption",
            themes=[],
            time_scope="recent",
            limit=1,
            strategy="event_primary",
        )
        status = result["source_status"]
        self.assertEqual(status["mode"], "event_primary")
        self.assertEqual(status["allow_local_rag"], False)


if __name__ == "__main__":
    unittest.main()
