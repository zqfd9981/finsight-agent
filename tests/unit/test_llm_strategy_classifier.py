"""LlmRetrievalStrategyClassifier 单元测试。

用 FakeLlmClient 替代真实网络调用，验证：
- LLM 返回合法策略被正确解析
- LLM 返回非法策略 / 抛异常 → 回退 fallback（Stub）
- 安全网：entities.company 存在 + event_impact 意图 + LLM 判 event_primary → 强制 dual_primary
- 公司名抽取兼容 dict / str / None
- 提示词文件可加载且含关键规则
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class _FakeLlmClient:
    """替代真实 LlmClient，返回预设 JSON 或抛异常。"""

    def __init__(self, *, payload: dict | None = None, raise_error: Exception | None = None) -> None:
        self._payload = payload or {}
        self._raise_error = raise_error
        self.last_variables: dict | None = None
        self.last_prompt_name: str | None = None

    def complete_json(self, *, prompt_name: str, variables: dict) -> dict:
        self.last_prompt_name = prompt_name
        self.last_variables = variables
        if self._raise_error is not None:
            raise self._raise_error
        return self._payload


class LlmStrategyClassifierTest(unittest.TestCase):
    def _make_classifier(self, *, payload=None, raise_error=None, fallback=None):
        from finsight_agent.control_plane.orchestrator.llm_strategy_classifier import (
            LlmRetrievalStrategyClassifier,
        )
        from finsight_agent.control_plane.orchestrator.retrieval_strategy_classifier import (
            StubRetrievalStrategyClassifier,
        )

        fake_llm = _FakeLlmClient(payload=payload, raise_error=raise_error)
        clf = LlmRetrievalStrategyClassifier(
            llm_client=fake_llm,
            fallback=fallback or StubRetrievalStrategyClassifier(),
            system_prompt="[test system prompt]",
        )
        return clf, fake_llm

    def test_llm_returns_dual_for_company_event(self) -> None:
        clf, fake_llm = self._make_classifier(
            payload={
                "strategy": "dual_primary",
                "confidence": "high",
                "reason": "company 隆基绿能 + 红海事件",
            }
        )
        payload = clf.classify(
            query="红海局势会对隆基绿能产生什么影响",
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"company": {"standard_name": "隆基绿能", "stock_code": "601012"}},
            },
            session_topic="",
        )
        self.assertEqual(payload["strategy"], "dual_primary")
        self.assertEqual(payload["confidence"], "high")
        # 验证 entities 确实被传给 LLM
        self.assertEqual(fake_llm.last_prompt_name, "strategy")
        self.assertEqual(
            fake_llm.last_variables["entities"]["company"]["standard_name"], "隆基绿能"
        )

    def test_invalid_strategy_falls_back_to_stub(self) -> None:
        clf, _ = self._make_classifier(payload={"strategy": "not_a_real_strategy"})
        payload = clf.classify(
            query="x",
            router_payload={"intent": "event_impact_analysis"},
            session_topic="",
        )
        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["reason"], "stub_fallback")

    def test_llm_exception_falls_back_to_stub(self) -> None:
        clf, _ = self._make_classifier(raise_error=RuntimeError("simulated llm down"))
        payload = clf.classify(
            query="x",
            router_payload={"intent": "event_impact_analysis"},
            session_topic="",
        )
        self.assertEqual(payload["strategy"], "event_primary")
        self.assertEqual(payload["reason"], "stub_fallback")

    def test_safety_net_forces_dual_when_company_event_and_llm_says_event(self) -> None:
        """回归防护：LLM 误判 event_primary，但实体已抽出具体公司 + 事件影响意图。

        对应真实失败 case：「红海局势会对隆基绿能产生什么影响」。
        """
        clf, _ = self._make_classifier(
            payload={
                "strategy": "event_primary",
                "confidence": "low",
                "reason": "llm mistakenly chose event",
            }
        )
        payload = clf.classify(
            query="红海局势会对隆基绿能产生什么影响",
            router_payload={
                "intent": "event_impact_analysis",
                "entities": {"company": {"standard_name": "隆基绿能", "stock_code": "601012"}},
            },
            session_topic="",
        )
        self.assertEqual(payload["strategy"], "dual_primary")
        self.assertIn("entity_override", payload["reason"])

    def test_safety_net_does_not_fire_without_company(self) -> None:
        """纯板块宏观问题：LLM 判 event_primary，无公司实体 → 不触发安全网。"""
        clf, _ = self._make_classifier(
            payload={"strategy": "event_primary", "confidence": "high", "reason": "纯板块"}
        )
        payload = clf.classify(
            query="红海局势最近怎么样了",
            router_payload={"intent": "event_impact_analysis", "entities": {}},
            session_topic="",
        )
        self.assertEqual(payload["strategy"], "event_primary")

    def test_extract_company_name_variants(self) -> None:
        from finsight_agent.control_plane.orchestrator.llm_strategy_classifier import (
            _extract_company_name,
        )

        self.assertEqual(
            _extract_company_name({"company": {"standard_name": "隆基绿能", "raw": "隆基"}}),
            "隆基绿能",
        )
        self.assertEqual(_extract_company_name({"company": "宁德时代"}), "宁德时代")
        self.assertIsNone(_extract_company_name({"company": None}))
        self.assertIsNone(_extract_company_name({}))
        self.assertIsNone(_extract_company_name("not a mapping"))


class StrategyPromptTest(unittest.TestCase):
    def test_prompt_file_loads_with_key_rules(self) -> None:
        from finsight_agent.infra.llm.prompt_registry import get_prompt

        prompt = get_prompt("strategy.system").text
        self.assertIn("dual_primary", prompt)
        self.assertIn("event_primary", prompt)
        self.assertIn("disclosure_primary", prompt)
        self.assertIn("决策铁律", prompt)
        self.assertIn("entities.company", prompt)


if __name__ == "__main__":
    unittest.main()
