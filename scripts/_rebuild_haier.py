"""海尔智家：重跑 TableExtractor（代码修复后），重新入库 SQLite。"""
import sys
import json
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))

from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.infra.llm.client import LlmClient

DB_PATH = REPO / "var/data/structured_data/metrics.db"
STRUCT_DIR = REPO / "var/data/parsed_filings/600690_海尔智家__annual__2025__600690_海尔智家_annual_report_2025_20250328__structured"
TABLES_JSONL = STRUCT_DIR / "tables.jsonl"
ELEMENTS_JSONL = STRUCT_DIR / "elements.jsonl"
DOC_ID = "600690_海尔智家__annual__2025__600690_海尔智家_annual_report_2025_20250328__structured"

print("=" * 80)
print("海尔智家 (600690) 重建")
print("=" * 80)

# 1. 删除旧 SQLite 记录
conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.execute("DELETE FROM metric_records WHERE company_code = '600690'")
deleted = cur.rowcount
conn.commit()
print(f"1. 删除旧记录: {deleted} 条")

# 2. 重跑 TableExtractor
print(f"\n2. 重跑 TableExtractor...")
llm_client = LlmClient()
normalizer = MetricNormalizer(
    aliases_path=REPO / "var/data/structured_data/metric_aliases.json",
    llm_client=llm_client,
)
extractor = TableExtractor(
    company_code="600690",
    company_name="海尔智家",
    source_document_id=DOC_ID,
    normalizer=normalizer,
    llm_client=llm_client,
)
records = extractor.extract_from_tables_file(TABLES_JSONL)
print(f"   提取 {len(records)} 条记录")

# 3. 统计 source_section 分布
from collections import Counter
ss_counts = Counter(r.source_section for r in records)
st_counts = Counter(r.statement_type for r in records)
print(f"\n3. source_section 分布: {dict(ss_counts)}")
print(f"   statement_type 分布: {dict(st_counts)}")

# 4. 入库
print(f"\n4. 入库 SQLite...")
from finsight_agent.capabilities.structured_data.repository import MetricRepository
repo = MetricRepository(sqlite_path=DB_PATH)
repo.save_records_for_company("600690", records)
print(f"   入库完成")

conn.close()
print(f"\n完成！")
