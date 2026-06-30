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

from finsight_agent.capabilities.retrieval.dense_index import DenseChunkIndex
from finsight_agent.capabilities.retrieval.dense_retrieval_service import DenseRetrievalService
from finsight_agent.capabilities.retrieval.parsing_models import ChunkRecord
from finsight_agent.capabilities.retrieval.parsed_storage import write_chunk_artifact
from finsight_agent.infra.embeddings.bge_m3 import BgeM3EmbeddingProvider


class DenseRetrievalServiceTest(unittest.TestCase):
    def test_dense_service_prefers_original_query_and_can_trigger_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            chunk_root = temp_root / "chunked_filings"
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
                        section_path=["主要会计数据"],
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

            index = DenseChunkIndex(
                storage_path=":memory:",
                collection_name="finsight_pdf_chunks_v1",
                embedding_provider=BgeM3EmbeddingProvider(),
            )
            try:
                index.rebuild_from_chunk_root(chunk_root)
                service = DenseRetrievalService(index=index, min_original_hits=2)

                result = service.search("归母净利润", limit=5)

                self.assertEqual(len(result.hits), 1)
                self.assertGreaterEqual(len(result.rewrite_queries), 1)
                self.assertEqual(result.rewrite_policy_version, "alias_v1")
            finally:
                index.close()


if __name__ == "__main__":
    unittest.main()
