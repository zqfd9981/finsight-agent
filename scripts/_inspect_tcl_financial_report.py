"""查看TCL中环财务报告章节(p82-106, 前25页)的实际内容构成。"""
import pdfplumber

pdf_path = "var/data/raw_filings/002129_TCL中环/annual/2025/002129_TCL中环_annual_report_2025_20250426.pdf"

with pdfplumber.open(pdf_path) as pdf:
    for page_num in range(82, 107):
        page = pdf.pages[page_num - 1]
        text = page.extract_text() or ""
        # 只打印前几行识别页面类型
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        # 跳过页眉
        content_lines = [l for l in lines if "TCL中环新能源科技股份有限公司2024年年度报告全文" not in l]
        preview = " | ".join(content_lines[:3])[:120]
        tables = page.extract_tables() or []
        table_info = f"[{len(tables)}表]" if tables else ""
        print(f"p{page_num:>3} {table_info:>5} | {preview}")
