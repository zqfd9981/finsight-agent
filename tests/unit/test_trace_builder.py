from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.dense_retrieval_service import DenseSearchResult
from finsight_agent.capabilities.retrieval.models import RetrievalResult, RetrievalTrace
from finsight_agent.capabilities.retrieval.sparse_retrieval_service import SparseSearchResult
from finsight_agent.capabilities.retrieval.trace_builder import (
    attach_trace_to_result,
    build_retrieval_notes,
    build_retrieval_trace,
)


class RetrievalTraceBuilderTest(unittest.TestCase):
    def test_retrieval_result_accepts_structured_trace(self) -> None:
        trace = RetrievalTrace(
            original_query="原始问题",
            normalized_query="归一化问题",
            rewrite_queries=["改写问题A", "改写问题B"],
            sparse_hit_count=3,
            dense_hit_count=4,
            fused_hit_count=5,
            reranked_hit_count=2,
            final_evidence_count=2,
            sparse_rewrite_triggered=True,
            dense_rewrite_triggered=False,
            parent_expand_attempted=True,
            parent_expand_fallback_count=1,
        )

        result = RetrievalResult(
            request_id="req-1",
            normalized_claim="归一化陈述",
            retrieval_trace=trace,
        )

        self.assertIs(result.retrieval_trace, trace)
        self.assertEqual(result.retrieval_trace.normalized_query, "归一化问题")

    def test_trace_fields_are_accessible(self) -> None:
        trace = RetrievalTrace(
            original_query="原始问题",
            normalized_query="归一化问题",
            rewrite_queries=[],
            sparse_hit_count=1,
            dense_hit_count=2,
            fused_hit_count=2,
            reranked_hit_count=1,
            final_evidence_count=1,
            sparse_rewrite_triggered=False,
            dense_rewrite_triggered=True,
            parent_expand_attempted=False,
            parent_expand_fallback_count=0,
        )

        self.assertEqual(trace.final_evidence_count, 1)
        self.assertTrue(trace.dense_rewrite_triggered)
        self.assertEqual(trace.parent_expand_fallback_count, 0)

    def test_build_trace_merges_rewrite_queries_and_counts(self) -> None:
        sparse_result = SparseSearchResult(
            hits=[],
            triggered_rewrite_queries=["归属于上市公司股东的净利润"],
        )
        dense_result = DenseSearchResult(
            hits=[],
            original_hit_count=1,
            rewrite_queries=["归属于上市公司股东的净利润", "营业收入"],
        )

        trace = build_retrieval_trace(
            original_query="归母净利润",
            normalized_query="归母净利润",
            sparse_result=sparse_result,
            dense_result=dense_result,
            fused_hit_count=4,
            reranked_hit_count=3,
            final_evidence_count=2,
            parent_expand_attempted=True,
            parent_expand_fallback_count=1,
        )

        self.assertEqual(
            trace.rewrite_queries,
            ["归属于上市公司股东的净利润", "营业收入"],
        )
        self.assertTrue(trace.sparse_rewrite_triggered)
        self.assertTrue(trace.dense_rewrite_triggered)
        self.assertEqual(trace.fused_hit_count, 4)
        self.assertEqual(trace.parent_expand_fallback_count, 1)

    def test_build_notes_only_emits_present_events(self) -> None:
        notes = build_retrieval_notes(
            sparse_result=SparseSearchResult(
                hits=[],
                triggered_rewrite_queries=["营业收入"],
            ),
            dense_result=DenseSearchResult(
                hits=[],
                original_hit_count=0,
                rewrite_queries=[],
            ),
            parent_expand_fallback_count=2,
        )

        self.assertEqual(
            notes,
            [
                "sparse rewrite: 营业收入",
                "parent expand fallback used for 2 evidence item(s)",
            ],
        )

    def test_attach_trace_to_result_updates_result_in_place(self) -> None:
        result = RetrievalResult(
            request_id="req-1",
            normalized_claim="测试问题",
        )
        trace = RetrievalTrace(
            original_query="测试问题",
            normalized_query="测试问题",
            rewrite_queries=[],
            sparse_hit_count=0,
            dense_hit_count=0,
            fused_hit_count=0,
            reranked_hit_count=0,
            final_evidence_count=0,
            sparse_rewrite_triggered=False,
            dense_rewrite_triggered=False,
            parent_expand_attempted=False,
            parent_expand_fallback_count=0,
        )

        updated = attach_trace_to_result(
            result=result,
            trace=trace,
            notes=["dense rewrite: 营业收入"],
        )

        self.assertIs(updated, result)
        self.assertIs(updated.retrieval_trace, trace)
        self.assertEqual(updated.retrieval_notes, ["dense rewrite: 营业收入"])


if __name__ == "__main__":
    unittest.main()
