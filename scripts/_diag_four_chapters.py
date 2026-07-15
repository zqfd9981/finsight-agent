"""找出严格保留 4 个区间的年报，并查看详情。"""
import json
from collections import Counter

data = json.loads(open("var/data/page_filter/annual_2025_pages.json", encoding="utf-8").read())

# 统计每份文档的 kept_ranges 数量分布
range_count_dist = Counter()
docs_by_ranges = {3: [], 4: []}
reason_set = Counter()

for company_key, doc in data["documents"].items():
    n = len(doc["kept_ranges"])
    range_count_dist[n] += 1
    if n in (3, 4):
        reasons = tuple(sorted(r["reason"] for r in doc["kept_ranges"]))
        reason_set[reasons] += 1
        docs_by_ranges[n].append((company_key, doc, reasons))

print("=== kept_ranges 数量分布 ===")
for n, cnt in sorted(range_count_dist.items()):
    print(f"  {n} 个区间: {cnt} 份")

print("\n=== 3 个区间文档的区间组合 TOP10 ===")
reason_3 = Counter()
for company_key, doc, reasons in docs_by_ranges[3]:
    reason_3[reasons] += 1
for reasons, cnt in reason_3.most_common(10):
    print(f"  {cnt} 份 → {reasons}")

print("\n=== 4 个区间文档的区间组合 ===")
reason_4 = Counter()
for company_key, doc, reasons in docs_by_ranges[4]:
    reason_4[reasons] += 1
for reasons, cnt in reason_4.most_common():
    print(f"  {cnt} 份 → {reasons}")

# 看下"最标准"的4章节：财务指标 + MD&A + 重要事项 + 财务报告（任意形式）
print("\n" + "=" * 80)
print("=== 4 区间文档逐份详情 ===")
print("=" * 80)
for company_key, doc, reasons in docs_by_ranges[4]:
    has_financial_metrics = any("财务指标" in r for r in reasons)
    has_mda = any("MD&A" in r for r in reasons)
    has_important = any("重要事项" in r for r in reasons)
    has_fin_report = any("财务报告" in r for r in reasons)
    score = sum([has_financial_metrics, has_mda, has_important, has_fin_report])
    if score == 4:
        print(f"\n>>> {company_key} (完整 4 类型) | 总{doc['total_pages']}p → 保留{doc['kept_page_count']}p ({doc['compression_ratio']*100:.0f}%)")
        for r in doc["kept_ranges"]:
            print(f"    p{r['start']:>3}-{r['end']:<3} ({r['page_count']:>3}p) | {r['title']} | {r['reason']}")

# 找一份3区间中最常见的，看看缺什么
print("\n" + "=" * 80)
print("=== 3 区间最常见的组合示例 ===")
print("=" * 80)
most_common_3 = reason_3.most_common(1)[0]
print(f"最常见组合: {most_common_3[1]} 份 → {most_common_3[0]}")
# 找该组合第一份
for company_key, doc, reasons in docs_by_ranges[3]:
    if reasons == most_common_3[0]:
        print(f"\n示例: {company_key} | 总{doc['total_pages']}p → 保留{doc['kept_page_count']}p ({doc['compression_ratio']*100:.0f}%)")
        print(f"所有章节:")
        for ch in doc["chapters"]:
            print(f"  p{ch['start']:>3}-{ch['end']:<3} ({ch['page_count']:>3}p) | {ch['title']}")
        print(f"保留区间:")
        for r in doc["kept_ranges"]:
            print(f"  p{r['start']:>3}-{r['end']:<3} ({r['page_count']:>3}p) | {r['title']} | {r['reason']}")
        break
