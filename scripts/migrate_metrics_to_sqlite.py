"""把现有 metric_records.jsonl 迁移到 SQLite。

用法：
    python scripts/migrate_metrics_to_sqlite.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC_ROOT))

from finsight_agent.capabilities.structured_data.models import MetricRecord
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.config.settings import load_settings


def main() -> int:
    settings = load_settings()
    jsonl_path = settings.structured_data.storage_root / "metric_records.jsonl"
    sqlite_path = settings.structured_data.sqlite_path

    if not jsonl_path.exists():
        print(f"JSONL 文件不存在: {jsonl_path}")
        return 1

    # 读取 JSONL
    records: list[MetricRecord] = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            records.append(MetricRecord(**json.loads(stripped)))

    print(f"读取 {len(records)} 条记录 from {jsonl_path.name}")

    # 按公司分组
    by_company: dict[str, list[MetricRecord]] = {}
    for r in records:
        by_company.setdefault(r.company_name, []).append(r)

    print(f"涉及 {len(by_company)} 家公司:")
    for name, recs in by_company.items():
        print(f"  {name}: {len(recs)} 条")

    # 写入 SQLite
    repo = MetricRepository(sqlite_path=sqlite_path)
    repo.save_records(records)
    print(f"\n写入 SQLite: {sqlite_path}")

    # 验证
    loaded = repo.load_records()
    print(f"验证: SQLite 里有 {len(loaded)} 条记录")
    assert len(loaded) == len(records), f"数量不一致: {len(loaded)} vs {len(records)}"

    # 抽查
    if loaded:
        sample = loaded[0]
        print(f"\n抽查第 1 条:")
        print(f"  company_name: {sample.company_name}")
        print(f"  metric_name: {sample.metric_name}")
        print(f"  time_scope: {sample.time_scope}")
        print(f"  value: {sample.value}")

    print("\n迁移完成。JSONL 文件保留作备份。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
