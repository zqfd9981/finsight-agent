"""检查 DB 中特定公司/指标的数据存储，用于排查 M-004/M-202/M-005 数据问题。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "var" / "data" / "structured_data" / "metrics.db"


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def main() -> None:
    # 查看比亚迪相关所有指标
    print("=" * 80)
    print("比亚迪 (002594) 营收/总资产/EPS 数据")
    print("=" * 80)
    rows = query(
        """SELECT metric_name, metric_label, value, unit, period_end, source_section,
                  statement_type, currency
           FROM metric_records
           WHERE company_code = '002594'
             AND metric_name IN ('revenue', 'total_assets', 'basic_eps',
                                 'total_revenue', 'operating_income')
             AND period_end LIKE '2024%'
           ORDER BY metric_name, statement_type"""
    )
    for r in rows:
        print(r)

    print("\n" + "=" * 80)
    print("宁德时代 (300750) EPS 数据")
    print("=" * 80)
    rows = query(
        """SELECT metric_name, metric_label, value, unit, period_end, source_section,
                  statement_type, currency
           FROM metric_records
           WHERE company_code = '300750'
             AND (metric_name LIKE '%eps%' OR metric_name LIKE '%per_share%'
                  OR metric_label LIKE '%每股%')
             AND period_end LIKE '2024%'
           ORDER BY metric_name, statement_type"""
    )
    for r in rows:
        print(r)

    print("\n" + "=" * 80)
    print("贵州茅台 (600519) 负债合计 数据")
    print("=" * 80)
    rows = query(
        """SELECT metric_name, metric_label, value, unit, period_end, source_section,
                  statement_type, currency
           FROM metric_records
           WHERE company_code = '600519'
             AND (metric_name LIKE '%liabilit%' OR metric_label LIKE '%负债%')
             AND period_end LIKE '2024%'
           ORDER BY metric_name, statement_type"""
    )
    for r in rows:
        print(r)

    # 查 value_numeric 是否填了
    print("\n" + "=" * 80)
    print("比亚迪营收/总资产 value_numeric 检查")
    print("=" * 80)
    rows = query(
        """SELECT metric_name, value, unit, value_numeric, period_end, statement_type
           FROM metric_records
           WHERE company_code = '002594'
             AND metric_name IN ('revenue', 'total_revenue', 'total_assets')
             AND period_end LIKE '2024%'
           ORDER BY metric_name, statement_type"""
    )
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
