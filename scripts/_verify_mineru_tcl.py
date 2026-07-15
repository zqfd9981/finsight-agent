"""验证 MineruDocumentParser：用 TCL中环 p10-12 跑解析。"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from finsight_agent.infra.document_parsers.mineru_parser import MineruDocumentParser

pdf_path = REPO_ROOT / "var" / "data" / "raw_filings" / "002129_TCL中环" / "annual" / "2025" / "002129_TCL中环_annual_report_2025_20250426.pdf"
page_filter = {10, 11, 12}

print(f"PDF: {pdf_path.name}")
print(f"解析页: {sorted(page_filter)}")
print("=" * 80, flush=True)

parser = MineruDocumentParser(
    cache_dir=REPO_ROOT / "var" / "data" / "_mineru_cache",
)
artifact = parser.parse(pdf_path, page_filter=page_filter)

print(f"\n解析完成:")
print(f"  elements: {len(artifact.elements)}")
print(f"  tables: {len(artifact.tables)}")

print(f"\n=== 前 10 个 elements ===")
for elem in artifact.elements[:10]:
    text_preview = elem.text[:80].replace("\n", " ")
    print(f"  p{elem.page_start} [{elem.element_type:>10}] {text_preview}")

print(f"\n=== 所有 tables ===")
for tbl in artifact.tables:
    md_preview = tbl.table_markdown[:200].replace("\n", " | ")
    print(f"  p{tbl.page_start} {tbl.caption_text[:40]}")
    print(f"    {md_preview}")

print(f"\n=== parse_report ===")
if artifact.parse_report:
    print(f"  status: {artifact.parse_report.status}")
    print(f"  primary_parser: {artifact.parse_report.primary_parser}")
    print(f"  page_count: {artifact.parse_report.page_count}")
    print(f"  parsed_element_count: {artifact.parse_report.parsed_element_count}")
    print(f"  parsed_table_count: {artifact.parse_report.parsed_table_count}")
