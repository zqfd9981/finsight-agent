from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.sql_assembler import (
    AssemblerError,
    assemble,
    build_period_range,
)


class SqlAssemblerTest(unittest.TestCase):
    def test_single_metric_single_company_single_period(self) -> None:
        sql, params = assemble(
            companies=["300750"],
            metrics=["net_profit"],
            periods=["2024-12-31"],
        )
        self.assertIn("company_code IN (?)", sql)
        self.assertIn("metric_name IN (?)", sql)
        self.assertIn("period_end IN (?)", sql)
        self.assertEqual(params, ("300750", "net_profit", "2024-12-31"))

    def test_multi_metrics_uses_in_clause(self) -> None:
        sql, _ = assemble(
            companies=["300750"],
            metrics=["net_profit", "revenue"],
            periods=["2024-12-31"],
        )
        self.assertIn("metric_name IN (?,?)", sql)

    def test_multi_companies_uses_in_clause(self) -> None:
        sql, _ = assemble(
            companies=["300750", "000651"],
            metrics=["net_profit"],
            periods=["2024-12-31"],
        )
        self.assertIn("company_code IN (?,?)", sql)

    def test_multi_periods_uses_in_clause(self) -> None:
        sql, _ = assemble(
            companies=["300750"],
            metrics=["net_profit"],
            periods=["2024-12-31", "2023-12-31"],
        )
        self.assertIn("period_end IN (?,?)", sql)

    def test_empty_periods_omits_period_clause(self) -> None:
        sql, _ = assemble(
            companies=["300750"],
            metrics=["net_profit"],
            periods=[],
        )
        # 窗口函数 PARTITION BY 含 period_end 是正常的；这里只断言不拼 period 过滤子句
        self.assertNotIn("period_end IN", sql)

    def test_value_filter_normalizes_unit(self) -> None:
        # 1000 亿 → 1000 × 1e8 = 1e11 元
        sql, params = assemble(
            companies=["300750"],
            metrics=["revenue"],
            periods=["2024-12-31"],
            filters=[{"op": ">", "value": 1000, "unit": "亿元"}],
        )
        self.assertIn("value_numeric > ?", sql)
        self.assertIn("currency = 'CNY'", sql)
        self.assertEqual(params[-1], 1e11)

    def test_ranking_appends_order_limit(self) -> None:
        sql, _ = assemble(
            companies=["300750", "000651"],
            metrics=["net_profit"],
            periods=["2024-12-31"],
            ranking={"limit": 5, "by_metric": "net_profit", "desc": True},
        )
        self.assertIn("ORDER BY value_numeric DESC LIMIT 5", sql)

    def test_statement_priority_window_present(self) -> None:
        # 关键：多公司场景必须用窗口函数取每实体合并口径唯一行
        sql, _ = assemble(
            companies=["300750", "000651"],
            metrics=["net_profit"],
            periods=["2024-12-31"],
        )
        self.assertIn("ROW_NUMBER() OVER (", sql)
        self.assertIn("PARTITION BY company_code, period_end", sql)
        self.assertIn("rn = 1", sql)
        # statement_type 优先级必须出现（防主 T2S 方案丢优先级的 bug）
        self.assertIn("CASE statement_type", sql)

    def test_source_section_whitelist_complete(self) -> None:
        # 关键：四表 + unknown 必须都在，修正主 T2S 方案只放 income_statement 的 bug
        sql, _ = assemble(
            companies=["300750"],
            metrics=["total_assets"],
            periods=["2024-12-31"],
        )
        for section in (
            "income_statement",
            "cash_flow_statement",
            "balance_sheet",
            "equity_statement",
            "unknown",
        ):
            self.assertIn(section, sql)
        self.assertNotIn("'notes'", sql)

    def test_no_string_interpolation_of_user_input(self) -> None:
        # 用户值必须走占位符，绝不拼进 SQL 字符串
        sql, params = assemble(
            companies=["300750'; DROP TABLE--"],
            metrics=["net_profit"],
            periods=["2024-12-31"],
        )
        # 危险字符串应原样出现在 params 里，不出现在 SQL 的 WHERE 子句文本里
        self.assertIn("300750'; DROP TABLE--", params)
        self.assertNotIn("DROP TABLE", sql)

    def test_empty_companies_raises(self) -> None:
        with self.assertRaises(AssemblerError):
            assemble(companies=[], metrics=["net_profit"], periods=["2024-12-31"])

    def test_empty_metrics_raises(self) -> None:
        with self.assertRaises(AssemblerError):
            assemble(companies=["300750"], metrics=[], periods=["2024-12-31"])

    def test_unsupported_op_raises(self) -> None:
        with self.assertRaises(AssemblerError):
            assemble(
                companies=["300750"],
                metrics=["net_profit"],
                periods=["2024-12-31"],
                filters=[{"op": "LIKE", "value": 100, "unit": "元"}],
            )

    def test_non_normalizable_unit_filter_raises(self) -> None:
        # % 单位无法归一，filter 应触发 AssemblerError（而非静默拼错 SQL）
        with self.assertRaises(AssemblerError):
            assemble(
                companies=["300750"],
                metrics=["net_profit"],
                periods=["2024-12-31"],
                filters=[{"op": ">", "value": 50, "unit": "%"}],
            )

    def test_companies_none_omits_company_clause(self) -> None:
        # 全公司（compute 路径"所有公司平均值"用）：不拼 company_code 过滤
        sql, params = assemble(
            companies=None,
            metrics=["net_profit"],
            periods=["2024-12-31"],
        )
        self.assertNotIn("company_code IN", sql)
        self.assertIn("metric_name IN (?)", sql)
        self.assertEqual(params, ("net_profit", "2024-12-31"))

    def test_companies_none_returns_all_companies(self) -> None:
        # 确认 None 与具体列表的区别：None 不进 params（company_code 仍出现在 PARTITION BY，那是窗口去重）
        sql_all, params_all = assemble(
            companies=None, metrics=["net_profit"], periods=["2024-12-31"]
        )
        sql_one, params_one = assemble(
            companies=["300750"], metrics=["net_profit"], periods=["2024-12-31"]
        )
        self.assertNotIn("company_code IN", sql_all)
        self.assertIn("company_code IN", sql_one)
        self.assertEqual(len(params_all), 2)  # metric + period
        self.assertEqual(len(params_one), 3)  # company + metric + period

    def test_build_period_range_expands_years(self) -> None:
        periods = build_period_range(2021, 2024)
        self.assertEqual(periods, ["2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31"])

    def test_build_period_range_swaps_if_reversed(self) -> None:
        periods = build_period_range(2024, 2022)
        self.assertEqual(periods, ["2022-12-31", "2023-12-31", "2024-12-31"])


if __name__ == "__main__":
    unittest.main()
