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

from finsight_agent.evaluation.event_eval.fixture_loader import load_event_eval_cases
from finsight_agent.evaluation.event_eval.models import ReplayResult


class EventEvalModelsTest(unittest.TestCase):
    def test_load_event_eval_cases_parses_jsonl_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "cases.jsonl"
            fixture_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "case_id": "event_dual_001",
                                "query": "红海局势升级利好哪些A股航运股？",
                                "expected_intent": "event_impact_analysis",
                                "expected_strategy": "dual_primary",
                                "allow_degraded": True,
                                "min_target_count": 1,
                                "expected_target_keywords": ["中远海能"],
                                "notes": "双主源事件样本",
                            },
                            ensure_ascii=False,
                        )
                    ]
                ),
                encoding="utf-8",
            )

            cases = load_event_eval_cases(fixture_path)

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].case_id, "event_dual_001")
        self.assertEqual(cases[0].expected_strategy, "dual_primary")

    def test_replay_result_serializes_core_fields(self) -> None:
        result = ReplayResult(
            case_id="event_dual_001",
            query="红海局势升级利好哪些A股航运股？",
            actual_intent="event_impact_analysis",
            actual_strategy="dual_primary",
            response_type="success",
            degraded=False,
            target_count=2,
            evidence_ref_count=3,
            summary="中远海能等标的受益于运价弹性。",
            failure_reason=None,
            target_keywords=["中远海能", "招商轮船"],
        )

        payload = result.to_dict()

        self.assertEqual(payload["actual_strategy"], "dual_primary")
        self.assertEqual(payload["target_count"], 2)

    def test_default_fixture_covers_three_strategies(self) -> None:
        fixture_path = (
            REPO_ROOT
            / "backend"
            / "src"
            / "finsight_agent"
            / "evaluation"
            / "event_eval"
            / "fixtures"
            / "event_cases_v1.jsonl"
        )

        cases = load_event_eval_cases(fixture_path)
        strategies = {case.expected_strategy for case in cases}

        self.assertIn("event_primary", strategies)
        self.assertIn("disclosure_primary", strategies)
        self.assertIn("dual_primary", strategies)
        self.assertGreaterEqual(len(cases), 6)


if __name__ == "__main__":
    unittest.main()
