"""三一重工：从 MinerU 缓存重建 tables.jsonl（含注释区），跑 TableExtractor 入库。

缓存页码映射（通过文本标记推断）：
  Cache A (27页): page_idx 0-17 = p90-p107（三表），page_idx 18-26 = p131-p139（注释区前段）
  Cache B (71页): page_idx 0-70 = p173-p243（注释区后段 + 母公司注释）

缺失页码（MinerU 未解析）：p108-p130, p140-p172（约56页注释区中段）
→ 先用可用页码验证代码修复效果，缺失页码后续可补调 MinerU API。
"""
import sys
import json
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))

from dataclasses import asdict
from finsight_agent.infra.document_parsers.mineru_parser import _build_artifact
from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.infra.llm.client import LlmClient

DB_PATH = REPO / "var/data/structured_data/metrics.db"
CACHE_ROOT = REPO / "var/data/_mineru_cache"
PDF_PATH = REPO / "var/data/raw_filings/600031_三一重工/annual/2025/600031_三一重工_annual_report_2025_20250418.pdf"
STRUCT_DIR = REPO / "var/data/parsed_filings/600031_三一重工__annual__2025__600031_三一重工_annual_report_2025_20250418__structured_v2"
DOC_ID = "600031_三一重工__annual__2025__600031_三一重工_annual_report_2025_20250418__structured_v2"

print("=" * 80)
print("三一重工 (600031) 从 MinerU 缓存重建")
print("=" * 80)

# 1. 读取所有缓存 content_list.json，建立 page_idx → 原始页码映射
print("\n1. 建立缓存页码映射...")

# 找三一的所有 content_list.json
cache_files = []
for d in sorted(CACHE_ROOT.iterdir()):
    if d.is_dir() and "600031" in d.name:
        for cf in d.rglob("*content_list.json"):
            cache_files.append(cf)

print(f"   找到 {len(cache_files)} 个 content_list.json")

# 已知文本标记（text → 原始页码）
MARKERS = {
    "合并资产负债表": 90,
    "母公司资产负债表": 92,
    "合并利润表": 94,
    "母公司利润表": 96,
    "合并现金流量表": 97,
    "母公司现金流量表": 99,
    "合并所有者权益变动表": 101,
    "母公司所有者权益变动表": 104,
    "七、 合并财务报表项目注释": 131,
    "十九、 母公司财务报表主要项目注释": 243,
}

# 为每个缓存建立映射
page_to_elements: dict[int, list[dict]] = {}

for cf in cache_files:
    raw = json.loads(cf.read_text(encoding="utf-8"))
    # 归一化为 list[list[dict]]
    if raw and isinstance(raw[0], list):
        pages = raw
    else:
        by_page = {}
        for item in raw:
            if isinstance(item, dict):
                p = item.get("page_idx", 0)
                by_page.setdefault(p, []).append(item)
        if not by_page:
            continue
        max_p = max(by_page.keys())
        pages = [by_page.get(i, []) for i in range(max_p + 1)]

    # 找标记，推断页码映射
    markers_found = {}  # page_idx → original_page
    for pidx, page_items in enumerate(pages):
        for item in page_items:
            if not isinstance(item, dict):
                continue
            text = ""
            t = item.get("text")
            if isinstance(t, str):
                text = t
            elif isinstance(t, list):
                text = " ".join(str(x) for x in t)
            for marker, orig_page in MARKERS.items():
                if marker in text and len(text) < 40:
                    markers_found[pidx] = orig_page

    if not markers_found:
        continue

    # 推断连续区间
    # 按 page_idx 排序，找连续段
    sorted_markers = sorted(markers_found.items())
    # 计算每段的偏移
    segments = []  # [(start_pidx, end_pidx, offset)]
    seg_start = sorted_markers[0][0]
    seg_offset = sorted_markers[0][1] - sorted_markers[0][0]
    prev_pidx = sorted_markers[0][0]

    for pidx, orig_page in sorted_markers[1:]:
        expected_offset = orig_page - pidx
        if expected_offset != seg_offset:
            # 新段
            segments.append((seg_start, prev_pidx, seg_offset))
            seg_start = pidx
            seg_offset = expected_offset
        prev_pidx = pidx
    segments.append((seg_start, prev_pidx, seg_offset))

    # 用每段的偏移映射所有 page_idx
    for pidx in range(len(pages)):
        for seg_start, seg_end, offset in segments:
            # 找最近的段
            if seg_start <= pidx <= seg_end:
                orig_page = pidx + offset
                if orig_page > 0:
                    page_to_elements[orig_page] = pages[pidx]
                break
            elif pidx < seg_start:
                # 在第一个段之前，用第一个段的偏移
                orig_page = pidx + offset
                if orig_page > 0:
                    page_to_elements[orig_page] = pages[pidx]
                break

    print(f"   {cf.name[:30]}..  pages={len(pages)}  markers={len(markers_found)}  segments={len(segments)}")

