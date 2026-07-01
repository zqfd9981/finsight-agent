from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


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
    ParsedTable,
)
from finsight_agent.capabilities.retrieval.parsed_storage import (
    write_chunk_artifact,
    write_parsed_artifact,
)


class PdfParsingArtifactsTest(unittest.TestCase):
    def test_write_parsed_artifact_creates_expected_files(self) -> None:
        artifact = ParsedDocumentArtifact(
            document={
                "document_id": "688012_semiannual_report_2025_20250829",
                "title": "2025年半年度报告",
                "page_count": 120,
            },
            elements=[
                ParsedElement(
                    element_id="doc_element_000001",
                    document_id="688012_semiannual_report_2025_20250829",
                    element_type="title",
                    page_start=3,
                    page_end=3,
                    order_in_document=1,
                    section_path=["管理层讨论与分析"],
                    text="管理层讨论与分析",
                    parser_source="mineru",
                )
            ],
            tables=[
                ParsedTable(
                    table_id="doc_table_000001",
                    document_id="688012_semiannual_report_2025_20250829",
                    page_start=20,
                    page_end=21,
                    order_in_document=1,
                    section_path=["主要会计数据"],
                    caption_text="表1：主要财务数据",
                    table_text="营业收入 100 净利润 50",
                    table_markdown="| 指标 | 数值 |",
                    parser_source="mineru",
                )
            ],
            parse_report=ParseReport(
                document_id="688012_semiannual_report_2025_20250829",
                status="success",
                primary_parser="mineru",
                parser_version="mineru_v1",
                fallback_used=False,
                page_count=120,
                parsed_element_count=1,
                parsed_table_count=1,
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = write_parsed_artifact(
                root=Path(temp_dir) / "parsed_filings",
                artifact=artifact,
            )

            self.assertTrue((output_dir / "document.json").exists())
            self.assertTrue((output_dir / "elements.jsonl").exists())
            self.assertTrue((output_dir / "tables.jsonl").exists())
            self.assertTrue((output_dir / "parse_report.json").exists())

            document_payload = json.loads(
                (output_dir / "document.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                document_payload["document_id"],
                "688012_semiannual_report_2025_20250829",
            )

    def test_write_chunk_artifact_creates_expected_files(self) -> None:
        parents = [
            ChunkRecord(
                chunk_id="doc_1_parent_000001",
                document_id="doc_1",
                chunk_level="parent",
                parent_id=None,
                chunk_text="管理层讨论与分析\n报告期内公司业务继续增长。",
                page_start=3,
                page_end=4,
                page_anchor=3,
                section_path=["管理层讨论与分析"],
                element_ids=["e1", "e2"],
                order_in_document=1,
                source_parser="mineru",
                created_from_parser_version="mineru_v1",
            )
        ]
        children = [
            ChunkRecord(
                chunk_id="doc_1_child_000001_01",
                document_id="doc_1",
                chunk_level="child",
                parent_id="doc_1_parent_000001",
                chunk_text="报告期内公司业务继续增长。",
                page_start=4,
                page_end=4,
                page_anchor=4,
                section_path=["管理层讨论与分析"],
                element_ids=["e2"],
                order_in_document=2,
                source_parser="mineru",
                created_from_parser_version="mineru_v1",
            )
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = write_chunk_artifact(
                root=Path(temp_dir) / "chunked_filings",
                document_id="doc_1",
                parents=parents,
                children=children,
                chunk_report={
                    "document_id": "doc_1",
                    "chunker_version": "chunker_v1",
                    "parent_count": 1,
                    "child_count": 1,
                    "warnings": [],
                    "generated_at": "2026-06-30T00:00:00Z",
                },
            )

            self.assertTrue((output_dir / "parents.jsonl").exists())
            self.assertTrue((output_dir / "children.jsonl").exists())
            self.assertTrue((output_dir / "chunk_report.json").exists())


if __name__ == "__main__":
    unittest.main()
