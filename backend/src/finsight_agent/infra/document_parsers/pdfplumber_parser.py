from __future__ import annotations

from pathlib import Path

import pdfplumber

from finsight_agent.capabilities.retrieval.parsing_models import ParsedDocumentArtifact
from finsight_agent.capabilities.retrieval.parsing_service import normalize_parsed_document


class PdfplumberDocumentParser:
    """使用 pdfplumber 提供整份文档级轻量 fallback 解析。"""

    def parse(self, pdf_path: Path, page_filter: set[int] | None = None) -> ParsedDocumentArtifact:
        """提取页级文本和基础表格，再映射成统一解析产物。

        Args:
            pdf_path: PDF 文件路径
            page_filter: 只解析这些页码（1-based）。None 表示全量解析。
        """

        elements: list[dict[str, object]] = []
        tables: list[dict[str, object]] = []
        current_section_path: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            for page_index, page in enumerate(pdf.pages, start=1):
                if page_filter is not None and page_index not in page_filter:
                    continue
                raw_text = page.extract_text() or ""
                text_parts = _split_page_into_parts(raw_text)
                if _should_skip_page(text_parts):
                    continue

                last_caption_text: str | None = None
                for part_index, text_part in enumerate(text_parts, start=1):
                    if _should_skip_text_part(text_part):
                        continue

                    element_type = _infer_element_type(text_part, page_index, part_index)
                    if element_type == "title":
                        current_section_path = [text_part]
                    if element_type == "table_caption":
                        last_caption_text = text_part

                    elements.append(
                        {
                            "type": element_type,
                            "page_start": page_index,
                            "page_end": page_index,
                            "text": text_part,
                            "section_path": list(current_section_path),
                            "confidence": None,
                        }
                    )

                for raw_table in page.extract_tables() or []:
                    normalized_table = _normalize_table(
                        raw_table=raw_table,
                        page_index=page_index,
                        section_path=current_section_path,
                        caption_text=last_caption_text or "",
                    )
                    if normalized_table is not None:
                        tables.append(normalized_table)

        raw_payload = {
            "document": {
                "document_id": pdf_path.stem,
                "title": pdf_path.stem,
                "source_path": str(pdf_path),
                "page_count": page_count,
            },
            "elements": elements,
            "tables": tables,
            "parse_report": {
                "status": "success",
                "primary_parser": "pdfplumber",
                "parser_version": "pdfplumber_v1",
                "fallback_used": False,
                "warnings": [],
                "duration_ms": 0,
            },
        }
        return normalize_parsed_document(raw_payload=raw_payload, parser_source="pdfplumber")


def _split_page_into_parts(raw_text: str) -> list[str]:
    """把页级文本按最小结构切成标题、表题和正文片段。"""

    stripped = raw_text.replace("\r", "").strip()
    if not stripped:
        return []

    parts: list[str] = []
    paragraph_buffer: list[str] = []
    for raw_line in stripped.splitlines():
        line = raw_line.strip()
        if not line:
            if paragraph_buffer:
                parts.append(" ".join(paragraph_buffer).strip())
                paragraph_buffer = []
            continue

        if _looks_like_standalone_structural_line(line):
            if paragraph_buffer:
                parts.append(" ".join(paragraph_buffer).strip())
                paragraph_buffer = []
            parts.append(line)
            continue

        paragraph_buffer.append(line)

    if paragraph_buffer:
        parts.append(" ".join(paragraph_buffer).strip())
    return [part for part in parts if part]


def _looks_like_standalone_structural_line(line: str) -> bool:
    """判断一行是否更像独立结构单元，而不是普通正文。"""

    if _looks_like_report_header(line):
        return True
    if _looks_like_catalog_heading(line):
        return True
    if _looks_like_catalog_entry(line):
        return True
    if _looks_like_appendix_inventory_entry(line):
        return True
    if _looks_like_glossary_entry(line):
        return True
    if _looks_like_section_title(line):
        return True
    if _looks_like_table_caption(line):
        return True
    if len(line) <= 30 and not line.endswith(("。", "；", "：", ":")):
        return True
    return False


def _should_skip_page(text_parts: list[str]) -> bool:
    """统一处理目录页、备查文件目录页和纯释义页的整页跳过。"""

    normalized_parts = _strip_report_headers(text_parts)
    if not normalized_parts:
        return False
    return (
        _is_catalog_page(normalized_parts)
        or _is_appendix_inventory_page(normalized_parts)
        or _is_glossary_page(normalized_parts)
    )


def _strip_report_headers(text_parts: list[str]) -> list[str]:
    """去掉每页重复出现的公司名 + 报告全文页眉，避免干扰页面类型判断。"""

    return [part for part in text_parts if not _looks_like_report_header(part)]


