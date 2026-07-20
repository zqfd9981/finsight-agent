"""compute_registry 单测：路径② 纯函数计算。"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# sys.path 注入（与现有测试风格一致）
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_SRC = _REPO_ROOT / "backend" / "src"
for _p in (str(_REPO_ROOT), str(_BACKEND_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from finsight_agent.capabilities.structured_data.compute_registry import compute  # noqa: E402
from finsight_agent.capabilities.structured_data.models import ComputePlan, MetricRecord  # noqa: E402


def _rec(
    company: str = "宁德时代",
    code: str = "300750",
    metric: str = "net_profit",
    period: str = "2024-12-31",
    value: str = "441.21",
    unit: str = "亿元",
) -> MetricRecord:
    return MetricRecord(
        company_name=company, company_code=code, metric_name=metric, metric_label=metric,
        time_scope=period, period_end=period, value=value, unit=unit, currency="CNY",
        source_type="local", source_document_id="d.pdf", source_table_id="t",
        source_caption="c", confidence="high",
    )


def _plan(op: str, metric_raw: str = "净利润", years: int = 0) -> ComputePlan:
    return ComputePlan(
        op=op, metric="net_profit", metric_raw=metric_raw,
        companies=["300750"], company_names=["宁德时代"],
        periods=["2024-12-31"], years=years,
    )


class ComputeRegistryTests(unittest.TestCase):
    def test_avg(self) -> None:
        rows = [_rec(value="100"), _rec(value="200"), _rec(value="300")]
        kind, out = compute("avg", rows, _plan("avg"))
        self.assertEqual(kind, "aggregate")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["value"], 200.0)
        self.assertIn("平均值", out[0]["label"])

    def test_sum(self) -> None:
        rows = [_rec(value="100"), _rec(value="200")]
        _, out = compute("sum", rows, _plan("sum"))
        self.assertEqual(out[0]["value"], 300.0)

    def test_max_picks_company(self) -> None:
        rows = [_rec(company="A", code="001", value="100"),
                _rec(company="B", code="002", value="300"),
                _rec(company="C", code="003", value="200")]
        _, out = compute("max", rows, _plan("max"))
        self.assertIn("B", out[0]["label"])
        self.assertEqual(out[0]["value"], 300.0)

    def test_min(self) -> None:
        rows = [_rec(value="100"), _rec(value="50"), _rec(value="200")]
        _, out = compute("min", rows, _plan("min"))
        self.assertEqual(out[0]["value"], 50.0)

    def test_count(self) -> None:
        rows = [_rec(), _rec(), _rec()]
        _, out = compute("count", rows, _plan("count"))
        self.assertEqual(out[0]["value"], 3)

    def test_yoy(self) -> None:
        rows = [_rec(period="2023-12-31", value="100"),
                _rec(period="2024-12-31", value="120")]
        kind, out = compute("yoy", rows, _plan("yoy"))
        self.assertEqual(kind, "growth")
        self.assertEqual(out[0]["value"], 20.0)  # (120-100)/100*100

    def test_yoy_negative(self) -> None:
        rows = [_rec(period="2023-12-31", value="100"),
                _rec(period="2024-12-31", value="80")]
        _, out = compute("yoy", rows, _plan("yoy"))
        self.assertEqual(out[0]["value"], -20.0)

    def test_cagr(self) -> None:
        # 100 -> 121 over 2 years = 10% CAGR
        rows = [_rec(period="2022-12-31", value="100"),
                _rec(period="2023-12-31", value="110"),
                _rec(period="2024-12-31", value="121")]
        _, out = compute("cagr", rows, _plan("cagr", years=2))
        self.assertAlmostEqual(out[0]["value"], 10.0, places=2)

    def test_consecutive_growth_true(self) -> None:
        rows = [_rec(period="2022-12-31", value="100"),
                _rec(period="2023-12-31", value="110"),
                _rec(period="2024-12-31", value="121")]
        _, out = compute("consecutive_growth", rows, _plan("consecutive_growth", years=2))
        self.assertEqual(out[0]["value"], "是")
        self.assertIn("detail", out[0])

    def test_consecutive_growth_false(self) -> None:
        rows = [_rec(period="2022-12-31", value="100"),
                _rec(period="2023-12-31", value="90"),
                _rec(period="2024-12-31", value="121")]
        _, out = compute("consecutive_growth", rows, _plan("consecutive_growth", years=2))
        self.assertEqual(out[0]["value"], "否")

    def test_empty_rows_returns_empty(self) -> None:
        kind, out = compute("avg", [], _plan("avg"))
        self.assertEqual(out, [])

    def test_yoy_insufficient_periods(self) -> None:
        rows = [_rec(period="2024-12-31", value="100")]
        _, out = compute("yoy", rows, _plan("yoy"))
        self.assertEqual(out, [])

    def test_cagr_zero_base_returns_empty(self) -> None:
        rows = [_rec(period="2022-12-31", value="0"),
                _rec(period="2024-12-31", value="100")]
        _, out = compute("cagr", rows, _plan("cagr", years=2))
        self.assertEqual(out, [])

    def test_unknown_op(self) -> None:
        kind, out = compute("bogus", [_rec()], _plan("avg"))
        self.assertEqual(kind, "")
        self.assertEqual(out, [])

    def test_non_numeric_values_filtered(self) -> None:
        rows = [_rec(value="100"), _rec(value="N/A"), _rec(value="200")]
        _, out = compute("avg", rows, _plan("avg"))
        self.assertEqual(out[0]["value"], 150.0)


if __name__ == "__main__":
    unittest.main()
