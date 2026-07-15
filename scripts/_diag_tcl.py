"""查看TCL中环年报的章节提取详情。"""
import json

data = json.loads(open("var/data/page_filter/annual_2025_pages.json", encoding="utf-8").read())

# 找TCL中环的key
tcl_keys = [k for k in data["documents"] if "TCL" in k or "中环" in k]
print(f"找到TCL中环相关文档: {tcl_keys}")

for company_key in tcl_keys:
    doc = data["documents"][company_key]
    print(f"\n{'=' * 80}")
    print(f"公司: {company_key}")
    print(f"PDF: {doc['pdf_path']}")
    print(f"总页数: {doc['total_pages']}")
    print(f"source: {doc['source']}")
    print(f"保留页数: {doc['kept_page_count']}")
    print(f"压缩比: {doc['compression_ratio'] * 100:.1f}%")

    print(f"\n=== 财务报告章节(p82+)的子章节 ===")
    for ch in doc["chapters"]:
        if ch["start"] >= 82:
            depth_mark = "  " * ch.get("depth", 0)
            print(f"  {depth_mark}p{ch['start']:>3}-{ch['end']:<3} ({ch['page_count']:>3}p) | {ch['title']}")

    print(f"\n=== 保留的区间 ===")
    for r in doc["kept_ranges"]:
        ptype = r.get("processing_type", "?")
        print(f"  [{ptype:>10}] p{r['start']:>3}-{r['end']:<3} ({r['page_count']:>3}p) | {r['title']} | {r['reason']}")
