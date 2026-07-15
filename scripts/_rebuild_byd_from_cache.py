"""从 MinerU 缓存重建比亚迪 tables.jsonl（带 table_html），跑 TableExtractor 验证。

不调 MinerU API，直接读 _mineru_cache 下的 content_list.json。
跑完后可删除此脚本。
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

# 1. 读缓存（41b44ab3 是 structured 路径的结果，page_idx 0-86 = 87 页）
cache_file = REPO_ROOT / "var/data/_mineru_cache/002594_比亚迪_annual_report_2025_20250325/41b44ab3-9c34-4845-b0d1-ea0821fe9fb4_content_list.json"
raw = json.loads(cache_file.read_text(encoding="utf-8"))
content_list = _normalize_content_list(raw)
print(f"缓存 content_list: {len(content_list)} 页")

# 2. 获取 structured_pages
pf = json.loads((REPO_ROOT / "var/data/page_filter/annual_2025_pages.json").read_text(encoding="utf-8"))
byd = pf["documents"]["002594_比亚迪"]
structured_ranges = [r for r in byd["kept_ranges"] if r.get("processing_type") == "structured"]
structured_pages: set[int] = set()
for r in structured_ranges:
    structured_pages.update(range(r["start"], r["end"] + 1))
print(f"structured_pages: {len(structured_pages)} 页 (p{min(structured_pages)}-p{max(structured_pages)})")

# 3. 重建 artifact（用修复后的 _build_artifact，保留 table_html）
pdf_path = REPO_ROOT / "var/data/raw_filings/002594_比亚迪/annual/2025/002594_比亚迪_annual_report_2025_20250325.pdf"
artifact = _build_artifact(
    pdf_path=pdf_path,
    content_list=content_list,
    full_md="",
    page_filter=structured_pages,
)
doc_id = "002594_比亚迪__annual__2025__002594_比亚迪_annual_report_2025_20250325__structured_v2"
artifact.document["document_id"] = doc_id
print(f"重建 artifact: {len(artifact.tables)} 张表, {len(artifact.elements)} 个元素")

# 检查 table_html 是否存在
has_html = sum(1 for t in artifact.tables if t.table_html.strip())
print(f"  含 table_html: {has_html}/{len(artifact.tables)}")

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
    company_code="002594",
    company_name="比亚迪",
    source_document_id=doc_id,
    normalizer=normalizer,
    llm_client=llm_client,
)
records = extractor.extract_from_tables_file(tables_jsonl)
print(f"\n=== 提取完成: {len(records)} 条指标 ===")

# 6. 统计 source_section 分布
from collections import Counter
section_counts = Counter(r.source_section for r in records)
print(f"source_section 分布: {dict(section_counts)}")
stmt_counts = Counter(r.statement_type for r in records)
print(f"statement_type 分布: {dict(stmt_counts)}")

# 7. 写入 SQLite
from finsight_agent.capabilities.structured_data.repository import MetricRepository
repo = MetricRepository(sqlite_path=REPO_ROOT / "var/data/structured_data/metrics.db")
repo.save_records_for_company("比亚迪", records)
print(f"写入 SQLite: {len(records)} 条记录")
