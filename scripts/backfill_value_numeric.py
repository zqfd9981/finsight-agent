"""Phase B 回填：扫全表按 (value, unit, currency) 重算 value_numeric（归一到元）。

设计要点：
- 直接复用 structured_data.unit_normalizer.normalize_to_base_unit，
  与 ETL 写入新数据、build_value_filter 归一阈值使用同一函数，保证口径一致。
- 只填可归一的行（CNY + 已知人民币单位）；非 CNY / % / 未知单位保持 NULL。
- 按 rowid 批量 UPDATE，单事务提交，16 万行级别可控。
- 运行前请务必已对 metrics.db 做文件级备份（本脚本不负责备份）。
"""
from __future__ import annotations

import sqlite3
import sys

# 复用项目自身的归一逻辑，避免重写一份导致口径漂移。
_SYS_PATH = r"c:\D\大模型课程\openspec测试项目\backend\src\finsight_agent\capabilities\structured_data"
if _SYS_PATH not in sys.path:
    sys.path.insert(0, _SYS_PATH)

from unit_normalizer import normalize_to_base_unit  # noqa: E402

DB_PATH = r"c:\D\大模型课程\openspec测试项目\var\data\structured_data\metrics.db"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 0. 确认表结构（列名/存在性），避免盲目 UPDATE。
    cur.execute("PRAGMA table_info(metric_records)")
    cols = [c[1] for c in cur.fetchall()]
    print("columns:", cols)
    if "value_numeric" not in cols or "value" not in cols or "unit" not in cols:
        raise SystemExit("metric_records 缺少必要列，终止回填")

    # 1. 回填前计数
    cur.execute("SELECT COUNT(*), COUNT(value_numeric) FROM metric_records")
    total, nonnull_before = cur.fetchone()
    print(f"BEFORE: total={total} value_numeric_nonnull={nonnull_before}")

    # 2. 拉全表 (rowid, value, unit, currency)
    cur.execute("SELECT rowid, value, unit, currency FROM metric_records")
    rows = cur.fetchall()

    updates: list[tuple[float, int]] = []
    skipped = 0
    for rowid, value, unit, currency in rows:
        v = normalize_to_base_unit(value, unit, currency or "CNY")
        if v is None:
            skipped += 1
            continue
        updates.append((v, rowid))

    print(f"computed non-null: {len(updates)} | skipped (non-normalizable): {skipped}")

    # 3. 单事务批量 UPDATE
    cur.executemany(
        "UPDATE metric_records SET value_numeric=? WHERE rowid=?",
        updates,
    )
    conn.commit()

    # 4. 回填后计数
    cur.execute("SELECT COUNT(value_numeric) FROM metric_records")
    nonnull_after = cur.fetchone()[0]
    print(f"AFTER: value_numeric_nonnull={nonnull_after}")

    conn.close()
    print("DONE. 原始 value/unit 列保留，如需回滚请用 .bak 备份文件替换。")


if __name__ == "__main__":
    main()
