"""查看TCL中环第二节(p9-12)的实际内容，判断价值。"""
import pdfplumber

pdf_path = "var/data/raw_filings/002129_TCL中环/annual/2025/002129_TCL中环_annual_report_2025_20250426.pdf"

with pdfplumber.open(pdf_path) as pdf:
    # 第二节 p9-12
    for page_num in range(9, 13):
        page = pdf.pages[page_num - 1]
        text = page.extract_text() or ""
        print(f"\n{'=' * 80}")
        print(f"=== 第 {page_num} 页 ===")
        print(f"{'=' * 80}")
        print(text)
