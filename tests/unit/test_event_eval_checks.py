from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.evaluation.event_eval.checks import run_event_eval_checks
from finsight_agent.evaluation.event_eval.models import EventEvalCase, ReplayResult


class EventEvalChecksTest(unittest.TestCase):
    def test_checks_fail_when_strategy_mismatches(self) -> None:
        case = EventEvalCase(
            case_id="dual_001",
            query="红海局势升级利好哪些A股航运股？",
            expected_intent="event_impact_analysis",
            expected_strategy="dual_primary",
            allow_degraded=True,
            min_target_count=1,
            expected_target_keywords=["航运"],
        )
        result = ReplayResult(
            case_id="dual_001",
            query=case.query,
            actual_intent="event_impact_analysis",
            actual_strategy="event_primary",
            response_type="success",
            degraded=False,
            target_count=1,
            evidence_ref_count=2,
            summary="事件背景已经建立。",
            target_keywords=["航运"],
        )

        checks = run_event_eval_checks(case, result)

        strategy_check = next(item for item in checks if item.check_name == "strategy_match")
        self.assertEqual(strategy_check.status, "fail")

    def test_checks_warn_when_degraded_is_allowed(self) -> None:
        case = EventEvalCase(
            case_id="event_001",
            query="红海局势最近怎么了？",
            expected_intent="event_impact_analysis",
            expected_strategy="event_primary",
            allow_degraded=True,
            min_target_count=0,
        )
        result = ReplayResult(
            case_id="event_001",
            query=case.query,
            actual_intent="event_impact_analysis",
            actual_strategy="event_primary",
            response_type="degraded",
            degraded=True,
            target_count=0,
            evidence_ref_count=1,
            summary="已拿到有限事件背景。",
        )

        checks = run_event_eval_checks(case, result)

        degraded_check = next(item for item in checks if item.check_name == "degraded_policy")
        self.assertEqual(degraded_check.status, "warn")


if __name__ == "__main__":
    unittest.main()
