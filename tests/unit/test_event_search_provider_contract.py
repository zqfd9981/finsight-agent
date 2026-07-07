from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class EventSearchProviderProtocolContractTest(unittest.TestCase):
    def test_protocol_can_be_imported_and_exposes_search_event_context(self) -> None:
        from finsight_agent.control_plane.orchestrator.event_search_provider import (
            EventSearchProvider,
        )

        # Protocol 本身只要求属性/方法存在；具体实现由后续 task 给出
        self.assertTrue(hasattr(EventSearchProvider, "search_event_context"))

    def test_protocol_signature_matches_existing_call_site(self) -> None:
        """验证 Protocol 方法签名与 dual_source_context_retriever.py:126 调用点一致。"""
        import inspect

        from finsight_agent.control_plane.orchestrator.event_search_provider import (
            EventSearchProvider,
        )

        sig = inspect.signature(EventSearchProvider.search_event_context)
        params = list(sig.parameters.keys())
        # 调用方传的关键字：query, event, themes, time_scope, limit
        for required in ("query", "event", "themes", "time_scope", "limit"):
            self.assertIn(required, params, f"missing param: {required}")


if __name__ == "__main__":
    unittest.main()