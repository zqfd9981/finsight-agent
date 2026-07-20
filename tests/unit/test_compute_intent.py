"""compute_intent 单测：路径② 确定性意图检测。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_SRC = _REPO_ROOT / "backend" / "src"
for _p in (str(_REPO_ROOT), str(_BACKEND_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from finsight_agent.capabilities.structured_data.compute_intent import detect_compute_intent  # noqa: E402


def _entities(metric="净利润", code="300750", period="2024-12-31"):
    return {
        "company": [{"standard_name": "宁德时代", "raw": "宁德时代", "stock_code": code}],
        "metric": [{"standard_name": "net_profit", "raw": metric, "metric_type": "direct"}],
        "time_scope": [{"raw": "2024年", "period_end": period, "fiscal_year": 2024}],
    }


class ComputeIntentTests(unittest.TestCase):
    def test_avg_detected(self) -> None:
        plan = detect_compute_intent("宁德时代2024净利润平均值", _entities())
        self.assertIsNotNone(plan)
        self.assertEqual(plan.op, "avg")
        self.assertEqual(plan.metric, "net_profit")
        self.assertEqual(plan.metric_raw, "净利润")

    def test_sum_detected(self) -> None:
        plan = detect_compute_intent("所有公司2024净利润总和", _entities())
        self.assertIsNotNone(plan)
        self.assertEqual(plan.op, "sum")

    def test_cagr_detected_with_years(self) -> None:
        plan = detect_compute_intent("宁德时代近3年净利润复合增长率", _entities())
        self.assertIsNotNone(plan)
        self.assertEqual(plan.op, "cagr")
        self.assertEqual(plan.years, 3)
        # 3 年 CAGR 需 years+1=4 个点（2021→2024，3 年跨度）
        self.assertEqual(plan.periods, ["2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31"])

    def test_consecutive_growth_detected(self) -> None:
        plan = detect_compute_intent("宁德时代连续3年净利润增长吗", _entities())
        self.assertIsNotNone(plan)
        self.assertEqual(plan.op, "consecutive_growth")
        self.assertEqual(plan.years, 3)

    def test_yoy_detected(self) -> None:
        plan = detect_compute_intent("宁德时代净利润同比增长率", _entities())
        self.assertIsNotNone(plan)
        self.assertEqual(plan.op, "yoy")

    def test_count_detected(self) -> None:
        plan = detect_compute_intent("净利润超100亿的有多少家公司", _entities())
        self.assertIsNotNone(plan)
        self.assertEqual(plan.op, "count")

    def test_no_compute_keyword_returns_none(self) -> None:
        # 普通取数查询，不应触发计算路径
        plan = detect_compute_intent("宁德时代2024净利润是多少", _entities())
        self.assertIsNone(plan)

    def test_topn_not_misrouted_to_max(self) -> None:
        # "净利润最高的公司" 是 TopN（Assembler ranking），不应被 compute 抢路由
        plan = detect_compute_intent("净利润最高的公司是哪家", _entities())
        self.assertIsNone(plan)

    def test_no_metric_returns_none(self) -> None:
        ents = _entities()
        ents["metric"] = []
        plan = detect_compute_intent("所有公司平均值", ents)
        self.assertIsNone(plan)

    def test_empty_company_means_all(self) -> None:
        # "所有公司平均值" → company 为空，plan.companies 为空（service 用 None 全公司）
        ents = _entities()
        ents["company"] = []
        plan = detect_compute_intent("所有公司2024净利润平均值", ents)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.companies, [])

    def test_consecutive_priority_over_yoy(self) -> None:
        # "连续增长"含"增长"，应优先 consecutive 而非 yoy
        plan = detect_compute_intent("连续2年增长", _entities())
        self.assertEqual(plan.op, "consecutive_growth")

    def test_cagr_priority_over_yoy(self) -> None:
        plan = detect_compute_intent("复合增长率", _entities())
        self.assertEqual(plan.op, "cagr")

    def test_empty_query_returns_none(self) -> None:
        self.assertIsNone(detect_compute_intent("", _entities()))


if __name__ == "__main__":
    unittest.main()