def _is_catalog_page(text_parts: list[str]) -> bool:
    """如果整页基本由目录标题和目录行组成，则整页跳过。"""

    if not text_parts:
        return False
    if text_parts[0] != "目录":
        return False

    remaining_parts = text_parts[1:]
    if not remaining_parts:
        return True
    return all(_looks_like_catalog_entry(part) for part in remaining_parts)


def _is_appendix_inventory_page(text_parts: list[str]) -> bool:
    """跳过“备查文件目录”这类只列附件清单的前置页。"""

    if not text_parts:
        return False
    if text_parts[0] != "备查文件目录":
        return False

    remaining_parts = text_parts[1:]
    if not remaining_parts:
        return True
    return all(_looks_like_appendix_inventory_entry(part) for part in remaining_parts)


def _is_glossary_page(text_parts: list[str]) -> bool:
    """跳过只包含术语释义表的前置页。"""

    if not text_parts:
        return False
    if text_parts[0] != "释义":
        return False

    remaining_parts = text_parts[1:]
    if not remaining_parts:
        return True
    return all(_looks_like_glossary_entry(part) for part in remaining_parts)


def _should_skip_text_part(text: str) -> bool:
    """过滤掉对后续检索帮助很小的页眉、页码等碎片。"""

    stripped = text.strip()
    if not stripped:
        return True
    if stripped.isdigit():
        return True
    if _looks_like_report_header(stripped):
        return True
    if _looks_like_catalog_heading(stripped):
        return True
    if _looks_like_catalog_entry(stripped):
        return True
    if stripped == "备查文件目录":
        return True
    if stripped == "释义":
        return True
    if _looks_like_glossary_entry(stripped):
        return True
    return False


def _infer_element_type(text: str, page_index: int, part_index: int) -> str:
    """按最小启发式判断 element 类型，避免 fallback 过度复杂。"""

    if _looks_like_table_caption(text):
        return "table_caption"
    if _looks_like_catalog_heading(text):
        return "paragraph"
    if page_index == 1 and part_index == 1 and len(text) <= 30:
        return "title"
    if _looks_like_section_title(text):
        return "title"
    return "paragraph"


def _looks_like_catalog_heading(text: str) -> bool:
    """识别“目录”“备查文件目录”这类目录页标签。"""

    return text in {"目录", "备查文件目录"}


def _looks_like_report_header(text: str) -> bool:
    """识别财报页面顶部反复出现的“公司名 + 报告全文”页眉。"""

    return "报告" in text and "全文" in text


def _looks_like_catalog_entry(text: str) -> bool:
    """识别带点线和页码的目录行，避免误判成正式章节标题。"""

    return ("...." in text or "……" in text) and any(char.isdigit() for char in text)


def _looks_like_appendix_inventory_entry(text: str) -> bool:
    """识别“备查文件目录”里的分项清单。"""

    return text.startswith(("（一）", "（二）", "（三）", "（四）", "（五）", "(一)", "(二)", "(三)", "(四)", "(五)"))


def _looks_like_glossary_entry(text: str) -> bool:
    """识别释义页里的术语-含义条目。"""

    if " 指 " in text:
        return True
    return text.startswith("释义项")


def _looks_like_table_caption(text: str) -> bool:
    """识别像“表1：主要财务数据”这样的表题。"""

    return text.startswith("表") and ("：" in text or ":" in text)


def _looks_like_section_title(text: str) -> bool:
    """识别常见章节标题样式。"""

    if _looks_like_catalog_entry(text):
        return False
    if text.startswith(("第一节", "第二节", "第三节", "第四节", "第五节")):
        return True
    if text.startswith(("一、", "二、", "三、", "四、", "五、")):
        return True
    if text.startswith(("（一）", "（二）", "（三）", "(一)", "(二)", "(三)")):
        return True
    return False


def _normalize_table(
    raw_table: list[list[str | None]],
    page_index: int,
    section_path: list[str],
    caption_text: str,
) -> dict[str, object] | None:
    """把 pdfplumber 的二维表格结果映射成内部标准表结构。"""

    normalized_rows: list[list[str]] = []
    for row in raw_table:
        cleaned_row = [str(cell or "").strip() for cell in row]
        if any(cell for cell in cleaned_row):
            normalized_rows.append(cleaned_row)

    if not normalized_rows:
        return None

    table_text = "\n".join(" ".join(cell for cell in row if cell) for row in normalized_rows)
    markdown_lines = ["| " + " | ".join(row) + " |" for row in normalized_rows]
    return {
        "page_start": page_index,
        "page_end": page_index,
        "section_path": list(section_path),
        "caption_text": caption_text,
        "table_text": table_text,
        "table_markdown": "\n".join(markdown_lines),
        "confidence": None,
    }
