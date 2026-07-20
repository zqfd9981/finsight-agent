"""直接测试 query_via_assembler 用 fallback_entities 能否取到数据。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finsight_agent.capabilities.structured_data.service import StructuredDataService
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer


def main() -> None:
    # 模拟 _rewrite_entities_for_raw_metric 的输出
    fallback_entities = {
        "company": {
            "raw": "宁德时代",
            "standard_name": "宁德时代",
            "stock_code": "300750",
        },
        "metric": {
            "raw": "净利润",
            "standard_name": "net_profit",
            "metric_type": "direct",
        },
        "time_scope": [
            {"period_end": "2022-12-31", "raw": ""},
            {"period_end": "2023-12-31", "raw": ""},
            {"period_end": "2024-12-31", "raw": ""},
        ],
    }

    aliases_path = Path(__file__).resolve().parents[1] / "var" / "data" / "structured_data" / "metric_aliases.json"
    normalizer = MetricNormalizer(aliases_path=aliases_path)
    svc = StructuredDataService(normalizer=normalizer)

    print("=== 调用 query_via_assembler ===")
    result = svc.query_via_assembler(fallback_entities)
    print(f"via: {result.via}")
    print(f"is_degraded: {result.is_degraded}")
    print(f"explanation: {result.explanation}")
    print(f"records count: {len(result.records)}")
    print(f"sql_used: {result.sql_used}")
    for r in result.records[:5]:
        print(f"  {r}")


if __name__ == "__main__":
    main()
