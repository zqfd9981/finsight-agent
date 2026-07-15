"""检查 p103 修复后的 markdown 格式，找出 is_metric_series_table 失败原因。"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from finsight_agent.capabilities.structured_data.cross_page_repair import (
    apply_repair_to_tables,
    find_truncated_tables,
    repair_truncated_table,
)
from finsight_agent.capabilities.structured_data.table_extractor import is_metric_series_table
from finsight_agent.infra.document_parsers.mineru_parser import MineruDocumentParser

DOC_DIR = (
    REPO_ROOT
    / "var"
    / "data"
    / "parsed_filings"
    / "002129_TCL中环__annual__2025__002129_TCL中环_annual_report_2025_20250426__structured"
)
TABLES_JSONL = DOC_DIR / "tables.jsonl"
PDF_PATH = (
    REPO_ROOT
    / "var"
    / "data"
    / "raw_filings"
    / "002129_TCL中环"
    / "annual"
    / "2025"
    / "002129_TCL中环_annual_report_2025_20250426.pdf"
)

with TABLES_JSONL.open(encoding="utf-8") as f:
    raw_tables = [json.loads(l) for l in f if l.strip()]

truncated = find_truncated_tables(raw_tables)
mineru = MineruDocumentParser(cache_dir=REPO_ROOT / "var" / "data" / "_mineru_cache")

# 只修复 p103
for idx, check in truncated:
    if check.page_start != 103:
        continue
    repair = repair_truncated_table(
        pdf_path=PDF_PATH,
        table_check=check,
        cache_dir=REPO_ROOT / "var" / "data" / "_merge_tmp",
        mineru_parser=mineru,
    )
    if not repair.repaired:
        print("修复失败")
        sys.exit(1)

    # 应用修复
    repaired_tables = apply_repair_to_tables(raw_tables, [repair])
    p103_table = repaired_tables[idx]
    md = p103_table.get("table_markdown") or ""

    print(f"=== p103 修复后 markdown（{md.count(chr(10))+1} 行）===\n")
    lines = md.split("\n")
    for i, line in enumerate(lines, 1):
        print(f"  L{i:2d}: {line}")

    print(f"\n=== is_metric_series_table 判断 ===")
    result = is_metric_series_table(md)
    print(f"  结果: {result}")

    # 对比 p97（完整权益变动表，提取了3条指标）
    p97_table = raw_tables[17]  # p97
    p97_md = p97_table.get("table_markdown") or ""
    print(f"\n=== p97 完整权益变动表（{p97_md.count(chr(10))+1} 行）前 10 行 ===")
    for i, line in enumerate(p97_md.split("\n")[:10], 1):
        print(f"  L{i:2d}: {line}")
    print(f"  is_metric_series_table: {is_metric_series_table(p97_md)}")
