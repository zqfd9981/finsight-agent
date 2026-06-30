from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid

from finsight_agent.config.settings import load_settings
from finsight_agent.infra.embeddings.bge_m3 import BgeM3EmbeddingProvider
from finsight_agent.infra.external.cninfo_filings import CninfoFilingsAdapter
from finsight_agent.infra.external.sse_filings import SseFilingsAdapter

from .acquisition_service import DefaultDownloader, PdfCorpusAcquisitionService
from .citation_builder import build_citation_record, build_parent_context
from .dense_index import DenseChunkIndex
from .dense_retrieval_service import DenseRetrievalService
from .fusion import rrf_fuse
from .models import (
    CitationRecord,
    DenseSearchFilters,
    EvidenceItem,
    RetrievalResult,
    RetrievalScoreBreakdown,
    SparseSearchFilters,
)
from .rerank import rerank_hits
from .sparse_index import SparseChunkIndex
from .sparse_retrieval_service import SparseRetrievalService


@dataclass(slots=True)
class SparseRetrievalFacade:
    """面向上层调用的首版 sparse retrieval facade。"""

    _index: SparseChunkIndex
    _service: SparseRetrievalService
    _chunked_filings_root: Path

    @classmethod
    def from_paths(
        cls,
        chunked_filings_root: Path,
        retrieval_index_root: Path,
        min_original_hits: int = 3,
    ) -> "SparseRetrievalFacade":
        index = SparseChunkIndex(retrieval_index_root / "sparse_chunks.db")
        service = SparseRetrievalService(index=index, min_original_hits=min_original_hits)
        return cls(
            _index=index,
            _service=service,
            _chunked_filings_root=chunked_filings_root,
        )

    def rebuild_index(self) -> int:
        return self._index.rebuild_from_chunk_root(self._chunked_filings_root)

    def search(
        self,
        query_text: str,
        limit: int = 10,
        filters: SparseSearchFilters | None = None,
    ):
        self.rebuild_index()
        return self._service.search(query_text=query_text, limit=limit, filters=filters)


@dataclass(slots=True)
class DenseRetrievalFacade:
    """面向上层调用的首版 dense retrieval facade。"""

    _index: DenseChunkIndex
    _service: DenseRetrievalService
    _chunked_filings_root: Path

    @classmethod
    def from_paths(
        cls,
        chunked_filings_root: Path,
        qdrant_path: Path | str,
        collection_name: str,
        embedding_provider: BgeM3EmbeddingProvider,
        min_original_hits: int = 3,
    ) -> "DenseRetrievalFacade":
        index = DenseChunkIndex(
            storage_path=qdrant_path,
            collection_name=collection_name,
            embedding_provider=embedding_provider,
        )
        service = DenseRetrievalService(index=index, min_original_hits=min_original_hits)
        return cls(
            _index=index,
            _service=service,
            _chunked_filings_root=chunked_filings_root,
        )

    def rebuild_index(self) -> int:
        return self._index.rebuild_from_chunk_root(self._chunked_filings_root)

    def search(
        self,
        query_text: str,
        limit: int = 10,
        filters: DenseSearchFilters | None = None,
    ):
        self.rebuild_index()
        return self._service.search(query_text=query_text, limit=limit, filters=filters)

    def close(self) -> None:
        """关闭 dense facade 关联的本地 Qdrant 连接。"""

        self._index.close()


