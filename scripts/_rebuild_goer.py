"""歌尔股份 (002241) 重建：用已有 structured 目录 + 修复后的 TableExtractor 重跑。

歌尔已有 structured 目录（625 元素/184 表），但注释区 0 条记录。
原因：旧版 TableExtractor 没有修复2（注释区兜底）和修复3（内容兜底）。
直接重跑 TableExtractor 即可，无需重建 tables.jsonl。

三表页码（来自完整年报）：
  p85 合并资产负债表, p89 合并利润表, p92 合并现金流量表, p95 合并所有者权益变动表
"""
import sys
import json
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))

from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.infra.llm.client import LlmClient

DB_PATH = REPO / "var/data/structured_data/metrics.db"
STRUCT_DIR = REPO / "var/data/parsed_filings/002241_歌尔股份__annual__2025__002241_歌尔股份_annual_report_2025_20250327__structured"
TABLES_JSONL = STRUCT_DIR / "tables.jsonl"
DOC_ID = "002241_歌尔股份__annual__2025__002241_歌尔股份_annual_report_2025_20250327__structured"

print("=" * 80)
print("歌尔股份 (002241) 重跑 TableExtractor（修复后）")
print("=" * 80)
print(f"tables.jsonl: {TABLES_JSONL.name}, 存在={TABLES_JSONL.exists()}")

# 1. 删除旧 SQLite 记录
conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.execute("DELETE FROM metric_records WHERE company_code = '002241'")
deleted = cur.rowcount
conn.commit()
conn.close()
print(f"\n1. 删除旧记录: {deleted} 条")

# 2. 重跑 TableExtractor
print(f"\n2. 重跑 TableExtractor...")
llm_client = LlmClient()
normalizer = MetricNormalizer(
    aliases_path=REPO / "var/data/structured_data/metric_aliases.json",
    llm_client=llm_client,
)
extractor = TableExtractor(
    company_code="002241",
    company_name="歌尔股份",
    source_document_id=DOC_ID,
    normalizer=normalizer,
    llm_client=llm_client,
)
records = extractor.extract_from_tables_file(TABLES_JSONL)
print(f"   提取 {len(records)} 条记录")

# 3. 统计
from collections import Counter
ss_counts = Counter(r.source_section for r in records)
st_counts = Counter(r.statement_type for r in records)
print(f"\n3. source_section 分布: {dict(ss_counts)}")
print(f"   statement_type 分布: {dict(st_counts)}")

# 4. 入库
print(f"\n4. 入库 SQLite...")
repo = MetricRepository(sqlite_path=DB_PATH)
repo.save_records_for_company("002241", records)
print(f"   入库完成")

print(f"\n完成！")
