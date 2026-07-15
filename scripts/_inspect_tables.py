"""检查比亚迪 tables.jsonl 的字段结构和 caption 样本。"""
import json
from collections import Counter
from pathlib import Path

TABLES = Path(r"c:\D\大模型课程\openspec测试项目\var\data\parsed_filings\002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2\tables.jsonl")

tables = []
with TABLES.open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            tables.append(json.loads(line))

print(f"总表数: {len(tables)}")
print(f"字段: {list(tables[0].keys())}")
print()

# 统计 caption 为空的情况
empty_caption = sum(1 for t in tables if not (t.get("caption") or "").strip())
print(f"caption 为空: {empty_caption}/{len(tables)}")
print()

# 看前 30 张表的 caption
print("=== 前 30 张表 caption/page_start ===")
for i, t in enumerate(tables[:30]):
    cap = (t.get("caption") or "")[:80]
    page = t.get("page_start", 0)
    ttype = (t.get("table_type") or "")[:40]
    print(f"  {i+1:3d}. p{page:3d} | type={ttype:40s} | caption={cap}")

# 统计含三表关键词的 caption
print()
print("=== 含三表关键词的表 ===")
stmt_kws = ["资产负债表", "利润表", "现金流量表", "所有者权益变动表", "股东权益变动表"]
for i, t in enumerate(tables):
    cap = t.get("caption") or ""
    if any(kw in cap for kw in stmt_kws):
        print(f"  {i+1:3d}. p{t.get('page_start',0):3d} | caption={cap[:100]}")
