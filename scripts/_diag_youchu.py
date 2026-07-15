"""诊断邮储银行章节提取情况。"""
import json

data = json.loads(open("var/data/page_filter/annual_2025_pages.json", encoding="utf-8").read())
doc = data["documents"]["601658_邮储银行"]

print(f"总页数: {doc['total_pages']}")
print(f"source: {doc['source']}")
print(f"保留页数: {doc['kept_page_count']}")
print(f"\n=== 所有章节 ===")
for ch in doc["chapters"]:
    print(f"  p{ch['start']:>3}-{ch['end']:<3} ({ch['page_count']:>3}p) | {ch['title']}")

print(f"\n=== 保留的区间 ===")
for r in doc["kept_ranges"]:
    print(f"  p{r['start']:>3}-{r['end']:<3} ({r['page_count']:>3}p) | {r['title']} | {r['reason']}")
