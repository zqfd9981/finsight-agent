"""检查 DB 中 EPS 相关 metric_name 分布，看 aliases 与实际存储是否一致。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "var" / "data" / "structured_data" / "metrics.db"


def main() -> None:
    conn = sqlite3.connect(DB)
    try:
        print("=" * 80)
        print("EPS 相关 metric_name 统计")
        print("=" * 80)
        rows = conn.execute(
            """SELECT metric_name, metric_label, COUNT(*) AS cnt, MIN(unit) AS u
               FROM metric_records
               WHERE metric_name LIKE '%eps%' OR metric_name LIKE '%per_share%'
                  OR metric_label LIKE '%每股收益%'
               GROUP BY metric_name, metric_label
               ORDER BY cnt DESC
               LIMIT 30"""
        ).fetchall()
        for r in rows:
            print(r)

        print("\n" + "=" * 80)
        print("total_liabilities 命中检查（任意 5 行）")
        print("=" * 80)
        rows = conn.execute(
            """SELECT DISTINCT company_code, metric_name, metric_label, value, unit, period_end
               FROM metric_records
               WHERE metric_name = 'total_liabilities'
               LIMIT 5"""
        ).fetchall()
        for r in rows:
            print(r)

        print("\n" + "=" * 80)
        print("负债合计 在 metric_label 中的统计")
        print("=" * 80)
        rows = conn.execute(
            """SELECT metric_name, metric_label, COUNT(*) AS cnt
               FROM metric_records
               WHERE metric_label LIKE '%负债合计%'
               GROUP BY metric_name, metric_label
               ORDER BY cnt DESC
               LIMIT 20"""
        ).fetchall()
        for r in rows:
            print(r)

        print("\n" + "=" * 80)
        print("metric_aliases 中查 basic_eps 是否有 DB 数据")
        print("=" * 80)
        rows = conn.execute(
            "SELECT COUNT(*) FROM metric_records WHERE metric_name = 'basic_eps'"
        ).fetchall()
        print("basic_eps 总数:", rows[0][0])
        rows = conn.execute(
            "SELECT COUNT(*) FROM metric_records WHERE metric_name = 'basic_earnings_per_share'"
        ).fetchall()
        print("basic_earnings_per_share 总数:", rows[0][0])

    finally:
        conn.close()


if __name__ == "__main__":
    main()
