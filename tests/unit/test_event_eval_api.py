from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from backend.apps.api import event_eval


class EventEvalApiTest(unittest.TestCase):
    def test_build_eval_route_metadata_returns_two_routes(self) -> None:
        routes = event_eval.build_eval_route_metadata()

        self.assertEqual(
            [route["path"] for route in routes],
            ["/api/v1/eval/event-cases", "/api/v1/eval/event-replay"],
        )

    def test_handle_event_cases_returns_fixture_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "cases.jsonl"
            fixture_path.write_text(
                json.dumps(
                    {
                        "case_id": "dual_001",
                        "query": "红海局势升级利好哪些A股航运股？",
                        "expected_intent": "event_impact_analysis",
                        "expected_strategy": "dual_primary",
                        "allow_degraded": True,
                        "min_target_count": 1,
                        "expected_target_keywords": ["中远海能"],
                        "notes": "双主源事件样本",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            original = event_eval.DEFAULT_EVENT_FIXTURE_PATH
            event_eval.DEFAULT_EVENT_FIXTURE_PATH = fixture_path
            try:
                payload = event_eval.handle_event_cases()
            finally:
                event_eval.DEFAULT_EVENT_FIXTURE_PATH = original

        self.assertEqual(len(payload["cases"]), 1)
        self.assertEqual(payload["cases"][0]["case_id"], "dual_001")

    def test_handle_event_replay_runs_selected_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "cases.jsonl"
            fixture_path.write_text(
                json.dumps(
                    {
                        "case_id": "dual_001",
                        "query": "红海局势升级利好哪些A股航运股？",
                        "expected_intent": "event_impact_analysis",
                        "expected_strategy": "dual_primary",
                        "allow_degraded": True,
                        "min_target_count": 1,
                        "expected_target_keywords": ["中远海能"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def _fake_replay_event_cases(
                *,
                fixture_path: Path,
                case_ids=None,
                service=None,
                include_trace=True,
            ):
                del fixture_path, service, include_trace
                self.assertEqual(case_ids, ["dual_001"])
                return [
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
                ]

            original_fixture_path = event_eval.DEFAULT_EVENT_FIXTURE_PATH
            original_replay = event_eval.replay_event_cases
            event_eval.DEFAULT_EVENT_FIXTURE_PATH = fixture_path
            event_eval.replay_event_cases = _fake_replay_event_cases
            try:
                payload = event_eval.handle_event_replay({"case_ids": ["dual_001"]})
            finally:
                event_eval.DEFAULT_EVENT_FIXTURE_PATH = original_fixture_path
                event_eval.replay_event_cases = original_replay

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["pass"], 1)
        self.assertEqual(payload["records"][0]["result"]["actual_strategy"], "dual_primary")


if __name__ == "__main__":
    unittest.main()
