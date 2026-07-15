"""看下TCL中环structured表格的实际内容（看前面几个大表和后面的明细表）。"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"

tables = []
with (doc_dir / "tables.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            tables.append(json.loads(line))

# 按页码排序，看几个代表性的表
sorted_tables = sorted(tables, key=lambda t: t.get("page_start", 0))

# 看前3个大表（应该是三表）和后3个明细表
interesting_indices = [1, 5, 8, 11, 13, 17, 28, 30, 40, 47, 48]
for i in interesting_indices:
    if i >= len(sorted_tables):
        continue
    tbl = sorted_tables[i]
    page = tbl.get("page_start", 0)
    md = tbl.get("table_markdown", "")
    rows = md.count("\n") + 1
    print(f"\n=== [{i}] p{page} ({rows}行) ===")
    # 只打印前8行
    for line in md.split("\n")[:8]:
        print(f"  {line[:120]}")
    if rows > 8:
        print(f"  ... ({rows - 8} more rows)")
