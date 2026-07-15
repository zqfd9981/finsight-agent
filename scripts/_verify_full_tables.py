"""用比亚迪 + 华能水电的全量真实表格验证修复效果。

对比修复前后：
1. 跑修复后的 TableExtractor 提取两家公司所有表格
2. 检查 time_scope 是否归一化（不再有 '2024年度' / '2024 年度' / 数值字符串 等异常值）
3. 检查 period_end 是否按列赋值（2023年列的 period_end=2023-12-31）
4. 检查净利润的 time_scope 和 value 对齐是否正确
"""
import sys
import json
from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT))

from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.config.settings import load_settings

settings = load_settings()
normalizer = MetricNormalizer(aliases_path=settings.structured_data.aliases_path)

companies = [
    ("比亚迪", "002594_比亚迪"),
    ("华能水电", "600025_华能水电"),
]

for display_name, dir_prefix in companies:
    print(f"\n{'='*70}")
    print(f"公司: {display_name}")
    print(f"{'='*70}")

    structured_dir = Path(REPO_ROOT / "var/data/parsed_filings")
    candidates = list(structured_dir.glob(f"{dir_prefix}*__structured"))
    if not candidates:
        print(f"  找不到 {dir_prefix}*__structured 目录")
        continue

    tables_file = candidates[0] / "tables.jsonl"
    if not tables_file.exists():
        print(f"  找不到 tables.jsonl")
        continue

    company_code = dir_prefix.split("_")[0]
    extractor = TableExtractor(
        company_code=company_code,
        company_name=display_name,
        source_document_id=f"{dir_prefix}__structured",
        normalizer=normalizer,
    )

    print(f"  提取中...")
    records = extractor.extract_from_tables_file(tables_file)
    print(f"  共提取 {len(records)} 条记录")

    # 1. time_scope 分布
    print(f"\n  --- time_scope 分布 ---")
    ts_counter = Counter(r.time_scope for r in records)
    for ts, cnt in ts_counter.most_common(15):
        print(f"    {ts!r}: {cnt}")

    # 2. period_end 分布
    print(f"\n  --- period_end 分布 ---")
    pe_counter = Counter(r.period_end for r in records)
    for pe, cnt in pe_counter.most_common(10):
        print(f"    {pe!r}: {cnt}")

    # 3. 检查异常 time_scope（数值字符串等）
    abnormal_ts = [ts for ts in ts_counter if any(c.isdigit() for c in ts) and "年" not in ts and "余额" not in ts and "期" not in ts]
    if abnormal_ts:
        print(f"\n  !! 异常 time_scope（数值字符串）: {abnormal_ts}")
    else:
        print(f"\n  ✅ 无异常 time_scope")

    # 4. 净利润相关记录
    print(f"\n  --- 净利润相关记录 ---")
    for r in records:
        if "profit" in r.metric_name and "net" in r.metric_name:
            print(f"    {r.metric_label} ({r.metric_name}) | time_scope={r.time_scope!r} | period_end={r.period_end} | value={r.value}")

    # 5. 验证 2024年 vs 2023年 值对比
    print(f"\n  --- 同一指标 2024年 vs 2023年 值对比 ---")
    from collections import defaultdict
    by_metric = defaultdict(dict)
    for r in records:
        if r.time_scope in ("2024年", "2023年"):
            by_metric[r.metric_label][r.time_scope] = r.value
    for label, ts_map in list(by_metric.items())[:10]:
        v2024 = ts_map.get("2024年")
        v2023 = ts_map.get("2023年")
        if v2024 and v2023:
            try:
                v24 = float(v2024.replace(",", "").replace("(", "-").replace(")", ""))
                v23 = float(v2023.replace(",", "").replace("(", "-").replace(")", ""))
                ratio = v24 / v23 if v23 != 0 else 0
                status = "✅" if 0.1 < ratio < 10 else "⚠️"
                print(f"    {status} {label}: 2024={v2024}, 2023={v2023}, ratio={ratio:.2f}")
            except Exception:
                print(f"    ? {label}: 2024={v2024}, 2023={v2023}")
