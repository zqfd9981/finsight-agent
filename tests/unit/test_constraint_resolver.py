from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.constraint_resolver import (
    resolve_constraints,
)


class ConstraintResolverTest(unittest.TestCase):
    # ---- filters ----

    def test_empty_filters_returns_empty(self) -> None:
        filters, ranking, warnings = resolve_constraints(None, None)
        self.assertEqual(filters, [])
        self.assertIsNone(ranking)
        self.assertEqual(warnings, [])

    def test_valid_filter_passthrough(self) -> None:
        filters, _, warnings = resolve_constraints(
            [{"op": ">", "value": 1000, "unit": "亿元"}], None
        )
        self.assertEqual(len(filters), 1)
        self.assertEqual(filters[0]["op"], ">")
        self.assertEqual(filters[0]["value"], 1000.0)
        self.assertEqual(filters[0]["unit"], "亿元")
        self.assertEqual(warnings, [])

    def test_unsupported_op_dropped(self) -> None:
        filters, _, warnings = resolve_constraints(
            [{"op": "LIKE", "value": 100, "unit": "元"}], None
        )
        self.assertEqual(filters, [])
        self.assertTrue(any("LIKE" in w for w in warnings))

    def test_non_numeric_value_dropped(self) -> None:
        # 相对值比较（"比茅台高"）会把公司名当 value → 非数值 → 丢弃，等价于省略约束
        filters, _, warnings = resolve_constraints(
            [{"op": ">", "value": "茅台", "unit": "元"}], None
        )
        self.assertEqual(filters, [])
        self.assertTrue(any("非数值" in w for w in warnings))

    def test_unit_defaults_to_yuan(self) -> None:
        filters, _, _ = resolve_constraints(
            [{"op": ">=", "value": 500}], None
        )
        self.assertEqual(filters[0]["unit"], "元")

    def test_valid_and_invalid_mixed(self) -> None:
        filters, _, warnings = resolve_constraints(
            [
                {"op": ">", "value": 10, "unit": "亿元"},
                "not-a-dict",
                {"op": "?", "value": 1},
            ],
            None,
        )
        self.assertEqual(len(filters), 1)
        self.assertEqual(len(warnings), 2)

    def test_filters_not_a_list(self) -> None:
        filters, _, warnings = resolve_constraints({"op": ">"}, None)
        self.assertEqual(filters, [])
        self.assertTrue(warnings)

    # ---- ranking ----

    def test_valid_ranking_passthrough(self) -> None:
        _, ranking, warnings = resolve_constraints(
            None, {"limit": 3, "desc": True, "by_metric": "net_profit"}
        )
        self.assertEqual(ranking["limit"], 3)
        self.assertTrue(ranking["desc"])
        self.assertEqual(ranking["by_metric"], "net_profit")
        self.assertEqual(warnings, [])

    def test_ranking_defaults_desc_true_limit_10(self) -> None:
        _, ranking, _ = resolve_constraints(None, {"limit": 1})
        self.assertTrue(ranking["desc"])
        self.assertEqual(ranking["limit"], 1)

    def test_ranking_limit_must_be_positive(self) -> None:
        _, ranking, warnings = resolve_constraints(None, {"limit": 0})
        self.assertIsNone(ranking)
        self.assertTrue(any("≥1" in w for w in warnings))

    def test_ranking_limit_non_integer(self) -> None:
        _, ranking, warnings = resolve_constraints(None, {"limit": "abc"})
        self.assertIsNone(ranking)
        self.assertTrue(warnings)

    def test_ranking_not_a_dict(self) -> None:
        _, ranking, warnings = resolve_constraints(None, [1, 2, 3])
        self.assertIsNone(ranking)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
