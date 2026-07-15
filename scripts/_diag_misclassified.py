"""查看被误判为A类的明细表（p147/p150/p158附近）。"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"

tables = []
with (doc_dir / "tables.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            tables.append(json.loads(line))

# 看p147/p150/p158的表
for tbl in tables:
    page = tbl.get("page_start", 0)
    if page in (147, 150, 158):
        md = tbl.get("table_markdown", "")
        rows = md.count("\n") + 1
        print(f"\n=== p{page} ({rows}行) ===")
        print(md[:500])
        print("---")
