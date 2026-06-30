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
from finsight_agent.capabilities.retrieval.service import (
    SparseRetrievalFacade,
    build_sparse_retrieval_facade,
)


class SparseRetrievalFacadeTest(unittest.TestCase):
    def test_search_returns_structured_sparse_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            chunk_root = temp_root / "chunked_filings"
            index_root = temp_root / "retrieval_index"

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

            facade = SparseRetrievalFacade.from_paths(
                chunked_filings_root=chunk_root,
                retrieval_index_root=index_root,
                min_original_hits=1,
            )

            result = facade.search("归母净利润", limit=5)

            self.assertEqual([hit.chunk_id for hit in result.hits], ["688126_child_000001"])
            self.assertEqual(result.hit_sources["688126_child_000001"], "rewritten")
            self.assertGreaterEqual(len(result.triggered_rewrite_queries), 1)

    def test_build_sparse_retrieval_facade_uses_repository_settings(self) -> None:
        facade = build_sparse_retrieval_facade()

        self.assertIsInstance(facade, SparseRetrievalFacade)


if __name__ == "__main__":
    unittest.main()
