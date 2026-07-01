from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.config.settings import load_settings
from finsight_agent.capabilities.retrieval.parsing_models import (
    ParseReport,
    ParsedDocumentArtifact,
)
from finsight_agent.capabilities.retrieval.parsing_service import (
    ParsingService,
    normalize_parsed_document,
)


class PdfParsingSettingsTest(unittest.TestCase):
    def test_load_settings_exposes_parsing_and_chunking_paths(self) -> None:
        settings = load_settings()

        self.assertEqual(settings.retrieval.parsed_filings_root.name, "parsed_filings")
        self.assertEqual(
            settings.retrieval.chunked_filings_root.name,
            "chunked_filings",
        )
        self.assertEqual(settings.retrieval.primary_parser_name, "mineru")
        self.assertGreater(settings.retrieval.parent_target_chars, 1000)
        self.assertGreater(settings.retrieval.child_target_chars, 200)


class FakeParser:
    def __init__(self, artifact: ParsedDocumentArtifact | None = None, error: Exception | None = None):
        self.artifact = artifact
        self.error = error
        self.calls: list[Path] = []

    def parse(self, pdf_path: Path) -> ParsedDocumentArtifact:
        self.calls.append(pdf_path)
        if self.error is not None:
            raise self.error
        assert self.artifact is not None
        return self.artifact


class PdfParsingServiceTest(unittest.TestCase):
    def test_parse_document_uses_primary_parser_when_it_succeeds(self) -> None:
        artifact = ParsedDocumentArtifact(
            document={"document_id": "doc_1", "title": "主解析成功"},
            parse_report=ParseReport(
                document_id="doc_1",
                status="success",
                primary_parser="mineru",
                parser_version="mineru_v1",
                fallback_used=False,
            ),
        )
        primary = FakeParser(artifact=artifact)
        fallback = FakeParser(
            error=AssertionError("primary 成功时不应该调用 fallback")
        )
        service = ParsingService(primary_parser=primary, fallback_parser=fallback)

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            result = service.parse_document(pdf_path)

        self.assertEqual(result.document["document_id"], "doc_1")
        self.assertEqual(primary.calls, [pdf_path])
        self.assertEqual(fallback.calls, [])

    def test_parse_document_falls_back_when_primary_parser_fails(self) -> None:
        fallback_artifact = ParsedDocumentArtifact(
            document={"document_id": "doc_2", "title": "fallback 成功"},
            parse_report=ParseReport(
                document_id="doc_2",
                status="success",
                primary_parser="mineru",
                parser_version="pdfplumber_v1",
                fallback_used=True,
                fallback_parser="pdfplumber",
            ),
        )
        primary = FakeParser(error=RuntimeError("mineru failed"))
        fallback = FakeParser(artifact=fallback_artifact)
        service = ParsingService(primary_parser=primary, fallback_parser=fallback)

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            result = service.parse_document(pdf_path)

        self.assertEqual(result.document["document_id"], "doc_2")
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(fallback.calls), 1)

    def test_parse_document_returns_minimal_failure_artifact_when_both_parsers_fail(
        self,
    ) -> None:
        primary = FakeParser(error=RuntimeError("mineru failed"))
        fallback = FakeParser(error=RuntimeError("pdfplumber failed"))
        service = ParsingService(primary_parser=primary, fallback_parser=fallback)

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            result = service.parse_document(pdf_path)

        self.assertEqual(result.document["source_path"], str(pdf_path))
        self.assertIsNotNone(result.parse_report)
        self.assertEqual(result.parse_report.status, "failed")
        self.assertTrue(result.parse_report.fallback_used)
        self.assertEqual(result.parse_report.fallback_parser, "pdfplumber")
        self.assertEqual(result.elements, [])
        self.assertEqual(result.tables, [])


class PdfParsingNormalizerTest(unittest.TestCase):
    def test_normalize_parsed_document_maps_raw_payload_to_standard_artifacts(self) -> None:
        raw_payload = {
            "document": {
                "document_id": "688012_semiannual_report_2025_20250829",
                "title": "2025年半年度报告",
                "page_count": 120,
            },
            "elements": [
                {
                    "type": "title",
                    "page_start": 3,
                    "page_end": 3,
                    "text": "管理层讨论与分析",
                    "section_path": ["管理层讨论与分析"],
                    "confidence": 0.99,
                },
                {
                    "type": "paragraph",
                    "page_start": 4,
                    "page_end": 4,
                    "text": "报告期内公司业务继续增长。",
                    "section_path": ["管理层讨论与分析"],
                    "confidence": 0.97,
                },
            ],
            "tables": [
                {
                    "page_start": 20,
                    "page_end": 21,
                    "caption_text": "表1：主要财务数据",
                    "table_text": "营业收入 100 净利润 50",
                    "table_markdown": "| 指标 | 数值 |",
                    "section_path": ["主要会计数据"],
                    "confidence": 0.92,
                }
            ],
            "parse_report": {
                "status": "success",
                "primary_parser": "mineru",
                "parser_version": "mineru_v1",
                "fallback_used": False,
            },
        }

        result = normalize_parsed_document(
            raw_payload=raw_payload,
            parser_source="mineru",
        )

        self.assertEqual(
            result.document["document_id"],
            "688012_semiannual_report_2025_20250829",
        )
        self.assertEqual(len(result.elements), 2)
        self.assertEqual(result.elements[0].element_type, "title")
        self.assertEqual(result.elements[1].order_in_document, 2)
        self.assertEqual(len(result.tables), 1)
        self.assertEqual(result.tables[0].caption_text, "表1：主要财务数据")
        self.assertIsNotNone(result.parse_report)
        self.assertEqual(result.parse_report.parsed_element_count, 2)
        self.assertEqual(result.parse_report.parsed_table_count, 1)


if __name__ == "__main__":
    unittest.main()
