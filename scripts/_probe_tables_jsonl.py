"""检查格力和平安的 structured 目录 tables.jsonl，看三表是否被 MinerU 解析出来。"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TARGETS = [
    ("000651", "格力电器", "000651_格力电器_annual_report_2025_20250428"),
    ("000001", "平安银行", "000001_平安银行_annual_report_2025_20250315"),
    ("600276", "恒瑞医药", "600276_恒瑞医药_annual_report_2025_20250331"),
]

for code, name, doc_stem in TARGETS:
    struct_dir = REPO / f"var/data/parsed_filings/{doc_stem}__structured"
    tables_path = struct_dir / "tables.jsonl"
    elements_path = struct_dir / "elements.jsonl"

    print(f"\n{'='*80}")
    print(f"{code} {name} | {struct_dir.name}")
    print(f"{'='*80}")

    if not tables_path.exists():
        print(f"  tables.jsonl 不存在")
        continue

    tables = []
    with tables_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tables.append(json.loads(line))

    print(f"  tables.jsonl: {len(tables)} 张表")
    print(f"  前 20 张表的 caption + page:")
    for i, t in enumerate(tables[:20]):
        caption = t.get("caption") or t.get("table_caption") or ""
        page = t.get("page_start") or t.get("page_idx") or "?"
        # 看是否含三表关键词
        is_bs = "资产负债表" in caption
        is_is = "利润表" in caption or "损益表" in caption
        is_cf = "现金流量表" in caption
        mark = " ★三表" if (is_bs or is_is or is_cf) else ""
        print(f"    [{i+1:>3}] p{page} | {caption[:70]}{mark}")

    # 找含三表关键词的表
    print(f"\n  含三表关键词的表:")
    found_stmt = False
    for i, t in enumerate(tables):
        caption = t.get("caption") or t.get("table_caption") or ""
        if any(kw in caption for kw in ("资产负债表", "利润表", "损益表", "现金流量表", "所有者权益变动表")):
            page = t.get("page_start") or t.get("page_idx") or "?"
            print(f"    [{i+1:>3}] p{page} | {caption[:70]} ★三表")
            found_stmt = True
    if not found_stmt:
        print(f"    （无）— 三表没被 MinerU 解析为 table，可能作为 text element")

    # 查 elements.jsonl 里是否有"资产负债表"等文本
    if elements_path.exists():
        print(f"\n  elements.jsonl 含三表关键词的文本行:")
        with elements_path.open(encoding="utf-8") as f:
            for line in f:
                el = json.loads(line)
                text = str(el.get("text") or "")
                if any(kw in text for kw in ("合并资产负债表", "合并利润表", "合并现金流量表")):
                    page = el.get("page_start") or "?"
                    print(f"    p{page} | {text[:80]}")
