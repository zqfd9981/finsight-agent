"""检查宁德时代 net_profit 2022/2023/2024 数据是否存在（用于 cagr 计算排查）。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "var" / "data" / "structured_data" / "metrics.db"


def main() -> None:
    conn = sqlite3.connect(DB)
    try:
        print("=== 宁德时代 net_profit 2022/2023/2024 数据 ===")
        rows = conn.execute(
            """SELECT metric_name, metric_label, value, unit, period_end,
                      source_section, statement_type, source_caption
               FROM metric_records
               WHERE company_code = '300750'
                 AND metric_name = 'net_profit'
                 AND period_end IN ('2022-12-31', '2023-12-31', '2024-12-31')
               ORDER BY period_end, statement_type"""
        ).fetchall()
        for r in rows:
            print(r)

        print("\n=== 宁德时代所有 net_profit 期数 ===")
        rows = conn.execute(
            """SELECT DISTINCT period_end, COUNT(*) cnt
               FROM metric_records
               WHERE company_code = '300750' AND metric_name = 'net_profit'
               GROUP BY period_end ORDER BY period_end"""
        ).fetchall()
        for r in rows:
            print(r)

        print("\n=== 模拟 compute_cagr 取数 SQL ===")
        # 假设 assemble 生成的 SQL 类似这样
        rows = conn.execute(
            """SELECT company_code, company_name, metric_name, metric_label,
                      value, unit, period_end, statement_type, source_section
               FROM metric_records
               WHERE metric_name = 'net_profit'
                 AND period_end IN ('2022-12-31', '2023-12-31', '2024-12-31')
                 AND company_code = '300750'
               ORDER BY period_end"""
        ).fetchall()
        print(f"取到 {len(rows)} 行")
        for r in rows:
            print(r)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
