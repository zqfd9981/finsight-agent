from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.control_plane.orchestrator.stage_runners.synthesize_answer import (
    _aggregate_multi_records,
    _safe_float_val,
)


def _rec(**overrides) -> dict:
    defaults = dict(
        company_name="宁德时代", company_code="300750", metric_name="net_profit",
        metric_label="净利润", period_end="2024-12-31", value="507", unit="亿元",
    )
    defaults.update(overrides)
    return defaults


class SafeFloatValTest(unittest.TestCase):
    def test_normal(self) -> None:
        self.assertEqual(_safe_float_val("507.45"), 507.45)

    def test_thousands_sep(self) -> None:
        self.assertEqual(_safe_float_val("1,234.56"), 1234.56)

    def test_paren_negative(self) -> None:
        self.assertEqual(_safe_float_val("(789.00)"), -789.0)

    def test_invalid_returns_zero(self) -> None:
        self.assertEqual(_safe_float_val("N/A"), 0.0)
        self.assertEqual(_safe_float_val(""), 0.0)


class AggregateMultiRecordsTest(unittest.TestCase):
    def test_multi_company_ranking(self) -> None:
        # 多公司单指标 → 排名格式，按 value 降序
        summary = _aggregate_multi_records([
            _rec(company_name="格力电器", company_code="000651", value="321"),
            _rec(company_name="宁德时代", company_code="300750", value="507"),
        ])
        self.assertIn("排名", summary)
        # 宁德(507) 应排在格力(321)前
        self.assertLess(summary.index("宁德时代"), summary.index("格力电器"))
        self.assertIn("507亿元", summary)
        self.assertIn("321亿元", summary)

    def test_multi_metrics_listing(self) -> None:
        # 单公司多指标 → 多指标列举
        summary = _aggregate_multi_records([
            _rec(metric_name="net_profit", metric_label="净利润", value="507"),
            _rec(metric_name="revenue", metric_label="营收", value="4009"),
        ])
        self.assertIn("净利润", summary)
        self.assertIn("营收", summary)
        self.assertIn("507亿元", summary)
        self.assertIn("4009亿元", summary)

    def test_multi_periods_comparison(self) -> None:
        # 单公司单指标多年 → 按年份降序列举
        summary = _aggregate_multi_records([
            _rec(period_end="2023-12-31", value="441"),
            _rec(period_end="2024-12-31", value="507"),
        ])
        self.assertIn("2024年", summary)
        self.assertIn("2023年", summary)
        # 2024 应排在 2023 前（降序）
        self.assertLess(summary.index("2024年"), summary.index("2023年"))

    def test_empty_records(self) -> None:
        self.assertEqual(_aggregate_multi_records([]), "未找到对应指标数据。")

    def test_fallback_listing(self) -> None:
        # 多公司多指标（不属于上述任一模式）→ 兜底逐行列举
        summary = _aggregate_multi_records([
            _rec(company_name="A", metric_name="net_profit", metric_label="净利润", value="100"),
            _rec(company_name="B", metric_name="revenue", metric_label="营收", value="200"),
        ])
        self.assertIn("A", summary)
        self.assertIn("B", summary)
        self.assertIn("100亿元", summary)
        self.assertIn("200亿元", summary)


if __name__ == "__main__":
    unittest.main()
