from __future__ import annotations

import gzip
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .acquisition_models import FilingRecord, SampleCompany
from .corpus_manifest import SampleUniverse
from .filing_filters import classify_filing
from .storage import build_output_path, write_status_snapshot


@dataclass(slots=True)
class IndexResult:
    """一次列表发现后的聚合结果。"""

    records: list[FilingRecord]


@dataclass(slots=True)
class DownloadResult:
    """一次下载批次的结果摘要。"""

    downloaded_count: int
    failed_count: int
    status_snapshot_path: Path


@dataclass(slots=True)
class CompanyDownloadSummary:
    """单家公司在一次采集批次中的下载摘要。"""

    company_code: str
    company_name: str
    candidate_count: int
    downloaded_count: int = 0
    failed_count: int = 0
    doc_types: set[str] = field(default_factory=set)
    failed_items: list[dict[str, str]] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        """转成可直接写入 JSON 快照的结构。"""

        return {
            "company_code": self.company_code,
            "company_name": self.company_name,
            "candidate_count": self.candidate_count,
            "downloaded_count": self.downloaded_count,
            "failed_count": self.failed_count,
            "doc_types": sorted(self.doc_types),
            "failed_items": list(self.failed_items),
        }


class DefaultDownloader:
    """默认的 PDF 下载器。"""

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self._timeout_seconds = timeout_seconds

    def download(self, url: str, destination: Path) -> Path:
        """下载并校验 PDF 内容，只允许真实 PDF 落盘。"""

        request = urllib.request.Request(
            url=url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/pdf,application/octet-stream,*/*",
                "Referer": "https://www.cninfo.com.cn/",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            payload = response.read()

        pdf_bytes = _extract_pdf_bytes(payload)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(pdf_bytes)
        return destination


class PdfCorpusAcquisitionService:
    """本地 PDF 语料采集服务。"""

    def __init__(
        self,
        sse_adapter,
        cninfo_adapter,
        downloader: DefaultDownloader | None = None,
        raw_filings_root: Path | None = None,
        status_root: Path | None = None,
    ) -> None:
        self._sse_adapter = sse_adapter
        self._cninfo_adapter = cninfo_adapter
        self._downloader = downloader or DefaultDownloader()
        self._raw_filings_root = raw_filings_root or Path("var/data/raw_filings")
        self._status_root = status_root or Path("var/data/corpus_status")

    def collect_filing_index(
        self,
        companies: list[SampleCompany],
        start_date: str,
        end_date: str,
    ) -> IndexResult:
        """发现并筛选指定公司范围内可进入语料库的披露文档。"""

        collected_records: list[FilingRecord] = []
        for company in companies:
            merged_records = self._collect_company_records(
                company=company,
                start_date=start_date,
                end_date=end_date,
            )
            for record in merged_records:
                if classify_filing(record) is None:
                    continue
                collected_records.append(record)
        return IndexResult(records=collected_records)

    def download_filings(
        self,
        companies: list[SampleCompany],
        start_date: str,
        end_date: str,
        snapshot_name: str = "download_status",
    ) -> DownloadResult:
        """对指定公司列表执行下载，并写出状态快照。"""

        index_result = self.collect_filing_index(
            companies=companies,
            start_date=start_date,
            end_date=end_date,
        )
        records_by_company = self._group_records_by_company(index_result.records)

        downloaded_count = 0
        failed_count = 0
        company_payloads: list[dict[str, object]] = []
        selected_codes = [company.company_code for company in companies]

        for company in companies:
            company_records = records_by_company.get(company.company_code, [])
            summary = CompanyDownloadSummary(
                company_code=company.company_code,
                company_name=company.company_name,
                candidate_count=len(company_records),
            )

            for record in company_records:
                classified = classify_filing(record)
                if classified is None:
                    continue

                destination = build_output_path(
                    root=self._raw_filings_root,
                    record=record,
                    normalized_doc_type=classified.normalized_doc_type,
                    report_year=classified.report_year,
                )
                try:
                    self._downloader.download(record.pdf_url, destination)
                except Exception as exc:
                    failed_count += 1
                    summary.failed_count += 1
                    summary.failed_items.append(
                        {
                            "title": record.title,
                            "publish_date": record.publish_date,
                            "pdf_url": record.pdf_url,
                            "error": str(exc),
                        }
                    )
                    continue

                downloaded_count += 1
                summary.downloaded_count += 1
                summary.doc_types.add(classified.normalized_doc_type)

            company_payloads.append(summary.to_payload())

        status_snapshot_path = write_status_snapshot(
            status_root=self._status_root,
            snapshot_name=snapshot_name,
            payload={
                "start_date": start_date,
                "end_date": end_date,
                "selected_company_count": len(companies),
                "company_codes": selected_codes,
                "downloaded_count": downloaded_count,
                "failed_count": failed_count,
                "companies": company_payloads,
            },
        )
        return DownloadResult(
            downloaded_count=downloaded_count,
            failed_count=failed_count,
            status_snapshot_path=status_snapshot_path,
        )

    def download_pilot_filings(
        self,
        sample_universe: SampleUniverse,
        pilot_company_count: int,
        start_date: str,
        end_date: str,
        company_codes: list[str] | None = None,
    ) -> DownloadResult:
        """按样本股池配置选择试点公司并执行下载。"""

        selected_companies = sample_universe.select_companies(
            limit=pilot_company_count,
            company_codes=company_codes,
        )
        return self.download_filings(
            companies=selected_companies,
            start_date=start_date,
            end_date=end_date,
            snapshot_name="pilot_download_status",
        )

    def _collect_company_records(
        self,
        company: SampleCompany,
        start_date: str,
        end_date: str,
    ) -> list[FilingRecord]:
        """按市场特征选择数据源，并对双源结果去重合并。"""

        # 沪市 / 科创板公司优先取 CNInfo。
        # 这样即便 SSE 列表存在，最终也会优先落到 CNInfo 的可下载 PDF。
        source_batches: list[list[FilingRecord]] = []
        if company.company_code.startswith("6"):
            source_batches.append(
                self._cninfo_adapter.list_filings(
                    company=company,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            source_batches.append(
                self._sse_adapter.list_filings(
                    company=company,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
        else:
            source_batches.append(
                self._cninfo_adapter.list_filings(
                    company=company,
                    start_date=start_date,
                    end_date=end_date,
                )
            )
            if self._sse_adapter is not None:
                source_batches.append(
                    self._sse_adapter.list_filings(
                        company=company,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )

        merged_records: list[FilingRecord] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for batch in source_batches:
            for record in batch:
                key = (
                    record.company_code,
                    record.publish_date,
                    _normalize_title_for_dedupe(record.title),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                merged_records.append(record)
        return merged_records

    def _group_records_by_company(
        self,
        records: list[FilingRecord],
    ) -> dict[str, list[FilingRecord]]:
        """把发现结果按公司代码分组，便于后续写公司级快照。"""

        grouped: dict[str, list[FilingRecord]] = {}
        for record in records:
            grouped.setdefault(record.company_code, []).append(record)
        return grouped


def _extract_pdf_bytes(payload: bytes) -> bytes:
    """校验下载内容是否为真实 PDF，同时识别 gzip 包装的挑战页。"""

    if payload.startswith(b"%PDF"):
        return payload

    if payload.startswith(b"\x1f\x8b"):
        unzipped = gzip.decompress(payload)
        if unzipped.startswith(b"%PDF"):
            return unzipped
        raise ValueError("下载内容是 gzip 包装的非 PDF 响应")

    if payload.lstrip().startswith(b"<"):
        raise ValueError("下载内容不是 PDF 响应")
    raise ValueError("下载内容不是有效 PDF")


def _normalize_title_for_dedupe(title: str) -> str:
    """把不同来源的标题归一化，便于做跨源去重。"""

    normalized = title.replace("：", ":").strip()
    if ":" in normalized:
        normalized = normalized.split(":", 1)[1]
    return "".join(normalized.split())
