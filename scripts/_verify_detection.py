"""轻量级验证：只检测截断，不调用 MinerU API。"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from finsight_agent.capabilities.structured_data.cross_page_repair import (
    check_table_completeness,
    find_truncated_tables,
    infer_table_type,
)

p = (
    REPO_ROOT
    / "var"
    / "data"
    / "parsed_filings"
    / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"
    / "tables.jsonl"
)
with p.open(encoding="utf-8") as f:
    tables = [json.loads(l) for l in f if l.strip()]

print(f"=== 共 {len(tables)} 张表 ===\n")
print("所有大表(>=5行)的类型推断和完整性：")
for idx, t in enumerate(tables):
    md = t.get("table_markdown") or ""
    page = t.get("page_start", 0)
    rows = md.count("\n") + 1
    if rows < 5:
        continue
    ttype = infer_table_type(md)
    check = check_table_completeness(table_index=idx, table_markdown=md, page_start=page)
    status = "完整" if check.is_complete else "截断"
    miss = check.missing_rows if not check.is_complete else ""
    ttype_str = ttype if ttype else "非三表"
    print(f"  [{idx}] p{page} ({rows}行) 类型={ttype_str} {status} {miss}")

print()
truncated = find_truncated_tables(tables)
print(f"=== 检测到 {len(truncated)} 张截断表 ===")
for idx, check in truncated:
    print(f"  [{idx}] p{check.page_start} ({check.row_count}行) {check.table_type}")
    print(f"    缺失: {check.missing_rows}")
