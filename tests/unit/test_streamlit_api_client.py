from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from frontend.streamlit_app.api_client import WorkbenchApiClient


class StreamlitApiClientTest(unittest.TestCase):
    def test_parse_response_ignores_unknown_response_fields(self) -> None:
        client = WorkbenchApiClient()

        payload = {
            "version": "v1",
            "session_id": "sess_extra",
            "turn_id": "turn_stub",
            "response": {
                "response_type": "success",
                "session_id": "sess_extra",
                "summary": "ok",
                "answer_markdown": "这是完整回答。",
                "report_blocks": [],
                "unexpected_field": "should be ignored",
            },
            "trace_blocks": [],
            "notes": None,
        }

        envelope = client.parse_response(payload)

        self.assertEqual(envelope.session_id, "sess_extra")
        self.assertEqual(envelope.response.answer_markdown, "这是完整回答。")

    def test_parse_event_cases_returns_view_models(self) -> None:
        client = WorkbenchApiClient()

        payload = {
            "cases": [
                {
                    "case_id": "dual_001",
                    "query": "红海局势升级利好哪些A股航运股？",
                    "expected_intent": "event_impact_analysis",
                    "expected_strategy": "dual_primary",
                    "allow_degraded": True,
                    "min_target_count": 1,
                    "expected_target_keywords": ["中远海能"],
                    "notes": "双主源事件样本",
                }
            ]
        }

        cases = client.parse_event_cases(payload)

        self.assertEqual(cases[0].case_id, "dual_001")
        self.assertEqual(cases[0].expected_strategy, "dual_primary")

    def test_parse_event_replay_returns_summary_and_records(self) -> None:
        client = WorkbenchApiClient()

        payload = {
            "summary": {"total": 1, "pass": 1, "warn": 0, "fail": 0},
            "records": [
                {
                    "case": {
                        "case_id": "dual_001",
                        "query": "红海局势升级利好哪些A股航运股？",
                    },
                    "result": {
                        "case_id": "dual_001",
                        "query": "红海局势升级利好哪些A股航运股？",
                        "actual_intent": "event_impact_analysis",
                        "actual_strategy": "dual_primary",
                        "response_type": "success",
                        "degraded": False,
                        "target_count": 2,
                        "evidence_ref_count": 3,
                        "summary": "中远海能等标的受益于运价弹性。",
                        "failure_reason": None,
                        "target_keywords": ["中远海能", "招商轮船"],
                    },
                    "checks": [
                        {
                            "check_name": "intent_match",
                            "status": "pass",
                            "message": "ok",
                        }
                    ],
                }
            ],
        }

        replay = client.parse_event_replay(payload)

        self.assertEqual(replay.summary.total, 1)
        self.assertEqual(replay.records[0].result.actual_strategy, "dual_primary")


class WorkbenchApiClientHttpTest(unittest.TestCase):
    def test_send_request_posts_to_resolved_backend_base_url(self) -> None:
        from unittest.mock import MagicMock, patch

        from shared.contracts.analysis_response_envelope import (
            AnalysisResponseEnvelope,
        )

        fake_response = MagicMock()
        fake_response.ok = True
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "version": "v1",
            "session_id": "sess_x",
            "turn_id": "turn_stub",
            "response": {
                "response_type": "success",
                "session_id": "sess_x",
                "summary": "ok",
                "answer_markdown": "这是完整回答。",
                "report_blocks": [],
            },
            "trace_blocks": [],
            "notes": None,
        }

        client = WorkbenchApiClient(
            backend_base_url="http://10.0.0.5:9000",
            endpoint_path="/api/v1/analysis/turns",
        )

        with patch(
            "frontend.streamlit_app.api_client.requests.post",
            return_value=fake_response,
        ) as patched:
            envelope = client.send_request(query="hello")

        called_url = patched.call_args.args[0]
        self.assertEqual(called_url, "http://10.0.0.5:9000/api/v1/analysis/turns")
        self.assertIsInstance(envelope, AnalysisResponseEnvelope)
        self.assertEqual(envelope.session_id, "sess_x")
        self.assertEqual(envelope.response.answer_markdown, "这是完整回答。")

    def test_send_request_raises_on_non_2xx(self) -> None:
        from unittest.mock import MagicMock, patch

        fake_response = MagicMock()
        fake_response.ok = False
        fake_response.status_code = 500
        fake_response.text = "boom"

        client = WorkbenchApiClient(backend_base_url="http://h:1")

        with patch(
            "frontend.streamlit_app.api_client.requests.post",
            return_value=fake_response,
        ):
            with self.assertRaises(RuntimeError):
                client.send_request(query="hi")

    def test_fetch_event_replay_round_trip(self) -> None:
        from unittest.mock import MagicMock, patch

        from frontend.streamlit_app.state.models import EventReplayRunView

        fake_response = MagicMock()
        fake_response.ok = True
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "summary": {"total": 0, "pass": 0, "warn": 0, "fail": 0},
            "records": [],
        }

        client = WorkbenchApiClient(backend_base_url="http://h:1")

        with patch(
            "frontend.streamlit_app.api_client.requests.post",
            return_value=fake_response,
        ) as patched:
            view = client.fetch_event_replay(case_ids=["stub"])

        called_url = patched.call_args.args[0]
        self.assertEqual(
            called_url, "http://h:1/api/v1/eval/event-replay"
        )
        self.assertIsInstance(view, EventReplayRunView)
        self.assertEqual(view.summary.total, 0)


if __name__ == "__main__":
    unittest.main()
