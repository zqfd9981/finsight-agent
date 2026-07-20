from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from shared.contracts.router_result import RouterResult
from finsight_agent.control_plane.router.schema import router_result_from_payload


class RouterResultContractTest(unittest.TestCase):
    def test_defaults_are_empty(self) -> None:
        rr = RouterResult()
        self.assertEqual(rr.filters, [])
        self.assertIsNone(rr.ranking)

    def test_keyword_construction_accepts_constraints(self) -> None:
        rr = RouterResult(
            intent="metric_lookup",
            filters=[{"op": ">", "value": 1000, "unit": "亿元"}],
            ranking={"limit": 1, "desc": True},
        )
        self.assertEqual(len(rr.filters), 1)
        self.assertEqual(rr.ranking["limit"], 1)

    def test_from_payload_populates_constraints(self) -> None:
        payload = {
            "intent": "metric_lookup",
            "follow_up_type": "none",
            "confidence": "high",
            "entities": {
                "company": {"raw": "宁德时代", "standard_name": "宁德时代", "stock_code": "300750"},
                "metric": {"raw": "净利润", "standard_name": "net_profit", "metric_type": "direct"},
                "time_scope": {"raw": "2024年", "period_end": "2024-12-31", "fiscal_year": 2024},
            },
            "needs": ["structured_data_query"],
            "constraints": {"preferred_output": "brief_answer"},
            "filters": [{"op": ">", "value": 1000, "unit": "亿元"}],
            "ranking": {"limit": 1, "desc": True},
        }
        rr = router_result_from_payload(payload)
        self.assertEqual(len(rr.filters), 1)
        self.assertEqual(rr.filters[0]["op"], ">")
        self.assertEqual(rr.ranking["limit"], 1)

    def test_from_payload_missing_constraints_defaults(self) -> None:
        payload = {
            "intent": "metric_lookup",
            "follow_up_type": "none",
            "confidence": "high",
            "entities": {},
            "needs": [],
            "constraints": {},
        }
        rr = router_result_from_payload(payload)
        self.assertEqual(rr.filters, [])
        self.assertIsNone(rr.ranking)

    def test_from_payload_wrong_types_coerced(self) -> None:
        # filters 不是列表 / ranking 不是对象 → 安全降级为空
        payload = {
            "intent": "metric_lookup",
            "follow_up_type": "none",
            "confidence": "high",
            "entities": {},
            "needs": [],
            "constraints": {},
            "filters": "should-be-list",
            "ranking": [1, 2, 3],
        }
        rr = router_result_from_payload(payload)
        self.assertEqual(rr.filters, [])
        self.assertIsNone(rr.ranking)


if __name__ == "__main__":
    unittest.main()
