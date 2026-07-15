"""隆基绿能 (601012) 重跑修复后的 TableExtractor + 入库 + 验证。

已有 structured 目录（215 表/169 含 html），但注释区 0 条。
直接重跑 TableExtractor（修复2+修复3生效后）即可。
"""
import sys
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend" / "src"))

from finsight_agent.capabilities.structured_data.table_extractor import TableExtractor
from finsight_agent.capabilities.structured_data.metric_normalizer import MetricNormalizer
from finsight_agent.capabilities.structured_data.repository import MetricRepository
from finsight_agent.infra.llm.client import LlmClient

DB_PATH = REPO / "var/data/structured_data/metrics.db"
STRUCT_DIR = REPO / "var/data/parsed_filings/601012_隆基绿能__annual__2025__601012_隆基绿能_annual_report_2025_20250507__structured"
TABLES_JSONL = STRUCT_DIR / "tables.jsonl"
DOC_ID = "601012_隆基绿能__annual__2025__601012_隆基绿能_annual_report_2025_20250507__structured"

print("=" * 80)
print("隆基绿能 (601012) 重跑 TableExtractor（修复后）")
print("=" * 80)

# 1. 删除旧 SQLite 记录
conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.execute("DELETE FROM metric_records WHERE company_code = '601012'")
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
    company_code="601012",
    company_name="隆基绿能",
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
repo.save_records_for_company("601012", records)
print(f"   入库完成")

print(f"\n完成！")
