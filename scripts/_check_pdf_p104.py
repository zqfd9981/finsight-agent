"""用 pdfplumber 提取原始 PDF p103-105 的文本，确认 p104 内容。"""
import pdfplumber
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
pdf_path = REPO_ROOT / "var" / "data" / "raw_filings" / "002129_TCL中环" / "annual" / "2025" / "002129_TCL中环_annual_report_2025_20250426.pdf"

with pdfplumber.open(pdf_path) as pdf:
    for page_idx in [103, 104, 105]:
        if page_idx > len(pdf.pages):
            continue
        page = pdf.pages[page_idx - 1]
        text = page.extract_text() or ""
        print(f"\n{'=' * 80}")
        print(f"=== p{page_idx} 原始文本（前 1500 字符）===")
        print(f"{'=' * 80}")
        print(text[:1500])
