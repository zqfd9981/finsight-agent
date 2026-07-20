"""检查宁德时代 net_profit 2023/2024 数据是否存在（用于 yoy 计算排查）。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "var" / "data" / "structured_data" / "metrics.db"


def main() -> None:
    conn = sqlite3.connect(DB)
    try:
        print("宁德时代 net_profit 2023/2024 数据：")
        rows = conn.execute(
            """SELECT metric_name, metric_label, value, unit, period_end, source_section, statement_type
               FROM metric_records
               WHERE company_code = '300750'
                 AND metric_name = 'net_profit'
                 AND period_end IN ('2023-12-31', '2024-12-31')
               ORDER BY period_end, statement_type"""
        ).fetchall()
        for r in rows:
            print(r)

        print("\n宁德时代 net_profit_growth_rate 数据（看 DB 是否有此 metric_name）：")
        rows = conn.execute(
            """SELECT metric_name, COUNT(*) FROM metric_records
               WHERE metric_name LIKE '%growth%' OR metric_name LIKE '%yoy%'
               GROUP BY metric_name LIMIT 20"""
        ).fetchall()
        for r in rows:
            print(r)

        # 直接模拟 compute_yoy 的 SQL
        print("\n模拟 compute_yoy 取数 SQL（companies=None 全公司，metric=net_profit，2期）：")
        rows = conn.execute(
            """SELECT company_code, metric_name, value, unit, period_end, statement_type,
                      value_numeric
               FROM metric_records
               WHERE metric_name = 'net_profit'
                 AND period_end IN ('2023-12-31', '2024-12-31')
                 AND source_section IN ('income_statement','cash_flow_statement',
                                        'balance_sheet','equity_statement','unknown')
               ORDER BY company_code, period_end
               LIMIT 10"""
        ).fetchall()
        for r in rows:
            print(r)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
