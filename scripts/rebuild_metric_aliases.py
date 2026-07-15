"""从 SQLite 读取所有 metric_records，调 LLM 生成 aliases，重新归一化后写回。

用途：parse_filtered_pages.py --build-aliases 在 LLM 归一化阶段崩溃后，
用这个脚本单独完成归一化，不需要重新解析 PDF。

用法：
    python scripts/rebuild_metric_aliases.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.config.settings import load_settings
from finsight_agent.infra.llm.client import LlmClient


def main() -> int:
    settings = load_settings()
    sqlite_path = settings.structured_data.sqlite_path
    aliases_path = settings.structured_data.aliases_path

    print(f"SQLite: {sqlite_path}")
    print(f"Aliases: {aliases_path}")

    repo = MetricRepository(sqlite_path=sqlite_path)
    all_records = repo.load_records()
    print(f"读取 {len(all_records)} 条记录，{len(set(r.company_name for r in all_records))} 家公司")
    print(f"唯一 metric_label: {len(set(r.metric_label for r in all_records))}")

    if not all_records:
        print("没有记录，退出")
        return 1

    # 用 LLM 构建映射表
    normalizer = MetricNormalizer(
        aliases_path=aliases_path,
        llm_client=LlmClient(),
    )
    print(f"已有映射: {len(normalizer.aliases)} 条")
    print("=" * 70, flush=True)

    new_aliases = normalizer.build_aliases_from_records(all_records)
    print(f"\n新增映射: {len(new_aliases)} 条")
    print(f"总映射: {len(normalizer.aliases)} 条")

    if not new_aliases:
        print("无新增映射，不需要重新归一化")
        return 0

    # 重新归一化并写回 SQLite
    print("\n重新归一化并写回 SQLite ...", flush=True)
    grouped: dict[str, list] = defaultdict(list)
    for record in all_records:
        record.metric_name = normalizer.normalize(record.metric_label)
        grouped[record.company_name].append(record)

    for company_name, records in grouped.items():
        repo.save_records_for_company(company_name, records)

    # 验证
    updated_records = repo.load_records()
    unique_names = len(set(r.metric_name for r in updated_records))
    print(f"完成：重新归一化 {len(updated_records)} 条记录，{len(grouped)} 家公司")
    print(f"归一化后唯一 metric_name: {unique_names}（归一化前 2892）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
