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

from finsight_agent.capabilities.structured_data.entities_validator import (
    EntitiesValidator,
    load_metric_keys,
)


_VALID_KEYS = {"net_profit", "revenue", "total_assets", "operating_cash_flow"}


def _validator() -> EntitiesValidator:
    return EntitiesValidator(valid_metric_keys=_VALID_KEYS)


class EntitiesValidatorTest(unittest.TestCase):
    def test_list_input_normal(self) -> None:
        v = _validator()
        out = v.validate({
            "company": [
                {"raw": "宁德时代", "standard_name": "宁德时代", "stock_code": "300750"},
                {"raw": "格力电器", "standard_name": "格力电器", "stock_code": "000651"},
            ],
            "metric": [
                {"raw": "净利润", "standard_name": "net_profit", "metric_type": "direct"},
                {"raw": "营收", "standard_name": "revenue", "metric_type": "direct"},
            ],
            "time_scope": [
                {"raw": "2024年", "period_end": "2024-12-31", "fiscal_year": 2024},
            ],
        })
        self.assertEqual(out["companies"], ["300750", "000651"])
        self.assertEqual(out["metrics"], ["net_profit", "revenue"])
        self.assertEqual(out["periods"], ["2024-12-31"])
        self.assertEqual(out["company_names"], ["宁德时代", "格力电器"])
        self.assertEqual(out["metric_raws"], ["净利润", "营收"])
        self.assertFalse(out["need_fallback"])

    def test_single_value_dict_wrapped_to_list(self) -> None:
        # 旧格式单值（dict）应包装成单元素列表
        v = _validator()
        out = v.validate({
            "company": {"raw": "宁德时代", "standard_name": "宁德时代", "stock_code": "300750"},
            "metric": {"raw": "净利润", "standard_name": "net_profit", "metric_type": "direct"},
            "time_scope": {"raw": "2024年", "period_end": "2024-12-31"},
        })
        self.assertEqual(out["companies"], ["300750"])
        self.assertEqual(out["metrics"], ["net_profit"])
        self.assertEqual(out["periods"], ["2024-12-31"])
        self.assertFalse(out["need_fallback"])

    def test_invalid_metric_key_dropped(self) -> None:
        # 不在受控词表的 key 应剔除；剔除后 metrics 为空 → need_fallback
        v = _validator()
        out = v.validate({
            "company": [{"standard_name": "宁德时代", "stock_code": "300750"}],
            "metric": [{"standard_name": "nonexistent_key", "raw": "瞎编"}],
            "time_scope": [{"period_end": "2024-12-31"}],
        })
        self.assertEqual(out["metrics"], [])
        self.assertTrue(out["need_fallback"])

    def test_partial_bad_metrics_kept_good(self) -> None:
        v = _validator()
        out = v.validate({
            "company": [{"standard_name": "宁德时代", "stock_code": "300750"}],
            "metric": [
                {"standard_name": "net_profit", "raw": "净利润"},
                {"standard_name": "bad_key", "raw": "坏"},
            ],
            "time_scope": [{"period_end": "2024-12-31"}],
        })
        self.assertEqual(out["metrics"], ["net_profit"])
        self.assertFalse(out["need_fallback"])

    def test_invalid_company_code_dropped(self) -> None:
        # 含注入字符的 code 应剔除
        v = _validator()
        out = v.validate({
            "company": [
                {"standard_name": "宁德时代", "stock_code": "300750"},
                {"standard_name": "黑客", "stock_code": "'; DROP--"},
            ],
            "metric": [{"standard_name": "net_profit", "raw": "净利润"}],
            "time_scope": [{"period_end": "2024-12-31"}],
        })
        self.assertEqual(out["companies"], ["300750"])

    def test_invalid_period_dropped(self) -> None:
        v = _validator()
        out = v.validate({
            "company": [{"standard_name": "宁德时代", "stock_code": "300750"}],
            "metric": [{"standard_name": "net_profit", "raw": "净利润"}],
            "time_scope": [
                {"period_end": "2024-12-31"},
                {"period_end": "not-a-date"},
                {"period_end": ""},
            ],
        })
        self.assertEqual(out["periods"], ["2024-12-31"])

    def test_empty_companies_triggers_fallback(self) -> None:
        v = _validator()
        out = v.validate({
            "company": [],
            "metric": [{"standard_name": "net_profit", "raw": "净利润"}],
            "time_scope": [{"period_end": "2024-12-31"}],
        })
        self.assertTrue(out["need_fallback"])

    def test_filters_and_ranking_passthrough(self) -> None:
        v = _validator()
        ranking = {"limit": 5, "by_metric": "net_profit", "desc": True}
        out = v.validate({
            "company": [{"standard_name": "宁德时代", "stock_code": "300750"}],
            "metric": [{"standard_name": "net_profit", "raw": "净利润"}],
            "time_scope": [{"period_end": "2024-12-31"}],
            "filters": [{"op": ">", "value": 100, "unit": "亿元"}],
            "ranking": ranking,
        })
        self.assertEqual(out["filters"], [{"op": ">", "value": 100, "unit": "亿元"}])
        self.assertEqual(out["ranking"], ranking)

    def test_load_metric_keys_from_real_aliases(self) -> None:
        # 验证真实 metric_aliases.json 能正确加载
        aliases_path = REPO_ROOT / "var" / "data" / "structured_data" / "metric_aliases.json"
        if not aliases_path.exists():
            self.skipTest("metric_aliases.json 不存在")
        keys = load_metric_keys(aliases_path)
        self.assertGreater(len(keys), 1000)  # 应有 4000+ 条
        self.assertIn("net_profit", keys)

    def test_empty_keyset_allows_all(self) -> None:
        # 受控词表为空时（测试场景）放行所有非空 key
        v = EntitiesValidator(valid_metric_keys=set())
        out = v.validate({
            "company": [{"standard_name": "X", "stock_code": "300750"}],
            "metric": [{"standard_name": "any_key", "raw": "任意"}],
            "time_scope": [{"period_end": "2024-12-31"}],
        })
        self.assertEqual(out["metrics"], ["any_key"])
        self.assertFalse(out["need_fallback"])


if __name__ == "__main__":
    unittest.main()
