from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.unit_normalizer import (
    is_normalizable,
    normalize_to_base_unit,
)


class UnitNormalizerTest(unittest.TestCase):
    def test_yi_to_yuan(self) -> None:
        self.assertAlmostEqual(normalize_to_base_unit("507.45", "亿元"), 5.0745e10)

    def test_qian_yuan_to_yuan(self) -> None:
        self.assertAlmostEqual(normalize_to_base_unit("1234.56", "千元"), 1_234_560.0)

    def test_wan_yuan_with_thousands_sep(self) -> None:
        # 千分位逗号应被清洗
        self.assertAlmostEqual(normalize_to_base_unit("1,234.56", "万元"), 12_345_600.0)

    def test_paren_negative(self) -> None:
        # 括号负值 (789.00) → -789.0
        self.assertAlmostEqual(normalize_to_base_unit("(789.00)", "元"), -789.0)

    def test_percent_not_normalizable(self) -> None:
        # 百分比无归一意义
        self.assertIsNone(normalize_to_base_unit("95.2", "%"))

    def test_non_cny_returns_none(self) -> None:
        self.assertIsNone(normalize_to_base_unit("100", "元", "USD"))

    def test_placeholder_returns_none(self) -> None:
        for ph in ("", "-", "—", "N/A"):
            self.assertIsNone(normalize_to_base_unit(ph, "元"))

    def test_unknown_unit_returns_none(self) -> None:
        self.assertIsNone(normalize_to_base_unit("100", "兆"))

    def test_is_normalizable(self) -> None:
        self.assertTrue(is_normalizable("亿元"))
        self.assertTrue(is_normalizable("千元"))
        self.assertFalse(is_normalizable("%"))
        self.assertFalse(is_normalizable("元", "USD"))


if __name__ == "__main__":
    unittest.main()
