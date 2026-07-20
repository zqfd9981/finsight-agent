"""检查比亚迪 total_assets/revenue 数据单位问题。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "var" / "data" / "structured_data" / "metrics.db"


def main() -> None:
    conn = sqlite3.connect(DB)
    try:
        print("=== 比亚迪 total_assets/revenue 数据 ===")
        rows = conn.execute(
            """SELECT metric_name, metric_label, value, unit, period_end,
                      statement_type, source_section, source_caption
               FROM metric_records
               WHERE company_code = '002594'
                 AND metric_name IN ('total_assets', 'revenue')
                 AND period_end = '2024-12-31'
               ORDER BY metric_name, statement_type"""
        ).fetchall()
        for r in rows:
            print(r)

        print("\n=== 比亚迪 vs 宁德时代 total_assets 单位对比 ===")
        rows = conn.execute(
            """SELECT company_code, company_name, metric_name, value, unit, period_end
               FROM metric_records
               WHERE metric_name = 'total_assets'
                 AND period_end = '2024-12-31'
                 AND company_code IN ('002594', '300750')
                 AND statement_type = 'consolidated'
                 AND source_section = 'balance_sheet'
               ORDER BY company_code"""
        ).fetchall()
        for r in rows:
            print(r)

        print("\n=== 比亚迪所有 unit 分布 ===")
        rows = conn.execute(
            """SELECT unit, COUNT(*) cnt
               FROM metric_records
               WHERE company_code = '002594'
               GROUP BY unit ORDER BY cnt DESC"""
        ).fetchall()
        for r in rows:
            print(r)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