@dataclass(slots=True)
class RetrievalFacade:
    """统一装配 sparse + dense + fusion + rerank 的 facade。"""

    sparse_facade: SparseRetrievalFacade
    dense_facade: DenseRetrievalFacade

    def retrieve_evidence(
        self,
        raw_query: str,
        limit: int = 5,
        company_code: str | None = None,
        doc_type: str | None = None,
        report_year: int | None = None,
    ) -> RetrievalResult:
        sparse_filters = SparseSearchFilters(
            company_code=company_code,
            doc_type=doc_type,
        )
        dense_filters = DenseSearchFilters(
            company_code=company_code,
            doc_type=doc_type,
            report_year=report_year,
        )

        sparse_result = self.sparse_facade.search(
            query_text=raw_query,
            limit=max(limit, 10),
            filters=sparse_filters,
        )
        dense_result = self.dense_facade.search(
            query_text=raw_query,
            limit=max(limit, 10),
            filters=dense_filters,
        )

        fused_hits = rrf_fuse(sparse_result.hits, dense_result.hits)
        reranked_hits = rerank_hits(fused_hits, raw_query, top_n=max(limit, 10))

        evidence_items: list[EvidenceItem] = []
        for rank, hit in enumerate(reranked_hits[:limit], start=1):
            citation = build_citation_record(
                document_id=hit.document_id,
                page_start=hit.page_start,
                page_end=hit.page_end,
                page_anchor=hit.page_anchor,
            )
            evidence_items.append(
                EvidenceItem(
                    evidence_id=f"evidence_{rank:04d}",
                    rank=rank,
                    support_strength=_classify_support_strength(hit.rerank_score),
                    matched_chunk_id=hit.chunk_id,
                    matched_parent_id=hit.parent_id,
                    excerpt=hit.chunk_text,
                    parent_context=build_parent_context(hit.chunk_text),
                    citation=citation,
                    retrieval_scores=RetrievalScoreBreakdown(
                        sparse_score=hit.sparse_score,
                        dense_score=hit.dense_score,
                        rrf_score=hit.rrf_score,
                        rerank_score=hit.rerank_score,
                    ),
                    company_code=hit.company_code,
                    company_name=hit.company_name,
                    doc_type=hit.doc_type,
                    section_path=list(hit.section_path),
                )
            )

        retrieval_notes: list[str] = []
        if sparse_result.triggered_rewrite_queries:
            retrieval_notes.append(
                f"sparse rewrite: {', '.join(sparse_result.triggered_rewrite_queries)}"
            )
        if dense_result.rewrite_queries:
            retrieval_notes.append(
                f"dense rewrite: {', '.join(dense_result.rewrite_queries)}"
            )

        return RetrievalResult(
            request_id=str(uuid.uuid4()),
            normalized_claim=raw_query.strip(),
            evidence_items=evidence_items,
            retrieval_notes=retrieval_notes,
        )

    def close(self) -> None:
        """关闭底层 facade 持有的本地资源。"""

        self.dense_facade.close()


def build_pdf_corpus_acquisition_service() -> PdfCorpusAcquisitionService:
    settings = load_settings()
    return PdfCorpusAcquisitionService(
        sse_adapter=SseFilingsAdapter(),
        cninfo_adapter=CninfoFilingsAdapter(),
        downloader=DefaultDownloader(),
        raw_filings_root=settings.retrieval.raw_filings_root,
        status_root=settings.retrieval.status_root,
    )


def build_sparse_retrieval_facade() -> SparseRetrievalFacade:
    settings = load_settings()
    return SparseRetrievalFacade.from_paths(
        chunked_filings_root=settings.retrieval.chunked_filings_root,
        retrieval_index_root=settings.retrieval.retrieval_index_root,
    )


def build_dense_retrieval_facade() -> DenseRetrievalFacade:
    settings = load_settings()
    embedding_provider = BgeM3EmbeddingProvider(
        model_name=settings.retrieval.dense.embedding_model_name,
        model_version=settings.retrieval.dense.embedding_model_version,
    )
    return DenseRetrievalFacade.from_paths(
        chunked_filings_root=settings.retrieval.chunked_filings_root,
        qdrant_path=settings.retrieval.dense.qdrant_path,
        collection_name=settings.retrieval.dense.qdrant_collection_name,
        embedding_provider=embedding_provider,
    )


def build_retrieval_facade() -> RetrievalFacade:
    return RetrievalFacade(
        sparse_facade=build_sparse_retrieval_facade(),
        dense_facade=build_dense_retrieval_facade(),
    )


def _classify_support_strength(score: float) -> str:
    if score >= 0.8:
        return "strong"
    if score >= 0.5:
        return "partial"
    if score > 0:
        return "weak"
    return "unsupported"
