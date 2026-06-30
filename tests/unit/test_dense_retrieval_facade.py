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
    DenseRetrievalFacade,
    RetrievalFacade,
    SparseRetrievalFacade,
)
from finsight_agent.infra.embeddings.bge_m3 import BgeM3EmbeddingProvider


class DenseRetrievalFacadeTest(unittest.TestCase):
    def test_facade_returns_retrieval_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            chunk_root = temp_root / "chunked_filings"
            retrieval_root = temp_root / "retrieval_index"
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
                        chunk_text="净利润同比增长，主要来自刻蚀设备收入提升。",
                        page_start=42,
                        page_end=42,
                        page_anchor=42,
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

            sparse_facade = SparseRetrievalFacade.from_paths(
                chunked_filings_root=chunk_root,
                retrieval_index_root=retrieval_root,
                min_original_hits=1,
            )
            dense_facade = DenseRetrievalFacade.from_paths(
                chunked_filings_root=chunk_root,
                qdrant_path=":memory:",
                collection_name="finsight_pdf_chunks_v1",
                embedding_provider=BgeM3EmbeddingProvider(),
                min_original_hits=1,
            )

            facade = RetrievalFacade(
                sparse_facade=sparse_facade,
                dense_facade=dense_facade,
            )
            try:
                result = facade.retrieve_evidence("净利润增长", limit=3, company_code="002371")

                self.assertTrue(result.request_id)
                self.assertEqual(result.normalized_claim, "净利润增长")
                self.assertGreaterEqual(len(result.evidence_items), 1)
            finally:
                facade.close()


if __name__ == "__main__":
    unittest.main()
