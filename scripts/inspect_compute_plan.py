"""独立测试 detect_compute_intent 输出 plan。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 添加 backend src 到 path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from finsight_agent.capabilities.structured_data.compute_intent import detect_compute_intent


def main() -> None:
    # 模拟 router 输出的 entities（两种 standard_name 变体都测）
    test_cases = [
        ("净利润复合增长率", "compound_growth_rate_net_profit"),
        ("净利润复合增长率", "net_profit_compound_growth_rate"),
        ("净利润同比增长率", "net_profit_growth_rate"),
        ("净利润同比增长率", "net_profit_yoy_growth"),
        ("净利润同比增长率", "yoy_net_profit"),
    ]
    query = "宁德时代2022到2024年净利润复合增长率是多少"

    for metric_raw, standard_name in test_cases:
        entities = {
            "company": {
                "raw": "宁德时代",
                "standard_name": "宁德时代",
                "stock_code": "300750",
            },
            "metric": {
                "raw": metric_raw,
                "standard_name": standard_name,
                "metric_type": "derived",
            },
            "time_scope": {
                "raw": "2022到2024年",
                "period_end": "",
                "fiscal_year": 2024,
            },
        }
        plan = detect_compute_intent(query, entities)
        print(f"\n--- metric_raw={metric_raw!r} standard_name={standard_name!r} ---")
        if plan is not None:
            print(f"  op={plan.op} metric={plan.metric!r} metric_raw={plan.metric_raw!r}")
            print(f"  periods={plan.periods} years={plan.years}")
        else:
            print(f"  plan=None")


if __name__ == "__main__":
    main()
