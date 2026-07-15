"""统计TCL中环structured路径下所有表格的caption和section_path分布。"""
import json
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parents[1]
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"

tables = []
with (doc_dir / "tables.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            tables.append(json.loads(line))

print(f"总 tables: {len(tables)}")
print(f"\n=== 所有表格（按页码排序）===")
for i, tbl in enumerate(sorted(tables, key=lambda t: t.get("page_start", 0)), 1):
    caption = tbl.get("caption_text", "")[:50]
    section = " > ".join(tbl.get("section_path", []))[:40]
    page = tbl.get("page_start", 0)
    rows = tbl.get("table_markdown", "").count("\n") + 1
    print(f"  [{i:>2}] p{page:>3} ({rows:>2}行) | {caption:<30} | {section}")
