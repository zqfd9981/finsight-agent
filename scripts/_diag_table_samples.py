"""看比亚迪和华能水电的真实表格样本，理解表头结构。"""
import json
from pathlib import Path

REPO_ROOT = Path(".").resolve()

companies = [
    ("比亚迪", "002594_比亚迪"),
    ("华能水电", "600025_华能水电"),
]

for display_name, dir_prefix in companies:
    print(f"\n{'='*70}")
    print(f"公司: {display_name}")
    print(f"{'='*70}")

    # 找 structured 目录
    structured_dir = Path(REPO_ROOT / "var/data/parsed_filings")
    candidates = list(structured_dir.glob(f"{dir_prefix}*__structured"))
    if not candidates:
        print(f"  找不到 {dir_prefix}*__structured 目录")
        continue

    tables_file = candidates[0] / "tables.jsonl"
    if not tables_file.exists():
        print(f"  找不到 tables.jsonl")
        continue

    # 读前 5 张表，看表头结构
    with tables_file.open(encoding="utf-8") as f:
        tables = [json.loads(line) for line in f if line.strip()]

    print(f"  共 {len(tables)} 张表")

    # 找含"净利润"的表
    profit_tables = []
    for i, tbl in enumerate(tables):
        md = tbl.get("table_markdown", "")
        if "净利润" in md and ("2024" in md or "2023" in md):
            profit_tables.append((i, tbl))

    print(f"  含'净利润'+年份的表: {len(profit_tables)} 张")

    # 展示前 3 张的表头和数据行
    for idx, (i, tbl) in enumerate(profit_tables[:3]):
        print(f"\n  --- 表 [{i}] p{tbl.get('page_start', '?')} caption={tbl.get('caption_text', '')[:40]} ---")
        md = tbl.get("table_markdown", "")
        lines = md.strip().split("\n")
        print(f"  共 {len(lines)} 行，前 6 行：")
        for j, line in enumerate(lines[:6]):
            print(f"    L{j}: {line[:120]}")
