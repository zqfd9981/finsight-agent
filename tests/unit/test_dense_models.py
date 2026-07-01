from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.models import DenseHit, DenseSearchRequest
from finsight_agent.config.settings import load_settings


class DenseModelsTest(unittest.TestCase):
    def test_dense_request_and_hit_fields_exist(self) -> None:
        request = DenseSearchRequest(query_text="净利润", limit=5, company_code="002371")
        self.assertEqual(request.query_text, "净利润")
        self.assertEqual(request.limit, 5)
        self.assertEqual(request.company_code, "002371")

        hit = DenseHit(
            chunk_id="c1",
            document_id="d1",
            parent_id="p1",
            company_code="002371",
            company_name="北方华创",
            doc_type="annual_report",
            report_year=2025,
            publish_date="2025-04-25",
            page_start=3,
            page_end=4,
            page_anchor=3,
            section_path=["管理层讨论与分析"],
            chunk_text="净利润同比增长",
            dense_score=0.91,
            query_variant="original",
        )
        self.assertEqual(hit.chunk_id, "c1")
        self.assertEqual(hit.query_variant, "original")

    def test_settings_include_dense_paths(self) -> None:
        settings = load_settings()
        self.assertIsInstance(settings.control_plane.root, Path)
        self.assertEqual(settings.retrieval.dense.qdrant_collection_name, "finsight_pdf_chunks_v1")
        self.assertEqual(settings.retrieval.dense.embedding_model_name, "bge-m3")
        self.assertEqual(settings.retrieval.dense.embedding_model_version, "bge-m3-v1")
        self.assertEqual(settings.retrieval.dense.qdrant_path.name, "qdrant")


if __name__ == "__main__":
    unittest.main()
