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


if __name__ == "__main__":
    unittest.main()
