from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from finsight_agent.config.settings import load_settings
from finsight_agent.infra.external.cninfo_filings import CninfoFilingsAdapter
from finsight_agent.infra.external.sse_filings import SseFilingsAdapter

from .acquisition_service import DefaultDownloader, PdfCorpusAcquisitionService
from .models import SparseSearchFilters
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
        """基于仓库路径构造 facade，并在首次调用前重建索引。"""

        index = SparseChunkIndex(retrieval_index_root / "sparse_chunks.db")
        service = SparseRetrievalService(
            index=index,
            min_original_hits=min_original_hits,
        )
        return cls(
            _index=index,
            _service=service,
            _chunked_filings_root=chunked_filings_root,
        )

    def rebuild_index(self) -> int:
        """从当前 chunk 产物目录全量重建 SQLite 稀疏索引。"""

        return self._index.rebuild_from_chunk_root(self._chunked_filings_root)

    def search(
        self,
        query_text: str,
        limit: int = 10,
        filters: SparseSearchFilters | None = None,
    ):
        """先确保索引可用，再执行原 query 优先的 sparse 检索。"""

        self.rebuild_index()
        return self._service.search(
            query_text=query_text,
            limit=limit,
            filters=filters,
        )


def build_pdf_corpus_acquisition_service() -> PdfCorpusAcquisitionService:
    """按仓库配置构造默认 PDF 语料采集服务实例。"""

    settings = load_settings()
    return PdfCorpusAcquisitionService(
        sse_adapter=SseFilingsAdapter(),
        cninfo_adapter=CninfoFilingsAdapter(),
        downloader=DefaultDownloader(),
        raw_filings_root=settings.retrieval.raw_filings_root,
        status_root=settings.retrieval.status_root,
    )


def build_sparse_retrieval_facade() -> SparseRetrievalFacade:
    """按仓库配置构造默认 sparse retrieval facade。"""

    settings = load_settings()
    return SparseRetrievalFacade.from_paths(
        chunked_filings_root=settings.retrieval.chunked_filings_root,
        retrieval_index_root=settings.retrieval.retrieval_index_root,
    )
