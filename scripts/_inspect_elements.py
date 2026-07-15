"""检查比亚迪 elements.jsonl 中的报表标题页码。"""
import json
from pathlib import Path

ELEMS = Path(r"c:\D\大模型课程\openspec测试项目\var\data\parsed_filings\002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2\elements.jsonl")

elements = []
with ELEMS.open(encoding="utf-8") as f:
    for line in f:
        if line.strip():
            elements.append(json.loads(line))

print(f"总元素数: {len(elements)}")
print(f"字段: {list(elements[0].keys())}")
print()

# 找含报表关键词的标题
stmt_kws = ["资产负债表", "利润表", "现金流量表", "所有者权益变动表", "股东权益变动表", "主要项目注释"]
print("=== 报表标题（按 page_start 排序）===")
seen_pages = set()
for el in elements:
    text = str(el.get("text") or "").strip()
    page = int(el.get("page_start") or 0)
    if not text:
        continue
    if any(kw in text for kw in stmt_kws) and page not in seen_pages:
        seen_pages.add(page)
        eltype = el.get("element_type") or el.get("type") or ""
        print(f"  p{page:3d} | type={eltype:20s} | text={text[:100]}")

# 找"财务报表主要项目注释"开始位置
print()
print("=== 注释区起点 ===")
for el in elements:
    text = str(el.get("text") or "").strip()
    page = int(el.get("page_start") or 0)
    if "财务报表主要项目注释" in text or "主要项目注释" in text:
        eltype = el.get("element_type") or el.get("type") or ""
        print(f"  p{page:3d} | type={eltype:20s} | text={text[:100]}")
        break

# 找 page_start 范围
pages = sorted({int(el.get("page_start") or 0) for el in elements})
print()
print(f"=== 页码范围 ===")
print(f"  min={pages[0]}, max={pages[-1]}, count={len(pages)}")
print(f"  前10页: {pages[:10]}")
print(f"  后10页: {pages[-10:]}")
