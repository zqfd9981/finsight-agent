from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.fusion import rrf_fuse
from finsight_agent.capabilities.retrieval.models import DenseHit, SparseChunkHit
from finsight_agent.capabilities.retrieval.rerank import rerank_hits


class DenseFusionAndRerankTest(unittest.TestCase):
    def test_rrf_fuse_deduplicates_by_chunk_id(self) -> None:
        sparse_hits = [
            SparseChunkHit(
                chunk_id="c1",
                document_id="d1",
                parent_id="p1",
                company_code="002371",
                company_name="北方华创",
                doc_type="annual_report",
                report_year="2025",
                publish_date="2025-04-25",
                page_start=1,
                page_end=1,
                page_anchor=1,
                section_path=["管理层讨论与分析"],
                chunk_text="净利润增长",
                bm25_score=1.0,
            )
        ]
        dense_hits = [
            DenseHit(
                chunk_id="c1",
                document_id="d1",
                parent_id="p1",
                company_code="002371",
                company_name="北方华创",
                doc_type="annual_report",
                report_year=2025,
                publish_date="2025-04-25",
                page_start=1,
                page_end=1,
                page_anchor=1,
                section_path=["管理层讨论与分析"],
                chunk_text="净利润增长",
                dense_score=0.9,
            )
        ]

        fused = rrf_fuse(sparse_hits, dense_hits)
        self.assertEqual(len(fused), 1)
        self.assertEqual(fused[0].chunk_id, "c1")
        self.assertIn("sparse", fused[0].matched_by)
        self.assertIn("dense", fused[0].matched_by)

    def test_rerank_hits_returns_sorted_hits(self) -> None:
        fused = rrf_fuse(
            [
                SparseChunkHit(
                    chunk_id="c1",
                    document_id="d1",
                    parent_id="p1",
                    company_code="002371",
                    company_name="北方华创",
                    doc_type="annual_report",
                    report_year="2025",
                    publish_date="2025-04-25",
                    page_start=1,
                    page_end=1,
                    page_anchor=1,
                    section_path=["管理层讨论与分析"],
                    chunk_text="净利润增长原因",
                    bm25_score=1.0,
                )
            ],
            [],
        )
        reranked = rerank_hits(fused, "净利润增长", top_n=5)
        self.assertEqual(len(reranked), 1)
        self.assertGreater(reranked[0].rerank_score, 0)


if __name__ == "__main__":
    unittest.main()
