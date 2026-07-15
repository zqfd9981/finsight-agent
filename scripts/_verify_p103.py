"""检查 p103-104 的 elements，看权益变动表结尾是否在 elements 里。"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
doc_dir = REPO_ROOT / "var" / "data" / "parsed_filings" / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"

elements = []
with (doc_dir / "elements.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            elements.append(json.loads(line))

# 看 p103-104 的所有 elements
print("=== p103-104 的 elements ===")
for elem in elements:
    page = elem.get("page_start", 0)
    if page in (103, 104):
        etype = elem.get("element_type", "")
        text = elem.get("text", "")[:150]
        print(f"  p{page} [{etype:>10}] {text}")

# 也看下 p103 的 table 完整内容
print("\n=== p103 table 完整内容 ===")
with (doc_dir / "tables.jsonl").open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            tbl = json.loads(line)
            if tbl.get("page_start") == 103:
                md = tbl.get("table_markdown", "")
                rows = md.count("\n") + 1
                print(f"  行数: {rows}")
                print(f"  最后8行:")
                for l in md.strip().split("\n")[-8:]:
                    print(f"    {l[:120]}")
