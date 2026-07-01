from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.citation_builder import build_parent_context
from finsight_agent.capabilities.retrieval.evidence_assembly import (
    assemble_evidence_item,
    classify_support_strength,
)
from finsight_agent.capabilities.retrieval.models import RerankedHit
from finsight_agent.capabilities.retrieval.parent_context_loader import ParentChunkRecord


class EvidenceAssemblyTest(unittest.TestCase):
    def test_assemble_uses_real_parent_context_when_record_exists(self) -> None:
        hit = RerankedHit(
            chunk_id="child-1",
            document_id="doc-1",
            parent_id="parent-1",
            company_code="600000",
            company_name="浦发银行",
            doc_type="annual_report",
            report_year="2025",
            publish_date="2025-03-28",
            page_start=12,
            page_end=13,
            page_anchor=12,
            section_path=["管理层讨论与分析"],
            chunk_text="  子块  文本\n包含  关键  证据  ",
            sparse_score=4.2,
            dense_score=0.71,
            rrf_score=0.09,
            rerank_score=0.92,
            matched_by=["sparse", "dense"],
        )
        parent_record = ParentChunkRecord(
            chunk_id="parent-1",
            chunk_text="真实 parent 上下文全文",
            page_start=10,
            page_end=14,
            section_path=["管理层讨论与分析"],
        )

        evidence, used_fallback = assemble_evidence_item(
            rank=1,
            hit=hit,
            parent_record=parent_record,
        )

        self.assertFalse(used_fallback)
        self.assertEqual(evidence.evidence_id, "evidence_0001")
        self.assertEqual(evidence.parent_context, "真实 parent 上下文全文")
        self.assertEqual(evidence.excerpt, "子块 文本 包含 关键 证据")
        self.assertEqual(evidence.citation.document_id, "doc-1")
        self.assertEqual(evidence.retrieval_scores.sparse_score, 4.2)
        self.assertEqual(evidence.retrieval_scores.dense_score, 0.71)
        self.assertEqual(evidence.retrieval_scores.rrf_score, 0.09)
        self.assertEqual(evidence.retrieval_scores.rerank_score, 0.92)

    def test_assemble_uses_fallback_parent_context_when_record_missing(self) -> None:
        hit = RerankedHit(
            chunk_id="child-2",
            document_id="doc-2",
            parent_id="parent-missing",
            company_code="000001",
            company_name="平安银行",
            doc_type="annual_report",
            report_year="2025",
            publish_date="2025-03-20",
            page_start=5,
            page_end=5,
            page_anchor=5,
            section_path=["主营业务"],
            chunk_text="  fallback  内容  ",
            sparse_score=1.1,
            dense_score=0.25,
            rrf_score=0.03,
            rerank_score=0.18,
            matched_by=["sparse"],
        )

        evidence, used_fallback = assemble_evidence_item(
            rank=2,
            hit=hit,
            parent_record=None,
        )

        self.assertTrue(used_fallback)
        self.assertEqual(evidence.parent_context, build_parent_context(hit.chunk_text))
        self.assertEqual(evidence.excerpt, "fallback 内容")

    def test_classify_support_strength_returns_strong_for_high_scores(self) -> None:
        hit = RerankedHit(
            chunk_id="child-3",
            document_id="doc-3",
            parent_id="parent-3",
            company_code="300750",
            company_name="宁德时代",
            doc_type="annual_report",
            report_year="2025",
            publish_date="2025-04-10",
            page_start=20,
            page_end=21,
            page_anchor=20,
            section_path=["经营情况讨论与分析"],
            chunk_text="高相关证据",
            sparse_score=3.0,
            dense_score=0.88,
            rrf_score=0.12,
            rerank_score=0.91,
            matched_by=["sparse", "dense"],
        )

        self.assertEqual(classify_support_strength(hit), "strong")

    def test_classify_support_strength_returns_weak_for_low_scores(self) -> None:
        hit = RerankedHit(
            chunk_id="child-4",
            document_id="doc-4",
            parent_id=None,
            company_code="002594",
            company_name="比亚迪",
            doc_type="annual_report",
            report_year="2025",
            publish_date="2025-03-26",
            page_start=30,
            page_end=30,
            page_anchor=30,
            section_path=["风险因素"],
            chunk_text="弱相关证据",
            sparse_score=0.2,
            dense_score=0.08,
            rrf_score=0.01,
            rerank_score=0.09,
            matched_by=["sparse"],
        )

        self.assertEqual(classify_support_strength(hit), "weak")


if __name__ == "__main__":
    unittest.main()