available_pages = sorted(page_to_elements.keys())
# 只保留三表区(p90-p107) + 注释区(p131-p243)，排除 Cache 1 的不可靠 RAG 页码映射
available_pages = [p for p in available_pages if (90 <= p <= 107) or (131 <= p <= 243)]
print(f"   可用页码: p{available_pages[0]}-p{available_pages[-1]}, 共 {len(available_pages)} 页")
# 检查缺失页码
all_needed = set(range(90, 108)) | set(range(131, 244))
missing = sorted(all_needed - set(available_pages))
if missing:
    print(f"   缺失页码: {len(missing)} 页 (MinerU 未解析)")
    print(f"   缺失范围: p{missing[0]}-p{missing[-1]}")

# 2. 构建 content_list + page_filter
page_filter = set(available_pages)
content_list = [page_to_elements[p] for p in available_pages]

print(f"\n2. 构建 content_list: {len(content_list)} 页, page_filter: {len(page_filter)} 页")

# 3. 调用 _build_artifact 重建
print(f"\n3. 调用 _build_artifact 重建 tables.jsonl + elements.jsonl...")
artifact = _build_artifact(
    pdf_path=PDF_PATH,
    content_list=content_list,
    full_md="",
    page_filter=page_filter,
)

# 4. 保存到 structured_v2 目录
STRUCT_DIR.mkdir(parents=True, exist_ok=True)
tables_jsonl = STRUCT_DIR / "tables.jsonl"
elements_jsonl = STRUCT_DIR / "elements.jsonl"

with tables_jsonl.open("w", encoding="utf-8") as f:
    for t in artifact.tables:
        f.write(json.dumps(asdict(t), ensure_ascii=False) + "\n")
with elements_jsonl.open("w", encoding="utf-8") as f:
    for e in artifact.elements:
        f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")

has_html = sum(1 for t in artifact.tables if (t.table_html or "").strip())
print(f"   tables.jsonl: {len(artifact.tables)} 张表, {has_html} 张含 table_html ({has_html*100//len(artifact.tables) if artifact.tables else 0}%)")
print(f"   elements.jsonl: {len(artifact.elements)} 个元素")

# 5. 删除旧 SQLite 记录
conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.execute("DELETE FROM metric_records WHERE company_code = '600031'")
deleted = cur.rowcount
conn.commit()
conn.close()
print(f"\n4. 删除旧 SQLite 记录: {deleted} 条")

# 6. 跑 TableExtractor
print(f"\n5. 跑 TableExtractor...")
llm_client = LlmClient()
normalizer = MetricNormalizer(
    aliases_path=REPO / "var/data/structured_data/metric_aliases.json",
    llm_client=llm_client,
)
extractor = TableExtractor(
    company_code="600031",
    company_name="三一重工",
    source_document_id=DOC_ID,
    normalizer=normalizer,
    llm_client=llm_client,
)
records = extractor.extract_from_tables_file(tables_jsonl)
print(f"   提取 {len(records)} 条记录")

# 7. 统计
from collections import Counter
ss_counts = Counter(r.source_section for r in records)
st_counts = Counter(r.statement_type for r in records)
print(f"\n6. source_section 分布: {dict(ss_counts)}")
print(f"   statement_type 分布: {dict(st_counts)}")

# 8. 入库
print(f"\n7. 入库 SQLite...")
repo = MetricRepository(sqlite_path=DB_PATH)
repo.save_records_for_company("600031", records)
print(f"   入库完成")

print(f"\n完成！")
