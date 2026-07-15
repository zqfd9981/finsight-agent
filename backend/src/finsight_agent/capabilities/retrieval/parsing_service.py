from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .parsing_models import (
    ParseReport,
    ParsedDocumentArtifact,
    ParsedElement,
    ParsedTable,
)


class ParsingService:
    """负责主解析器、fallback 解析器与失败兜底的薄调度层。"""

    def __init__(self, primary_parser, fallback_parser) -> None:
        self._primary_parser = primary_parser
        self._fallback_parser = fallback_parser

    def parse_document(self, pdf_path: Path) -> ParsedDocumentArtifact:
        """优先走主解析器，失败后整份文档切到 fallback。"""

        try:
            artifact = self._primary_parser.parse(pdf_path)
            return self._with_primary_report(artifact)
        except Exception as primary_error:
            try:
                artifact = self._fallback_parser.parse(pdf_path)
                return self._with_fallback_report(artifact)
            except Exception as fallback_error:
                return self._build_failed_artifact(
                    pdf_path=pdf_path,
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )

    def _with_primary_report(self, artifact: ParsedDocumentArtifact) -> ParsedDocumentArtifact:
        """确保主解析成功产物带有完整 parse report。"""

        if artifact.parse_report is None:
            artifact.parse_report = ParseReport(
                document_id=str(artifact.document.get("document_id", "")),
                status="success",
                primary_parser="mineru",
                parser_version="unknown",
                fallback_used=False,
            )
            return artifact
        artifact.parse_report = replace(artifact.parse_report, fallback_used=False)
        return artifact

    def _with_fallback_report(self, artifact: ParsedDocumentArtifact) -> ParsedDocumentArtifact:
        """确保 fallback 成功产物正确标注 fallback 信息。"""

        if artifact.parse_report is None:
            artifact.parse_report = ParseReport(
                document_id=str(artifact.document.get("document_id", "")),
                status="success",
                primary_parser="mineru",
                parser_version="unknown",
                fallback_used=True,
                fallback_parser="pdfplumber",
            )
            return artifact
        artifact.parse_report = replace(
            artifact.parse_report,
            fallback_used=True,
            fallback_parser="pdfplumber",
        )
        return artifact

    def _build_failed_artifact(
        self,
        pdf_path: Path,
        primary_error: Exception,
        fallback_error: Exception,
    ) -> ParsedDocumentArtifact:
        """当主解析器和 fallback 都失败时，返回最小失败产物。"""

        return ParsedDocumentArtifact(
            document={
                "document_id": pdf_path.stem,
                "source_path": str(pdf_path),
                "title": pdf_path.name,
            },
            elements=[],
            tables=[],
            parse_report=ParseReport(
                document_id=pdf_path.stem,
                status="failed",
                primary_parser="mineru",
                parser_version="failed",
                fallback_used=True,
                fallback_parser="pdfplumber",
                warnings=[
                    f"primary_parser_failed: {primary_error}",
                    f"fallback_parser_failed: {fallback_error}",
                ],
            ),
        )


def normalize_parsed_document(
    raw_payload: dict[str, object],
    parser_source: str,
) -> ParsedDocumentArtifact:
    """把第三方 parser 的原始结果映射成内部统一解析产物。"""

    raw_document = _require_mapping(raw_payload.get("document"), "document")
    document_id = str(raw_document.get("document_id", ""))

    elements: list[ParsedElement] = []
    for index, raw_element in enumerate(raw_payload.get("elements", []) or [], start=1):
        if not isinstance(raw_element, dict):
            continue
        elements.append(
            ParsedElement(
                element_id=f"{document_id}_element_{index:06d}",
                document_id=document_id,
                element_type=str(raw_element.get("type", "paragraph")),
                page_start=int(raw_element.get("page_start", 1)),
                page_end=int(raw_element.get("page_end", raw_element.get("page_start", 1))),
                order_in_document=index,
                section_path=list(raw_element.get("section_path", []) or []),
                text=str(raw_element.get("text", "")),
                parser_source=parser_source,
                confidence=_maybe_float(raw_element.get("confidence")),
                bbox=raw_element.get("bbox") if isinstance(raw_element.get("bbox"), dict) else None,
                related_table_id=(
                    str(raw_element.get("related_table_id"))
                    if raw_element.get("related_table_id") is not None
                    else None
                ),
            )
        )

    tables: list[ParsedTable] = []
    for index, raw_table in enumerate(raw_payload.get("tables", []) or [], start=1):
        if not isinstance(raw_table, dict):
            continue
        tables.append(
            ParsedTable(
                table_id=f"{document_id}_table_{index:06d}",
                document_id=document_id,
                page_start=int(raw_table.get("page_start", 1)),
                page_end=int(raw_table.get("page_end", raw_table.get("page_start", 1))),
                order_in_document=index,
                section_path=list(raw_table.get("section_path", []) or []),
                caption_text=str(raw_table.get("caption_text", "")),
                table_text=str(raw_table.get("table_text", "")),
                table_markdown=str(raw_table.get("table_markdown", "")),
                table_html=str(raw_table.get("table_html", "")),
                parser_source=parser_source,
                confidence=_maybe_float(raw_table.get("confidence")),
                bbox=raw_table.get("bbox") if isinstance(raw_table.get("bbox"), dict) else None,
                table_type_hint=(
                    str(raw_table.get("table_type_hint"))
                    if raw_table.get("table_type_hint") is not None
                    else None
                ),
                resolved_unit=str(raw_table.get("resolved_unit", "") or ""),
                related_metric_hints=[
                    str(item) for item in (raw_table.get("related_metric_hints", []) or [])
                ],
            )
        )

    raw_report = _require_mapping(raw_payload.get("parse_report"), "parse_report")
    parse_report = ParseReport(
        document_id=document_id,
        status=str(raw_report.get("status", "success")),
        primary_parser=str(raw_report.get("primary_parser", parser_source)),
        parser_version=str(raw_report.get("parser_version", "unknown")),
        fallback_used=bool(raw_report.get("fallback_used", False)),
        fallback_parser=(
            str(raw_report.get("fallback_parser"))
            if raw_report.get("fallback_parser") is not None
            else None
        ),
        page_count=int(raw_document.get("page_count", 0) or 0),
        parsed_element_count=len(elements),
        parsed_table_count=len(tables),
        warnings=[str(item) for item in (raw_report.get("warnings", []) or [])],
        duration_ms=int(raw_report.get("duration_ms", 0) or 0),
    )
    return ParsedDocumentArtifact(
        document=dict(raw_document),
        elements=elements,
        tables=tables,
        parse_report=parse_report,
    )


def build_parsing_service() -> ParsingService:
    """构造默认解析服务，主解析失败时自动退回 pdfplumber。"""

    from finsight_agent.infra.document_parsers.mineru_parser import MineruDocumentParser
    from finsight_agent.infra.document_parsers.pdfplumber_parser import PdfplumberDocumentParser

    return ParsingService(
        primary_parser=MineruDocumentParser(),
        fallback_parser=PdfplumberDocumentParser(),
    )


def _require_mapping(value: object, name: str) -> dict[str, object]:
    """确保 normalizer 输入节点是对象。"""

    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _maybe_float(value: object) -> float | None:
    """把可选数值字段安全转换成浮点数。"""

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
