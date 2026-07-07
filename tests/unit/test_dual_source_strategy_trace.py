"""DualSourceExternalContextRetriever trace 透传测试。"""

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


class _StubClassifier:
    def __init__(self, payload):
        self._payload = payload

    def classify(self, *, query, router_payload, session_topic):
        del query, router_payload, session_topic
        return self._payload


class DualSourceStrategyTraceTest(unittest.TestCase):
    def _build_planner(self):
        def build_plan(*, strategy_payload, router_payload):
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

        return type(
            "_StubPlanner",
            (),
            {"build_plan": staticmethod(build_plan)},
        )()

    def test_source_status_includes_trained_metadata(self) -> None:
        classifier = _StubClassifier(
            {
                "strategy": "dual_primary",
                "confidence": "high",
                "reason": "structbert:margin=0.500;top1=dual_primary;top2=event_primary",
            }
        )
        planner = self._build_planner()
        event_provider = _StubEventProvider(
            ExternalContextResult(summary_hint="事件背景", evidence_refs=["bocha:1"])
        )
        disclosure_provider = _StubDisclosureProvider(
            ExternalContextResult(
                candidate_hints=["中远海能"], evidence_refs=["cninfo:1"]
            )
        )

        retriever = DualSourceExternalContextRetriever(
            classifier=classifier,
            planner=planner,
            event_search_provider=event_provider,
            disclosure_search_provider=disclosure_provider,
        )

        result = retriever.retrieve_event_context(
            query="红海局势升级利好哪些A股航运股？",
            event="红海局势升级",
            themes=["航运"],
            time_scope="recent",
            limit=3,
        )
        status = result["source_status"]
        self.assertEqual(status["strategy_confidence"], "high")
        self.assertIn("structbert:margin=0.5", status["strategy_reason"])
        self.assertEqual(status["strategy_source"], "trained")
        self.assertEqual(status["mode"], "dual_primary")

    def test_source_status_marks_stub_fallback(self) -> None:
        """stub_fallback 路径下 strategy_source 必须是 ``stub_fallback``。"""
        classifier = _StubClassifier(
            {"strategy": "event_primary", "confidence": "low", "reason": "stub_fallback"}
        )
        planner = self._build_planner()
        event_provider = _StubEventProvider(
            ExternalContextResult(summary_hint="事件背景", evidence_refs=["bocha:1"])
        )
        disclosure_provider = _StubDisclosureProvider(
            ExternalContextResult(evidence_refs=["cninfo:1"])
        )

        retriever = DualSourceExternalContextRetriever(
            classifier=classifier,
            planner=planner,
            event_search_provider=event_provider,
            disclosure_search_provider=disclosure_provider,
        )
        result = retriever.retrieve_event_context(
            query="x",
            event="e",
            themes=[],
            time_scope="recent",
            limit=1,
        )
        status = result["source_status"]
        self.assertEqual(status["strategy_source"], "stub_fallback")
        self.assertEqual(status["strategy_reason"], "stub_fallback")
        self.assertEqual(status["strategy_confidence"], "low")
