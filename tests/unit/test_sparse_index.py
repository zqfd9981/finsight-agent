from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.parsing_models import ChunkRecord
from finsight_agent.capabilities.retrieval.parsed_storage import write_chunk_artifact
from finsight_agent.capabilities.retrieval.sparse_index import (
    SparseChunkIndex,
    SparseSearchFilters,
)


class SparseIndexTest(unittest.TestCase):
    def test_build_index_from_chunk_directory_and_query_keyword(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            chunk_root = temp_root / "chunked_filings"
            index_path = temp_root / "retrieval_index" / "sparse_chunks.db"

            write_chunk_artifact(
                root=chunk_root,
                document_id="002371_annual_report_2025_20250425",
                parents=[],
                children=[
                    ChunkRecord(
                        chunk_id="002371_child_000001",
                        document_id="002371_annual_report_2025_20250425",
                        chunk_level="child",
                        parent_id="002371_parent_000001",
                        chunk_text="报告期内公司净利润同比增长，主要受刻蚀设备收入提升带动。",
                        page_start=42,
                        page_end=42,
                        page_anchor=42,
                        section_path=["管理层讨论与分析", "主营业务分析"],
                        element_ids=["e1", "e2"],
                        order_in_document=1,
                        source_parser="pdfplumber",
                        created_from_parser_version="pdfplumber_v1",
                    ),
                    ChunkRecord(
                        chunk_id="002371_child_000002",
                        document_id="002371_annual_report_2025_20250425",
                        chunk_level="child",
                        parent_id="002371_parent_000001",
                        chunk_text="公司研发投入继续增加，主要投向先进工艺平台。",
                        page_start=50,
                        page_end=50,
                        page_anchor=50,
                        section_path=["管理层讨论与分析", "研发投入"],
                        element_ids=["e3"],
                        order_in_document=2,
                        source_parser="pdfplumber",
                        created_from_parser_version="pdfplumber_v1",
                    ),
                ],
                chunk_report={
                    "document_id": "002371_annual_report_2025_20250425",
                    "chunker_version": "chunker_v1",
                    "parent_count": 0,
                    "child_count": 2,
                    "warnings": [],
                    "generated_at": "2026-06-30T00:00:00Z",
                },
            )

            index = SparseChunkIndex(index_path=index_path)
            indexed_count = index.rebuild_from_chunk_root(chunk_root)

            self.assertEqual(indexed_count, 2)
            hits = index.search("净利润", limit=5)

            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].chunk_id, "002371_child_000001")
            self.assertEqual(hits[0].company_code, "002371")
            self.assertEqual(hits[0].doc_type, "annual_report")
            self.assertEqual(hits[0].page_start, 42)
            self.assertEqual(hits[0].section_path, ["管理层讨论与分析", "主营业务分析"])

    def test_search_supports_company_and_doc_type_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            chunk_root = temp_root / "chunked_filings"
            index_path = temp_root / "retrieval_index" / "sparse_chunks.db"

            write_chunk_artifact(
                root=chunk_root,
                document_id="002371_annual_report_2025_20250425",
                parents=[],
                children=[
                    ChunkRecord(
                        chunk_id="002371_child_000001",
                        document_id="002371_annual_report_2025_20250425",
                        chunk_level="child",
                        parent_id="002371_parent_000001",
                        chunk_text="净利润增长主要来自半导体设备收入增长。",
                        page_start=10,
                        page_end=10,
                        page_anchor=10,
                        section_path=["管理层讨论与分析"],
                        element_ids=["e1"],
                        order_in_document=1,
                        source_parser="pdfplumber",
                        created_from_parser_version="pdfplumber_v1",
                    )
                ],
                chunk_report={
                    "document_id": "002371_annual_report_2025_20250425",
                    "chunker_version": "chunker_v1",
                    "parent_count": 0,
                    "child_count": 1,
                    "warnings": [],
                    "generated_at": "2026-06-30T00:00:00Z",
                },
            )
            write_chunk_artifact(
                root=chunk_root,
                document_id="688012_major_announcement_2025_20250829",
                parents=[],
                children=[
                    ChunkRecord(
                        chunk_id="688012_child_000001",
                        document_id="688012_major_announcement_2025_20250829",
                        chunk_level="child",
                        parent_id="688012_parent_000001",
                        chunk_text="净利润增长与新增订单确认节奏有关。",
                        page_start=2,
                        page_end=2,
                        page_anchor=2,
                        section_path=["公告正文"],
                        element_ids=["e2"],
                        order_in_document=1,
                        source_parser="pdfplumber",
                        created_from_parser_version="pdfplumber_v1",
                    )
                ],
                chunk_report={
                    "document_id": "688012_major_announcement_2025_20250829",
                    "chunker_version": "chunker_v1",
                    "parent_count": 0,
                    "child_count": 1,
                    "warnings": [],
                    "generated_at": "2026-06-30T00:00:00Z",
                },
            )

            index = SparseChunkIndex(index_path=index_path)
            index.rebuild_from_chunk_root(chunk_root)

            company_hits = index.search(
                "净利润",
                limit=5,
                filters=SparseSearchFilters(company_code="002371"),
            )
            self.assertEqual([hit.chunk_id for hit in company_hits], ["002371_child_000001"])

            doc_type_hits = index.search(
                "净利润",
                limit=5,
                filters=SparseSearchFilters(doc_type="major_announcement"),
            )
            self.assertEqual([hit.chunk_id for hit in doc_type_hits], ["688012_child_000001"])

    def test_rebuild_creates_sqlite_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            chunk_root = temp_root / "chunked_filings"
            index_path = temp_root / "retrieval_index" / "sparse_chunks.db"

            write_chunk_artifact(
                root=chunk_root,
                document_id="002371_annual_report_2025_20250425",
                parents=[],
                children=[
                    ChunkRecord(
                        chunk_id="002371_child_000001",
                        document_id="002371_annual_report_2025_20250425",
                        chunk_level="child",
                        parent_id="002371_parent_000001",
                        chunk_text="净利润增长来自主营业务改善。",
                        page_start=8,
                        page_end=8,
                        page_anchor=8,
                        section_path=["管理层讨论与分析"],
                        element_ids=["e1"],
                        order_in_document=1,
                        source_parser="pdfplumber",
                        created_from_parser_version="pdfplumber_v1",
                    )
                ],
                chunk_report={
                    "document_id": "002371_annual_report_2025_20250425",
                    "chunker_version": "chunker_v1",
                    "parent_count": 0,
                    "child_count": 1,
                    "warnings": [],
                    "generated_at": "2026-06-30T00:00:00Z",
                },
            )

            index = SparseChunkIndex(index_path=index_path)
            index.rebuild_from_chunk_root(chunk_root)

            connection = sqlite3.connect(index_path)
            try:
                table_names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                    ).fetchall()
                }
            finally:
                connection.close()

            self.assertIn("chunks", table_names)
            self.assertIn("chunk_fts", table_names)


if __name__ == "__main__":
    unittest.main()
