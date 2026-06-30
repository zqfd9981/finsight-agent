from __future__ import annotations

from finsight_agent.config.settings import load_settings
from finsight_agent.infra.external.cninfo_filings import CninfoFilingsAdapter
from finsight_agent.infra.external.sse_filings import SseFilingsAdapter

from .acquisition_service import DefaultDownloader, PdfCorpusAcquisitionService


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
