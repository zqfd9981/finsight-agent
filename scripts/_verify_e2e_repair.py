"""端到端验证：跨页修复 + 指标提取全流程。

流程：
  1. 读取现有 tables.jsonl
  2. 检测截断（find_truncated_tables）
  3. 修复 p103（repair_truncated_table，调用 MinerU API）
  4. 应用修复（apply_repair_to_tables）
  5. 提取指标（TableExtractor）
  6. 验证 metric_records 包含权益变动表的"四、本期期末余额"等指标
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from finsight_agent.capabilities.structured_data.cross_page_repair import (
    apply_repair_to_tables,
    find_truncated_tables,
    repair_truncated_table,
)
from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor
from finsight_agent.infra.document_parsers.mineru_parser import MineruDocumentParser

DOC_DIR = (
    REPO_ROOT
    / "var"
    / "data"
    / "parsed_filings"
    / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"
)
TABLES_JSONL = DOC_DIR / "tables.jsonl"
PDF_PATH = (
    REPO_ROOT
    / "var"
    / "data"
    / "raw_filings"
    / "002129_TCL中环"
    / "annual"
    / "2025"
    / "002129_TCL中环_annual_report_2025_20250426.pdf"
)

# 1. 读取现有 tables.jsonl
print("=== 步骤1: 读取 tables.jsonl ===")
with TABLES_JSONL.open(encoding="utf-8") as f:
    raw_tables = [json.loads(l) for l in f if l.strip()]
print(f"  共 {len(raw_tables)} 张表")

# 2. 检测截断
print("\n=== 步骤2: 检测截断表 ===")
truncated = find_truncated_tables(raw_tables)
print(f"  检测到 {len(truncated)} 张截断表:")
for idx, check in truncated:
    print(f"    [{idx}] p{check.page_start} ({check.row_count}行) {check.table_type} 缺:{check.missing_rows}")

# 3. 修复（调用 MinerU API）
print("\n=== 步骤3: 跨页修复（调用 MinerU API）===")
mineru = MineruDocumentParser(cache_dir=REPO_ROOT / "var" / "data" / "_mineru_cache")
repair_results = []
repaired_count = 0
for idx, check in truncated:
    print(f"\n  修复 [{idx}] p{check.page_start} {check.table_type} ...", flush=True)
    t0 = time.time()
    repair = repair_truncated_table(
        pdf_path=PDF_PATH,
        table_check=check,
        cache_dir=REPO_ROOT / "var" / "data" / "_merge_tmp",
        mineru_parser=mineru,
    )
    elapsed = time.time() - t0
    print(f"    repaired={repair.repaired} rows={repair.new_row_count} pages={repair.merged_pages} ({elapsed:.1f}s)")
    print(f"    reason: {repair.reason[:80]}")
    if repair.repaired:
        repaired_count += 1
        for row in check.missing_rows:
            found = row in repair.new_markdown
            print(f"    {'✓' if found else '✗'} 包含 '{row}'")
    repair_results.append(repair)

print(f"\n  修复完成: {repaired_count}/{len(truncated)} 张成功")

# 4. 应用修复到 tables（生成新列表，不写回原文件）
print("\n=== 步骤4: 应用修复到 tables ===")
if repaired_count > 0:
    repaired_tables = apply_repair_to_tables(raw_tables, repair_results)
    # 写到临时文件给 TableExtractor 用
    tmp_tables = DOC_DIR / "tables_repaired.jsonl"
    with tmp_tables.open("w", encoding="utf-8") as f:
        for tbl in repaired_tables:
            f.write(json.dumps(tbl, ensure_ascii=False) + "\n")
    print(f"  修复后的 tables 写到: {tmp_tables.name}")
    # 统计修复前后 p103 表的行数变化
    for idx, check in truncated:
        old_rows = raw_tables[idx].get("table_markdown", "").count("\n") + 1
        new_rows = repaired_tables[idx].get("table_markdown", "").count("\n") + 1
        print(f"    [{idx}] p{check.page_start} {check.table_type}: {old_rows}行 → {new_rows}行")
else:
    tmp_tables = TABLES_JSONL
    print("  无修复，用原 tables.jsonl")

# 5. 提取指标
print("\n=== 步骤5: 提取三表指标 ===")
extractor = TableExtractor(
    company_code="002129",
    company_name="TCL中环",
    source_document_id="002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured",
)
metric_records = extractor.extract_from_tables_file(tmp_tables)
print(f"\n  共提取 {len(metric_records)} 条 MetricRecord")

# 6. 验证：按表类型统计指标
print("\n=== 步骤6: 验证指标分布 ===")
# 通过 source_caption 和 metric_name 推断表类型
equity_keywords = ["期末余额", "期初余额", "本期期末余额", "本年期初余额", "所有者权益内部结转"]
income_keywords = ["营业收入", "营业成本", "净利润", "每股收益"]
cashflow_keywords = ["经营活动", "投资活动", "筹资活动", "现金流量"]
balance_keywords = ["资产总计", "负债合计", "流动资产", "非流动资产"]

equity_count = 0
income_count = 0
cashflow_count = 0
balance_count = 0
other_count = 0
for r in metric_records:
    name = r.metric_name
    if any(kw in name for kw in equity_keywords):
        equity_count += 1
    elif any(kw in name for kw in income_keywords):
        income_count += 1
    elif any(kw in name for kw in cashflow_keywords):
        cashflow_count += 1
    elif any(kw in name for kw in balance_keywords):
        balance_count += 1
    else:
        other_count += 1

print(f"  权益变动表相关指标: {equity_count}")
print(f"  利润表相关指标:     {income_count}")
print(f"  现金流量表相关指标: {cashflow_count}")
print(f"  资产负债表相关指标: {balance_count}")
print(f"  其他:               {other_count}")

# 7. 重点验证 p103 修复后的权益变动表是否贡献了指标
print("\n=== 步骤7: 验证 p103 修复后的权益变动表指标 ===")
p103_records = [r for r in metric_records if "p103" in r.source_table_id or "_repaired" in r.source_table_id]
# 也检查是否有"四、本期期末余额"相关指标
final_balance_records = [r for r in metric_records if "本期期末余额" in r.metric_name or "期末余额" in r.metric_name]
print(f"  含'期末余额'的指标: {len(final_balance_records)}")
if final_balance_records:
    print(f"  示例:")
    for r in final_balance_records[:5]:
        print(f"    {r.metric_name} | {r.time_scope} | {r.value[:30] if r.value else ''}")

# 8. 清理临时文件
if tmp_tables != TABLES_JSONL and tmp_tables.exists():
    tmp_tables.unlink()
    print(f"\n  清理临时文件: {tmp_tables.name}")

print("\n=== 端到端验证完成 ===")
print(f"  截断检测: {len(truncated)} 张")
print(f"  修复成功: {repaired_count} 张")
print(f"  指标提取: {len(metric_records)} 条")
