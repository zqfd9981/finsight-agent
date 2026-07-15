"""查看 p87-104 之间所有1行表的实际内容。"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"

tables = []
with (doc_dir / "tables.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            tables.append(json.loads(line))

# 看p87-104之间所有表，包括1行的
print("=== p87-104 之间所有表 ===")
for i, tbl in enumerate(sorted(tables, key=lambda t: t.get("page_start", 0)), 1):
    page = tbl.get("page_start", 0)
    if page < 86 or page > 104:
        continue
    md = tbl.get("table_markdown", "")
    rows = md.count("\n") + 1
    text = tbl.get("table_text", "")[:100]
    section = " > ".join(tbl.get("section_path", []))[:30]
    print(f"\n[{i}] p{page} ({rows}行) | section: {section}")
    print(f"  markdown 完整内容:")
    print(f"  {md}")
    print(f"  text预览: {text}")
