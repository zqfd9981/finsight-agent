"""synthesize_answer._format_computed_result 单测：路径② 计算结果格式化。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for _p in (str(REPO_ROOT), str(BACKEND_SRC_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from finsight_agent.control_plane.orchestrator.stage_runners.synthesize_answer import (  # noqa: E402
    _format_computed_result,
)


class FormatComputedResultTest(unittest.TestCase):
    def test_aggregate(self) -> None:
        out = _format_computed_result({
            "computed": True, "kind": "aggregate",
            "rows": [{"label": "净利润平均值", "value": 312.5, "unit": "亿元"}],
        })
        # 亿元 → 亿元（已是展示单位），312.5 是非整数保留 2 位小数 → "312.50"
        self.assertEqual(out, "净利润平均值为 312.50亿元。")

    def test_growth(self) -> None:
        out = _format_computed_result({
            "computed": True, "kind": "growth",
            "rows": [{"label": "净利润同比增长率", "value": 12.3, "unit": "%"}],
        })
        # % 不换算，format_display_value 原样返回 "12.3"
        self.assertEqual(out, "净利润同比增长率为 12.3%。")

    def test_consecutive_with_detail(self) -> None:
        out = _format_computed_result({
            "computed": True, "kind": "consecutive",
            "rows": [{"label": "连续2年净利润增长", "value": "是",
                      "detail": "2022年增长、2023年增长"}],
        })
        self.assertIn("连续2年净利润增长：是", out)
        self.assertIn("2022年增长", out)

    def test_consecutive_no_detail(self) -> None:
        out = _format_computed_result({
            "computed": True, "kind": "consecutive",
            "rows": [{"label": "连续2年净利润增长", "value": "否", "unit": "", "detail": ""}],
        })
        self.assertEqual(out, "连续2年净利润增长：否。")

    def test_rank(self) -> None:
        out = _format_computed_result({
            "computed": True, "kind": "rank",
            "rows": [{"label": "宁德时代", "value": 22.66, "unit": "%"},
                     {"label": "格力电器", "value": 18.3, "unit": "%"}],
        })
        self.assertIn("排名：", out)
        self.assertIn("宁德时代 22.66%", out)
        self.assertIn("格力电器 18.3%", out)

    def test_empty_rows(self) -> None:
        out = _format_computed_result({"computed": True, "kind": "aggregate", "rows": []})
        self.assertEqual(out, "计算失败或数据不足。")


if __name__ == "__main__":
    unittest.main()
