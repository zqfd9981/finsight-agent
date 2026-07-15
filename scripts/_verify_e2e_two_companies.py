"""2 家公司完整链路验证：extract → save → query。

治本修复后的端到端验证，跑通后才全量重抽取 88 家。
不重跑 MinerU，只用现有 __structured/tables.jsonl 重新提取 + 写库 + 查询。
"""
from __future__ import annotations

import shutil
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT))

from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.models import MetricQuery
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor
from finsight_agent.config.settings import load_settings

settings = load_settings()
sqlite_path = Path(settings.structured_data.sqlite_path)
aliases_path = settings.structured_data.aliases_path
normalizer = MetricNormalizer(aliases_path=aliases_path)

# 备份 DB
backup_path = sqlite_path.with_suffix(".db.bak")
if not backup_path.exists():
    shutil.copy2(sqlite_path, backup_path)
    print(f"[备份] {sqlite_path} → {backup_path}")
else:
    print(f"[备份] 已存在 {backup_path}，跳过备份")

repo = MetricRepository(sqlite_path=sqlite_path)

COMPANIES = [
    ("比亚迪", "002594_比亚迪"),
    ("华能水电", "600025_华能水电"),
]

parsed_root = REPO_ROOT / "var" / "data" / "parsed_filings"

# ============================================================
# Step 1: extract + save
# ============================================================
print("\n" + "=" * 70)
print("Step 1: extract + save（从现有 tables.jsonl 重新提取并写库）")
print("=" * 70)

for display_name, dir_prefix in COMPANIES:
    candidates = list(parsed_root.glob(f"{dir_prefix}*__structured"))
    if not candidates:
        print(f"  [跳过] 找不到 {dir_prefix}*__structured 目录")
        continue
    tables_file = candidates[0] / "tables.jsonl"
    if not tables_file.exists():
        print(f"  [跳过] 找不到 tables.jsonl")
        continue

    company_code = dir_prefix.split("_")[0]
    extractor = TableExtractor(
        company_code=company_code,
        company_name=display_name,
        source_document_id=f"{dir_prefix}__structured",
        normalizer=normalizer,
    )
    records = extractor.extract_from_tables_file(tables_file)
    print(f"\n  [{display_name}] 提取 {len(records)} 条记录")

    # statement_type 分布
    st_counter = Counter(r.statement_type for r in records)
    print(f"    statement_type 分布: {dict(st_counter)}")

    # time_scope 分布
    ts_counter = Counter(r.time_scope for r in records)
    print(f"    time_scope 分布: {dict(ts_counter)}")

    # period_end 分布
    pe_counter = Counter(r.period_end for r in records)
    print(f"    period_end 分布: {dict(pe_counter)}")

    # 异常 time_scope 检查
    abnormal = [
        ts for ts in ts_counter
        if any(c.isdigit() for c in ts) and "年" not in ts and "余额" not in ts and "期" not in ts
    ]
    if abnormal:
        print(f"    !! 异常 time_scope: {abnormal}")
    else:
        print(f"    OK 无异常 time_scope")

    # 写库
    repo.save_records_for_company(display_name, records)
    print(f"    已写入 SQLite（save_records_for_company）")

# ============================================================
# Step 2: query 验证
# ============================================================
print("\n" + "=" * 70)
print("Step 2: query 验证（find_best_match）")
print("=" * 70)

QUERIES = [
    # (描述, company_name, metric_name, time_scope, metric_label_raw, 期望说明)
    ("比亚迪 2024年 归母净利润", "比亚迪", "net_profit", "2024年", "净利润", "应命中 consolidated 口径"),
    ("比亚迪 2024年 营业收入", "比亚迪", "revenue", "2024年", "营业收入", "value 应为大额正数"),
    ("比亚迪 2023年 归母净利润", "比亚迪", "net_profit", "2023年", "净利润", "period_end 应为 2023-12-31"),
    ("比亚迪 latest 归母净利润", "比亚迪", "net_profit", "latest", "净利润", "应取 2024-12-31"),
    ("比亚迪 2024-12-31 营业收入", "比亚迪", "revenue", "2024-12-31", "营业收入", "日期格式匹配"),
    ("华能水电 2024年 营业收入", "华能水电", "revenue", "2024年", "营业收入", "应命中"),
    ("华能水电 2024年 货币资金", "华能水电", "cash_and_equivalents", "2024年", "货币资金", "应返回 consolidated 3,093,114,296.74（非母公司 182,575,663.92）"),
    ("华能水电 latest 营业收入", "华能水电", "revenue", "latest", "营业收入", "应取最新期间"),
    # 口语兜底测试：用"净利润"查 net_profit_attributable_to_parent
    ("比亚迪 2024年 口语净利润兜底", "比亚迪", "net_profit_attributable_to_parent", "2024年", "净利润", "metric_label LIKE 兜底"),
]

all_pass = True
for desc, company, metric, scope, raw, expect in QUERIES:
    result = repo.find_best_match(
        MetricQuery(
            company_name=company,
            metric_name=metric,
            time_scope=scope,
            metric_label_raw=raw,
        )
    )
    if result is None:
        print(f"\n  [FAIL] {desc}")
        print(f"         期望: {expect}")
        print(f"         实际: 未命中")
        all_pass = False
        continue
    print(f"\n  [OK] {desc}")
    print(f"       metric_label={result.metric_label!r}")
    print(f"       metric_name={result.metric_name!r}")
    print(f"       time_scope={result.time_scope!r} | period_end={result.period_end}")
    print(f"       value={result.value} | statement_type={result.statement_type}")
    print(f"       期望: {expect}")

# ============================================================
# Step 3: 合并/母公司口径优先级验证
# ============================================================
print("\n" + "=" * 70)
print("Step 3: 合并/母公司口径优先级验证")
print("=" * 70)

# 查找同时有 consolidated 和 parent_only 的指标
import sqlite3
from contextlib import closing

with closing(sqlite3.connect(sqlite_path)) as conn:
    rows = conn.execute(
        """
        SELECT company_name, metric_name, metric_label, statement_type, COUNT(*) as cnt
        FROM metric_records
        WHERE company_name IN ('比亚迪', '华能水电')
          AND statement_type != 'unknown'
        GROUP BY company_name, metric_name, metric_label
        HAVING COUNT(DISTINCT statement_type) > 1
        LIMIT 5
        """
    ).fetchall()

if rows:
    print(f"  找到 {len(rows)} 个同时含合并/母公司口径的指标：")
    for r in rows:
        print(f"    {r[0]} | {r[1]} | {r[2]} | 口径种类={r[3]} | 记录数={r[4]}")
    # 查询验证：应优先返回 consolidated
    test_company, test_metric = rows[0][0], rows[0][1]
    result = repo.find_best_match(
        MetricQuery(
            company_name=test_company,
            metric_name=test_metric,
            time_scope="latest",
            metric_label_raw=rows[0][2],
        )
    )
    if result and result.statement_type == "consolidated":
        print(f"\n  [OK] {test_company} {test_metric} latest → consolidated（优先级正确）")
    elif result:
        print(f"\n  [WARN] {test_company} {test_metric} latest → {result.statement_type}（期望 consolidated）")
        all_pass = False
    else:
        print(f"\n  [FAIL] {test_company} {test_metric} latest → 未命中")
        all_pass = False
else:
    print("  未找到同时含合并/母公司口径的指标（可能全部 unknown，需检查 _infer_statement_type）")

print("\n" + "=" * 70)
print(f"验证结果: {'全部通过 ✅' if all_pass else '存在问题 ⚠️'}")
print("=" * 70)
