from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import uuid

from finsight_agent.config.settings import load_settings
from finsight_agent.infra.embeddings.bge_m3 import BgeM3EmbeddingProvider
from finsight_agent.infra.external.cninfo_filings import CninfoFilingsAdapter
from finsight_agent.infra.external.sse_filings import SseFilingsAdapter

from .acquisition_service import DefaultDownloader, PdfCorpusAcquisitionService
from .dense_index import DenseChunkIndex
from .dense_retrieval_service import DenseRetrievalService
from .evidence_assembly import assemble_evidence_item
from .fusion import rrf_fuse
from .models import DenseSearchFilters, RetrievalResult, SparseSearchFilters
from .parent_context_loader import ParentContextLoader
from .rerank import rerank_hits
from .sparse_index import SparseChunkIndex
from .sparse_retrieval_service import SparseRetrievalService
from .trace_builder import (
    attach_trace_to_result,
    build_retrieval_notes,
    build_retrieval_trace,
)


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
        # 索引由调用方显式 rebuild_index() 维护，搜索时不重建（与 DenseRetrievalFacade 一致）
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
        return self._service.search(query_text=query_text, limit=limit, filters=filters)

    def close(self) -> None:
        """关闭 dense facade 关联的本地 Qdrant 连接。"""

        self._index.close()


@dataclass(slots=True)
class RetrievalFacade:
    """统一装配 sparse + dense + fusion + rerank 的 facade。"""

    sparse_facade: SparseRetrievalFacade
    dense_facade: DenseRetrievalFacade
    parent_loader: ParentContextLoader

    def retrieve_evidence(
        self,
        raw_query: str,
        limit: int = 5,
        company_code: str | None = None,
        doc_type: str | None = None,
        report_year: int | None = None,
    ) -> RetrievalResult:
        normalized_query = raw_query.strip()
        search_limit = max(limit, 10)
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
            limit=search_limit,
            filters=sparse_filters,
        )
        dense_result = self.dense_facade.search(
            query_text=raw_query,
            limit=search_limit,
            filters=dense_filters,
        )

        fused_hits = rrf_fuse(sparse_result.hits, dense_result.hits)
        reranked_hits = rerank_hits(fused_hits, raw_query, top_n=search_limit)

        evidence_items = []
        parent_expand_fallback_count = 0
        for rank, hit in enumerate(reranked_hits[:limit], start=1):
            parent_record = self.parent_loader.load_parent(
                document_id=hit.document_id,
                parent_id=hit.parent_id,
            )
            evidence, used_fallback = assemble_evidence_item(
                rank=rank,
                hit=hit,
                parent_record=parent_record,
            )
            evidence_items.append(evidence)
            if used_fallback:
                parent_expand_fallback_count += 1

        retrieval_trace = build_retrieval_trace(
            original_query=raw_query,
            normalized_query=normalized_query,
            sparse_result=sparse_result,
            dense_result=dense_result,
            fused_hit_count=len(fused_hits),
            reranked_hit_count=len(reranked_hits),
            final_evidence_count=len(evidence_items),
            parent_expand_attempted=bool(evidence_items),
            parent_expand_fallback_count=parent_expand_fallback_count,
        )
        retrieval_notes = build_retrieval_notes(
            sparse_result=sparse_result,
            dense_result=dense_result,
            parent_expand_fallback_count=parent_expand_fallback_count,
        )

        result = RetrievalResult(
            request_id=str(uuid.uuid4()),
            normalized_claim=normalized_query,
            evidence_items=evidence_items,
        )
        return attach_trace_to_result(
            result=result,
            trace=retrieval_trace,
            notes=retrieval_notes,
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
        use_real_model=True,
    )
    return DenseRetrievalFacade.from_paths(
        chunked_filings_root=settings.retrieval.chunked_filings_root,
        qdrant_path=settings.retrieval.dense.qdrant_path,
        collection_name=settings.retrieval.dense.qdrant_collection_name,
        embedding_provider=embedding_provider,
    )


def build_retrieval_facade() -> RetrievalFacade:
    settings = load_settings()
    return RetrievalFacade(
        sparse_facade=build_sparse_retrieval_facade(),
        dense_facade=build_dense_retrieval_facade(),
        parent_loader=ParentContextLoader(settings.retrieval.chunked_filings_root),
    )
