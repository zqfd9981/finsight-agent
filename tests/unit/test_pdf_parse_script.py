from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.parsing_models import (
    ChunkRecord,
    ParseReport,
    ParsedDocumentArtifact,
    ParsedElement,
)

from scripts.parse_pdf_document import run_parse_document


class PdfParseScriptTest(unittest.TestCase):
    def test_run_parse_document_writes_summary_json(self) -> None:
        artifact = ParsedDocumentArtifact(
            document={"document_id": "doc_1", "title": "sample"},
            elements=[
                ParsedElement(
                    element_id="e1",
                    document_id="doc_1",
                    element_type="paragraph",
                    page_start=1,
                    page_end=1,
                    order_in_document=1,
                    text="hello",
                    parser_source="pdfplumber",
                )
            ],
            tables=[],
            parse_report=ParseReport(
                document_id="doc_1",
                status="success",
                primary_parser="pdfplumber",
                parser_version="pdfplumber_v1",
                fallback_used=False,
            ),
        )

        class FakeParsingService:
            def parse_document(self, pdf_path: Path) -> ParsedDocumentArtifact:
                return artifact

        class FakeChunkingResult:
            def __init__(self) -> None:
                self.parents = [
                    ChunkRecord(
                        chunk_id="p1",
                        document_id="doc_1",
                        chunk_level="parent",
                        parent_id=None,
                        chunk_text="parent",
                        page_start=1,
                        page_end=1,
                        page_anchor=1,
                    )
                ]
                self.children = [
                    ChunkRecord(
                        chunk_id="c1",
                        document_id="doc_1",
                        chunk_level="child",
                        parent_id="p1",
                        chunk_text="child",
                        page_start=1,
                        page_end=1,
                        page_anchor=1,
                    )
                ]

        fake_settings = type(
            "FakeSettings",
            (),
            {
                "retrieval": type(
                    "FakeRetrieval",
                    (),
                    {
                        "parsed_filings_root": Path("var/data/parsed_filings"),
                        "chunked_filings_root": Path("var/data/chunked_filings"),
                        "parent_target_chars": 2000,
                        "child_target_chars": 500,
                    },
                )()
            },
        )()

        with (
            mock.patch("scripts.parse_pdf_document.load_settings", return_value=fake_settings),
            mock.patch(
                "scripts.parse_pdf_document.build_parsing_service",
                return_value=FakeParsingService(),
            ),
            mock.patch(
                "scripts.parse_pdf_document.build_chunks",
                return_value=FakeChunkingResult(),
            ),
            mock.patch(
                "scripts.parse_pdf_document.write_parsed_artifact",
                return_value=Path("var/data/parsed_filings/doc_1"),
            ),
            mock.patch(
                "scripts.parse_pdf_document.write_chunk_artifact",
                return_value=Path("var/data/chunked_filings/doc_1"),
            ),
            mock.patch("sys.stdout", new=io.StringIO()) as fake_stdout,
        ):
            exit_code = run_parse_document(["--pdf-path", "sample.pdf"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(fake_stdout.getvalue())
        self.assertEqual(payload["document_id"], "doc_1")
        self.assertEqual(payload["parent_count"], 1)
        self.assertEqual(payload["child_count"], 1)


if __name__ == "__main__":
    unittest.main()
