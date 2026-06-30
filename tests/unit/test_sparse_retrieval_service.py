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

from finsight_agent.capabilities.retrieval.parsing_models import ChunkRecord
from finsight_agent.capabilities.retrieval.parsed_storage import write_chunk_artifact
from finsight_agent.capabilities.retrieval.sparse_index import SparseChunkIndex
from finsight_agent.capabilities.retrieval.sparse_retrieval_service import (
    SparseRetrievalService,
)


class SparseRetrievalServiceTest(unittest.TestCase):
    def test_search_prefers_original_query_hits_without_triggering_alias_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            chunk_root = temp_root / "chunked_filings"
            index_path = temp_root / "retrieval_index" / "sparse_chunks.db"

            write_chunk_artifact(
                root=chunk_root,
                document_id="002371_北方华创_annual_report_2025_20250425",
                parents=[],
                children=[
                    ChunkRecord(
                        chunk_id="002371_child_000001",
                        document_id="002371_北方华创_annual_report_2025_20250425",
                        chunk_level="child",
                        parent_id="002371_parent_000001",
                        chunk_text="本期营业收入增长主要来自半导体设备业务放量。",
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
                    "document_id": "002371_北方华创_annual_report_2025_20250425",
                    "chunker_version": "chunker_v1",
                    "parent_count": 0,
                    "child_count": 1,
                    "warnings": [],
                    "generated_at": "2026-06-30T00:00:00Z",
                },
            )

            index = SparseChunkIndex(index_path=index_path)
            index.rebuild_from_chunk_root(chunk_root)
            service = SparseRetrievalService(index=index, min_original_hits=1)

            result = service.search("营业收入", limit=5)

            self.assertEqual([hit.chunk_id for hit in result.hits], ["002371_child_000001"])
            self.assertEqual(result.triggered_rewrite_queries, [])
            self.assertEqual(result.hit_sources["002371_child_000001"], "original")

    def test_search_uses_alias_queries_only_when_original_hits_are_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            chunk_root = temp_root / "chunked_filings"
            index_path = temp_root / "retrieval_index" / "sparse_chunks.db"

            write_chunk_artifact(
                root=chunk_root,
                document_id="688126_沪硅产业_semiannual_report_2024_20240830",
                parents=[],
                children=[
                    ChunkRecord(
                        chunk_id="688126_child_000001",
                        document_id="688126_沪硅产业_semiannual_report_2024_20240830",
                        chunk_level="child",
                        parent_id="688126_parent_000001",
                        chunk_text="归属于上市公司股东的净利润较上年同期明显下降。",
                        page_start=6,
                        page_end=6,
                        page_anchor=6,
                        section_path=["(一) 主要会计数据"],
                        element_ids=["e1"],
                        order_in_document=1,
                        source_parser="pdfplumber",
                        created_from_parser_version="pdfplumber_v1",
                    )
                ],
                chunk_report={
                    "document_id": "688126_沪硅产业_semiannual_report_2024_20240830",
                    "chunker_version": "chunker_v1",
                    "parent_count": 0,
                    "child_count": 1,
                    "warnings": [],
                    "generated_at": "2026-06-30T00:00:00Z",
                },
            )

            index = SparseChunkIndex(index_path=index_path)
            index.rebuild_from_chunk_root(chunk_root)
            service = SparseRetrievalService(index=index, min_original_hits=1)

            result = service.search("归母净利润", limit=5)

            self.assertEqual([hit.chunk_id for hit in result.hits], ["688126_child_000001"])
            self.assertGreaterEqual(len(result.triggered_rewrite_queries), 1)
            self.assertEqual(result.hit_sources["688126_child_000001"], "rewritten")


if __name__ == "__main__":
    unittest.main()
