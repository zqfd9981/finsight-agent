"""测试跨页修复全流程：p103-105 母公司权益变动表。"""
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from finsight_agent.capabilities.structured_data.cross_page_repair import (
    check_table_completeness,
    find_truncated_tables,
    merge_pages_to_single_pdf,
    repair_truncated_table,
)
from finsight_agent.infra.document_parsers.mineru_parser import MineruDocumentParser

# 1. 读取现有 tables.jsonl，找出截断表
import json
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"
tables_jsonl = doc_dir / "tables.jsonl"

raw_tables = []
with tables_jsonl.open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            raw_tables.append(json.loads(line))

print(f"=== 读取 {len(raw_tables)} 张表 ===\n")

# 2. 检测截断
truncated = find_truncated_tables(raw_tables)
print(f"=== 检测到 {len(truncated)} 张截断表 ===\n")
for idx, check in truncated:
    print(f"  table[{idx}] p{check.page_start} ({check.row_count}行) {check.table_type}")
    print(f"    缺失: {check.missing_rows}")
    print(f"    原因: {check.reason}")
    print()

if not truncated:
    print("没有截断表，退出")
    sys.exit(0)

# 3. 测试页面合并
pdf_path = REPO_ROOT / "var" / "data" / "raw_filings" / "002129_TCL中环" / "annual" / "2025" / "002129_TCL中环_annual_report_2025_20250426.pdf"
print(f"=== 测试页面合并: p103+p104+p105 ===")
temp_pdf = REPO_ROOT / "var" / "data" / "_merge_tmp" / "test_p103_105.pdf"
t0 = time.time()
merge_pages_to_single_pdf(pdf_path, [103, 104, 105], temp_pdf)
print(f"  合并完成: {temp_pdf.name} ({temp_pdf.stat().st_size} bytes, {time.time()-t0:.1f}s)")
print(f"  路径: {temp_pdf}")
print()

# 4. 用 MinerU 重解析
print(f"=== MinerU 重解析合并后的单页 PDF ===")
mineru = MineruDocumentParser(cache_dir=REPO_ROOT / "var" / "data" / "_mineru_cache")
t0 = time.time()
artifact = mineru.parse(temp_pdf)
print(f"  解析完成: {len(artifact.elements)} elements, {len(artifact.tables)} tables ({time.time()-t0:.1f}s)")
print()

# 5. 看重解析的 table 内容
print(f"=== 重解析的 table 内容 ===")
for i, tbl in enumerate(artifact.tables):
    md = str(tbl.table_markdown or "")
    rows = md.count("\n") + 1
    print(f"\n  table[{i}] p{tbl.page_start} ({rows}行)")
    print(f"  前3行: {md.split(chr(10))[:3]}")
    print(f"  后3行: {md.split(chr(10))[-3:]}")
    # 检查是否包含之前缺失的汇总行
    if "四、本期期末余额" in md:
        print(f"  ✓ 包含'四、本期期末余额'")

# 6. 跑完整修复流程
print(f"\n=== 完整修复流程 ===")
for idx, check in truncated:
    print(f"\n修复 table[{idx}] p{check.page_start} {check.table_type}")
    t0 = time.time()
    repair = repair_truncated_table(
        pdf_path=pdf_path,
        table_check=check,
        cache_dir=REPO_ROOT / "var" / "data" / "_merge_tmp",
        mineru_parser=mineru,
    )
    elapsed = time.time() - t0
    print(f"  repaired: {repair.repaired}")
    print(f"  new_markdown 行数: {repair.new_row_count}")
    print(f"  merged_pages: {repair.merged_pages}")
    print(f"  reason: {repair.reason}")
    print(f"  耗时: {elapsed:.1f}s")
    if repair.repaired:
        # 验证汇总行
        for row in check.missing_rows:
            if row in repair.new_markdown:
                print(f"  ✓ 包含 '{row}'")
            else:
                print(f"  ✗ 仍缺 '{row}'")
