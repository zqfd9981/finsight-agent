from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

# 让测试同时可以导入后端包和顶层 shared 包。
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


from fastapi.testclient import TestClient  # noqa: E402

from backend.apps.api.analysis_turns import ANALYSIS_TURNS_PATH  # noqa: E402
from backend.apps.api.event_eval import EVENT_CASES_PATH, EVENT_REPLAY_PATH  # noqa: E402


class BackendApiAppTest(unittest.TestCase):
    def test_build_app_registers_three_workbench_routes(self) -> None:
        from backend.apps.api.app_factory import build_app

        app = build_app()
        paths = {route.path for route in app.routes if hasattr(route, "path")}
        self.assertIn(ANALYSIS_TURNS_PATH, paths)
        self.assertIn(EVENT_CASES_PATH, paths)
        self.assertIn(EVENT_REPLAY_PATH, paths)

    def test_post_analysis_turns_returns_envelope(self) -> None:
        from backend.apps.api.app_factory import build_app

        client = TestClient(build_app())
        resp = client.post(
            ANALYSIS_TURNS_PATH,
            json={
                "version": "v1",
                "query": "宁德时代 2024 年净利润是多少？",
                "query_mode": "first_turn",
                "session_id": None,
                "include_trace": False,
                "notes": None,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["version"], "v1")
        self.assertIn("session_id", body)
        self.assertIn("response", body)
        self.assertIn("trace_blocks", body)

    def test_post_analysis_turns_rejects_missing_query(self) -> None:
        from backend.apps.api.app_factory import build_app

        client = TestClient(build_app())
        resp = client.post(
            ANALYSIS_TURNS_PATH,
            json={"version": "v1", "include_trace": False},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertIn("query", resp.text.lower())

    def test_get_event_cases_returns_cases_list(self) -> None:
        from backend.apps.api.app_factory import build_app

        client = TestClient(build_app())
        resp = client.get(EVENT_CASES_PATH)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("cases", body)
        self.assertIsInstance(body["cases"], list)

    def test_post_event_replay_returns_summary_and_records(self) -> None:
        # 后端真实 replay 会触发 GDELT 真实检索（plan R1 / design D6）；
        # TestClient 测试只验证路由形状，replay 函数通过 monkey-patch 替换为假实现。
        from backend.apps.api import event_eval
        from backend.apps.api.app_factory import build_app

        def _fake_replay_event_cases(
            *,
            fixture_path,
            case_ids=None,
            service=None,
            include_trace=True,
        ):
            del fixture_path, service, include_trace
            return [
                {
                    "case": {"case_id": "stub_001", "query": "stub query"},
                    "result": {
                        "case_id": "stub_001",
                        "query": "stub query",
                        "actual_intent": "event_impact_analysis",
                        "actual_strategy": "dual_primary",
                        "response_type": "success",
                        "degraded": False,
                        "target_count": 1,
                        "evidence_ref_count": 1,
                        "summary": "stub summary",
                        "failure_reason": None,
                        "target_keywords": ["stub_target"],
                    },
                    "checks": [
                        {"check_name": "intent_match", "status": "pass", "message": "ok"}
                    ],
                }
            ]

        original_replay = event_eval.replay_event_cases
        event_eval.replay_event_cases = _fake_replay_event_cases
        try:
            client = TestClient(build_app())
            resp = client.post(EVENT_REPLAY_PATH, json={"case_ids": None})
        finally:
            event_eval.replay_event_cases = original_replay

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("summary", body)
        self.assertIn("records", body)
        self.assertIn("total", body["summary"])


if __name__ == "__main__":
    unittest.main()
