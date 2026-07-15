"""检查格力/平安/恒瑞的 tables.jsonl（正确路径），看三表是否被 MinerU 解析为表格。"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# 正确路径：不带 __structured 后缀
TARGETS = [
    ("000651", "格力电器", "000651_格力电器__annual__2025__000651_格力电器_annual_report_2025_20250428"),
    ("000001", "平安银行", "000001_平安银行__annual__2025__000001_平安银行_annual_report_2025_20250315"),
    ("600276", "恒瑞医药", "600276_恒瑞医药__annual__2025__600276_恒瑞医药_annual_report_2025_20250331"),
    ("601600", "中国铝业", "601600_中国铝业__annual__2025__601600_中国铝业_annual_report_2025_20250327"),
]

for code, name, dir_name in TARGETS:
    struct_dir = REPO / f"var/data/parsed_filings/{dir_name}"
    tables_path = struct_dir / "tables.jsonl"
    elements_path = struct_dir / "elements.jsonl"

    print(f"\n{'='*80}")
    print(f"{code} {name}")
    print(f"{'='*80}")

    if not tables_path.exists():
        print(f"  tables.jsonl 不存在: {tables_path}")
        continue

    tables = []
    with tables_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tables.append(json.loads(line))

    print(f"  tables.jsonl: {len(tables)} 张表")

    # 找含三表关键词的表（caption 或 table_markdown 前 200 字符）
    print(f"\n  含三表关键词的表:")
    found_stmt = False
    for i, t in enumerate(tables):
        caption = t.get("caption") or t.get("table_caption") or ""
        markdown = (t.get("table_markdown") or "")[:300]
        html = (t.get("table_html") or "")[:300]
        combined = caption + markdown + html
        keywords = []
        if "资产负债表" in combined or "资产总计" in combined or "负债合计" in combined:
            keywords.append("BS")
        if "利润表" in combined or "营业总收入" in combined or "营业收入" in combined:
            keywords.append("IS")
        if "现金流量表" in combined or "经营活动产生的现金流量" in combined:
            keywords.append("CF")
        if keywords:
            page = t.get("page_start") or t.get("page_idx") or "?"
            print(f"    [{i+1:>3}] p{page} | {','.join(keywords)} | caption={caption[:50]}")
            found_stmt = True
    if not found_stmt:
        print(f"    （无）")

    # 前 10 张表的 caption
    print(f"\n  前 10 张表:")
    for i, t in enumerate(tables[:10]):
        caption = t.get("caption") or t.get("table_caption") or ""
        page = t.get("page_start") or t.get("page_idx") or "?"
        rows = (t.get("table_markdown") or "").count("\n")
        print(f"    [{i+1:>3}] p{page} ({rows}行) | {caption[:60]}")
