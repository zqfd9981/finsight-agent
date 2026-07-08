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


class _StubReranker:
    def rerank(self, *, query, profile, candidates, top_n=None):
        del query, profile, top_n
        ranked = []
        for candidate in candidates:
            score = 0.95 if "钢铁" in candidate.text else 0.10
            ranked.append({"id": candidate.id, "score": score, "keep": True})
        return ranked


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

    def test_rerank_hits_can_use_pluggable_reranker(self) -> None:
        fused = rrf_fuse(
            [
                SparseChunkHit(
                    chunk_id="steel",
                    document_id="d1",
                    parent_id="p1",
                    company_code="000001",
                    company_name="钢铁公司",
                    doc_type="annual_report",
                    report_year="2025",
                    publish_date="2025-04-25",
                    page_start=1,
                    page_end=1,
                    page_anchor=1,
                    section_path=["管理层讨论与分析"],
                    chunk_text="钢铁行业产能去化推动盈利修复。",
                    bm25_score=1.0,
                ),
                SparseChunkHit(
                    chunk_id="pig",
                    document_id="d2",
                    parent_id="p2",
                    company_code="000002",
                    company_name="养殖公司",
                    doc_type="annual_report",
                    report_year="2025",
                    publish_date="2025-04-25",
                    page_start=2,
                    page_end=2,
                    page_anchor=2,
                    section_path=["管理层讨论与分析"],
                    chunk_text="生猪产能去化进入倒计时。",
                    bm25_score=0.9,
                ),
            ],
            [],
        )

        reranked = rerank_hits(
            fused,
            "钢铁新一轮产能去化到底是行政命令还是市场化倒逼？",
            top_n=5,
            reranker=_StubReranker(),
        )

        self.assertEqual(reranked[0].chunk_id, "steel")
        self.assertGreater(reranked[0].rerank_score, reranked[1].rerank_score)


if __name__ == "__main__":
    unittest.main()
