"""对 metric_records 去重（按自然键保留一条），修复重建引入的重复行。

背景：
  - rebuild_from_cache.py 在零成本模式下，注释表其实仍会被 rule 回退提取
    （source_section='notes'），而脚本又额外并入旧库 notes，导致用友网络等
    notes 翻倍。
  - 此外 TableExtractor 本身在权益变动表等位置会产生重复行
    （whole-db 约 2196 条重复）。

自然键（同一指标单元格的唯一标识）：
  company_name | metric_name | time_scope | period_end | value |
  source_table_id | source_section | statement_type

修复方式：对每组成键保留 id 最小的一条，删除其余。幂等、安全
（同一表同一指标同一数值→同一单元格，重复即冗余）。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB = Path("var/data/structured_data/metrics.db")

NATURAL_KEY = (
    "company_name, metric_name, time_scope, period_end, value, "
    "source_table_id, source_section, statement_type"
)


def dedup(db_path: Path) -> tuple[int, int]:
    with sqlite3.connect(str(db_path)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM metric_records").fetchone()[0]
        # 保留每组自然键中 id 最小的一行
        conn.execute(
            f"""
            DELETE FROM metric_records
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM metric_records
                GROUP BY {NATURAL_KEY}
            )
            """
        )
        after = conn.execute("SELECT COUNT(*) FROM metric_records").fetchone()[0]
        conn.commit()
    return before, after


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DB
    b, a = dedup(db)
    print(f"[去重] {db}")
    print(f"  修复前: {b} 行")
    print(f"  修复后: {a} 行")
    print(f"  删除重复: {b - a} 行")
