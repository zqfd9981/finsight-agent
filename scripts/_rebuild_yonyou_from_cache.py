"""从 MinerU 缓存重建用友网络 tables.jsonl（带 table_html），跑 TableExtractor。

用 3ca8e475 缓存（113 页 = structured_pages 合计），不调 MinerU API。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"
for p in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from finsight_agent.infra.document_parsers.mineru_parser import (
    _build_artifact,
    _normalize_content_list,
)
from finsight_agent.capabilities.retrieval.parsed_storage import write_parsed_artifact
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor
from finsight_agent.infra.llm.client import LlmClient

# 1. 读缓存（3ca8e475 是 structured 路径，113 页对应 p85-p107 + p130-p203 + p246-p261）
cache_file = REPO_ROOT / "var/data/_mineru_cache/600588_用友网络_annual_report_2025_20250329/3ca8e475-0b26-42ed-9bc2-f31022ef0ba3_content_list.json"
raw = json.loads(cache_file.read_text(encoding="utf-8"))
content_list = _normalize_content_list(raw)
print(f"缓存 content_list: {len(content_list)} 页")

# 2. 获取 structured_pages（多段）
pf = json.loads((REPO_ROOT / "var/data/page_filter/annual_2025_pages.json").read_text(encoding="utf-8"))
yonyou = pf["documents"]["600588_用友网络"]
structured_ranges = [r for r in yonyou["kept_ranges"] if r.get("processing_type") == "structured"]
structured_pages: set[int] = set()
for r in structured_ranges:
    structured_pages.update(range(r["start"], r["end"] + 1))
print(f"structured_pages: {len(structured_pages)} 页 (p{min(structured_pages)}-p{max(structured_pages)})")

# 3. 重建 artifact（用修复后的 _build_artifact，保留 table_html + paragraph→title 提升）
pdf_path = REPO_ROOT / "var/data/raw_filings/600588_用友网络/annual/2025/600588_用友网络_annual_report_2025_20250329.pdf"
artifact = _build_artifact(
    pdf_path=pdf_path,
    content_list=content_list,
    full_md="",
    page_filter=structured_pages,
)
doc_id = "600588_用友网络__annual__2025__600588_用友网络_annual_report_2025_20250329__structured_v2"
artifact.document["document_id"] = doc_id
print(f"重建 artifact: {len(artifact.tables)} 张表, {len(artifact.elements)} 个元素")

# 检查 table_html
has_html = sum(1 for t in artifact.tables if t.table_html.strip())
print(f"  含 table_html: {has_html}/{len(artifact.tables)}")

# 检查 title 元素（paragraph→title 提升后应该有 title 了）
title_cnt = sum(1 for el in artifact.elements if el.element_type == "title")
print(f"  title 元素: {title_cnt}")

# 4. 写入 parsed_filings
parsed_root = REPO_ROOT / "var/data/parsed_filings"
write_parsed_artifact(parsed_root, artifact)
tables_jsonl = parsed_root / doc_id / "tables.jsonl"
print(f"写入 {tables_jsonl}")

# 5. 跑 TableExtractor（含 LLM 注释决策）
from finsight_agent.config.settings import load_settings
settings = load_settings()
aliases_path = settings.structured_data.aliases_path
normalizer = MetricNormalizer(aliases_path=aliases_path)
print(f"归一化器: {len(normalizer.aliases)} 条映射")
try:
    llm_client = LlmClient(timeout_seconds=90, max_tokens=8192)
except Exception as e:
    print(f"LLM 初始化失败: {e}，将跳过注释表")
    llm_client = None

extractor = TableExtractor(
    company_code="600588",
    company_name="用友网络",
    source_document_id=doc_id,
    normalizer=normalizer,
    llm_client=llm_client,
)
records = extractor.extract_from_tables_file(tables_jsonl)
print(f"\n=== 提取完成: {len(records)} 条指标 ===")

# 6. 统计分布
from collections import Counter
section_counts = Counter(r.source_section for r in records)
print(f"source_section 分布: {dict(section_counts)}")
stmt_counts = Counter(r.statement_type for r in records)
print(f"statement_type 分布: {dict(stmt_counts)}")

# 7. 写入 SQLite
from finsight_agent.capabilities.structured_data.repository import MetricRepository
repo = MetricRepository(sqlite_path=REPO_ROOT / "var/data/structured_data/metrics.db")
repo.save_records_for_company("用友网络", records)
print(f"写入 SQLite: {len(records)} 条记录")
