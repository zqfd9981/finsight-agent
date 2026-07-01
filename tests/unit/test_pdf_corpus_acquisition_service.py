from __future__ import annotations

import sys
import tempfile
import unittest
import gzip
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from finsight_agent.capabilities.retrieval.acquisition_models import (
    FilingRecord,
    SampleCompany,
)
from finsight_agent.capabilities.retrieval.acquisition_service import (
    PdfCorpusAcquisitionService,
    _extract_pdf_bytes,
)
from finsight_agent.capabilities.retrieval.corpus_manifest import SampleUniverse
from finsight_agent.capabilities.retrieval.service import (
    build_pdf_corpus_acquisition_service,
)
from finsight_agent.infra.external.cninfo_filings import (
    CninfoFilingsAdapter,
    normalize_cninfo_record,
)
from finsight_agent.infra.external.sse_filings import (
    SseFilingsAdapter,
    normalize_sse_record,
)


class SseAdapterNormalizationTest(unittest.TestCase):
    def test_normalize_sse_record_maps_fields_to_internal_shape(self) -> None:
        raw_item = {
            "BULLETIN_TYPE": "L012",
            "SECURITY_CODE": "688981",
            "TITLE": "2024年年度报告",
            "SSEDATE": "2025-03-29",
            "URL": "/disclosure/listedinfo/announcement/c/new/2025-03-29/123.pdf",
        }

        record = normalize_sse_record(raw_item, company_name="中芯国际")

        self.assertEqual(record.source_name, "sse")
        self.assertEqual(record.company_code, "688981")
        self.assertEqual(record.company_name, "中芯国际")
        self.assertEqual(record.publish_date, "2025-03-29")
        self.assertTrue(record.pdf_url.startswith("https://"))

    def test_list_filings_uses_expected_query_params_and_flattens_grouped_result(self) -> None:
        company = SampleCompany(
            company_code="688981",
            company_name="中芯国际",
            segment="manufacturing_idm",
            subsegment="foundry",
            priority="high",
        )
        captured_request: dict[str, object] = {}

        class FakeFetcher:
            # 用可注入抓取器锁定查询参数，避免真实网络耦合进单测。
            def get_json(self, url: str, params: dict[str, object], headers: dict[str, str]):
                captured_request["url"] = url
                captured_request["params"] = dict(params)
                captured_request["headers"] = dict(headers)
                return {
                    "result": [
                        [
                            {
                                "BULLETIN_TYPE": "L023",
                                "SECURITY_CODE": "688981",
                                "SECURITY_NAME": "中芯国际",
                                "TITLE": "中芯国际2024年年度报告",
                                "SSEDATE": "2025-03-28",
                                "URL": "/disclosure/listedinfo/announcement/c/new/2025-03-28/688981_20250328.pdf",
                            }
                        ],
                        [
                            {
                                "BULLETIN_TYPE": "L023",
                                "SECURITY_CODE": "688981",
                                "SECURITY_NAME": "中芯国际",
                                "TITLE": "中芯国际2025年半年度报告",
                                "SSEDATE": "2025-08-29",
                                "URL": "/disclosure/listedinfo/announcement/c/new/2025-08-29/688981_20250829.pdf",
                            }
                        ],
                    ]
                }

        adapter = SseFilingsAdapter(fetcher=FakeFetcher())

        records = adapter.list_filings(
            company=company,
            start_date="2024-01-01",
            end_date="2025-12-31",
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].title, "中芯国际2024年年度报告")
        self.assertEqual(records[1].title, "中芯国际2025年半年度报告")
        self.assertEqual(
            captured_request["url"],
            "https://query.sse.com.cn/security/stock/queryCompanyBulletinNew.do",
        )
        self.assertEqual(captured_request["params"]["SECURITY_CODE"], "688981")
        self.assertEqual(captured_request["params"]["START_DATE"], "2024-01-01")
        self.assertEqual(captured_request["params"]["END_DATE"], "2025-12-31")
        self.assertEqual(captured_request["params"]["isPagination"], "true")


class CninfoAdapterNormalizationTest(unittest.TestCase):
    def test_normalize_cninfo_record_maps_fields_to_internal_shape(self) -> None:
        raw_item = {
            "secCode": "002371",
            "secName": "北方华创",
            "announcementTitle": "<em>北方华创</em>：关于签订重大合同的公告",
            "announcementTime": 1744905600000,
            "adjunctUrl": "finalpage/2025-04-18/PDF.pdf",
            "announcementId": "1234567890",
        }

        record = normalize_cninfo_record(raw_item)

        self.assertEqual(record.source_name, "cninfo")
        self.assertEqual(record.market, "szse")
        self.assertEqual(record.company_code, "002371")
        self.assertEqual(record.company_name, "北方华创")
        self.assertEqual(record.announcement_id, "1234567890")
        self.assertNotIn("<em>", record.title)

    def test_list_filings_uses_fulltext_search_and_filters_company_code(self) -> None:
        company = SampleCompany(
            company_code="002371",
            company_name="北方华创",
            segment="equipment",
            subsegment="etch_deposition",
            priority="high",
        )
        calls: list[tuple[str, dict[str, object]]] = []

        class FakeFetcher:
            # CNInfo 现在走全文检索接口，这里确认查询参数和代码过滤都正确。
            def get_json(self, url: str, params: dict[str, object], headers: dict[str, str]):
                calls.append((url, dict(params)))
                return {
                    "announcements": [
                        {
                            "secCode": "002371",
                            "secName": "北方华创",
                            "announcementTitle": "<em>北方华创</em>：2025年半年度报告",
                            "announcementTime": 1756425600000,
                            "adjunctUrl": "finalpage/2025-08-29/1225000000.PDF",
                            "announcementId": "1225000000",
                        },
                        {
                            "secCode": "002371",
                            "secName": "北方华创",
                            "announcementTitle": "<em>北方华创</em>：关于签订重大合同的公告",
                            "announcementTime": 1744905600000,
                            "adjunctUrl": "finalpage/2025-04-18/1224000000.PDF",
                            "announcementId": "1224000000",
                        },
                        {
                            "secCode": "000001",
                            "secName": "平安银行",
                            "announcementTitle": "平安银行：不应被保留",
                            "announcementTime": 1744905600000,
                            "adjunctUrl": "finalpage/2025-04-18/1224000001.PDF",
                            "announcementId": "1224000001",
                        },
                    ],
                    "totalRecordNum": 2,
                }

        adapter = CninfoFilingsAdapter(fetcher=FakeFetcher())

        records = adapter.list_filings(
            company=company,
            start_date="2024-01-01",
            end_date="2025-12-31",
        )

        self.assertEqual(len(records), 2)
        self.assertTrue(all(record.company_code == "002371" for record in records))
        self.assertEqual(records[0].source_name, "cninfo")
        self.assertNotIn("<em>", records[0].title)
        self.assertEqual(
            calls[0][0],
            "https://www.cninfo.com.cn/new/fulltextSearch/full",
        )
        self.assertEqual(calls[0][1]["searchkey"], "002371")
        self.assertEqual(calls[0][1]["sdate"], "2024-01-01")
        self.assertEqual(calls[0][1]["edate"], "2025-12-31")
        self.assertEqual(calls[0][1]["pageNum"], "1")


class FakeAdapter:
    def __init__(self, records):
        self.records = records

    def list_filings(self, company, start_date, end_date):
        return list(self.records)


class FakeDownloader:
    def __init__(self):
        self.downloads = []

    def download(self, url, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"%PDF-1.4\n")
        self.downloads.append((url, destination))
        return destination


class FailingDownloader:
    def download(self, url, destination):
        raise RuntimeError(f"download failed for {url}")


class SelectiveDownloader:
    def __init__(self):
        self.downloads = []

    def download(self, url, destination):
        self.downloads.append((url, destination))
        if "sse.com.cn" in url:
            raise ValueError("下载内容是 gzip 包装的非 PDF 响应")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"%PDF-1.7\n")
        return destination


class PdfCorpusAcquisitionServiceTest(unittest.TestCase):
    def test_collect_filing_index_filters_only_supported_documents(self) -> None:
        company = SampleCompany(
            company_code="688981",
            company_name="中芯国际",
            segment="manufacturing_idm",
            subsegment="foundry",
            priority="high",
        )
        records = [
            FilingRecord(
                source_name="sse",
                market="sse",
                company_code="688981",
                company_name="中芯国际",
                title="2024年年度报告",
                publish_date="2025-03-29",
                source_doc_type="regular",
                pdf_url="https://example.test/a.pdf",
            ),
            FilingRecord(
                source_name="sse",
                market="sse",
                company_code="688981",
                company_name="中芯国际",
                title="关于召开股东大会的通知",
                publish_date="2025-03-20",
                source_doc_type="announcement",
                pdf_url="https://example.test/b.pdf",
            ),
        ]

        service = PdfCorpusAcquisitionService(
            sse_adapter=FakeAdapter(records),
            cninfo_adapter=FakeAdapter([]),
        )

        result = service.collect_filing_index(
            companies=[company],
            start_date="2021-01-01",
            end_date="2026-06-30",
        )

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].title, "2024年年度报告")

    def test_collect_filing_index_prefers_cninfo_record_when_sse_and_cninfo_repeat_same_filing(
        self,
    ) -> None:
        company = SampleCompany(
            company_code="688012",
            company_name="中微公司",
            segment="equipment",
            subsegment="etch_deposition",
            priority="high",
        )
        sse_record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688012",
            company_name="中微公司",
            title="2025年半年度报告",
            publish_date="2025-08-29",
            source_doc_type="regular",
            pdf_url="https://www.sse.com.cn/a.pdf",
        )
        cninfo_record = FilingRecord(
            source_name="cninfo",
            market="szse",
            company_code="688012",
            company_name="中微公司",
            title="中微公司：2025年半年度报告",
            publish_date="2025-08-29",
            source_doc_type="announcement",
            pdf_url="https://static.cninfo.com.cn/a.pdf",
        )

        service = PdfCorpusAcquisitionService(
            sse_adapter=FakeAdapter([sse_record]),
            cninfo_adapter=FakeAdapter([cninfo_record]),
        )

        result = service.collect_filing_index(
            companies=[company],
            start_date="2025-01-01",
            end_date="2025-12-31",
        )

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].source_name, "cninfo")
        self.assertEqual(result.records[0].pdf_url, "https://static.cninfo.com.cn/a.pdf")

    def test_download_filings_writes_pdf_and_status_snapshot(self) -> None:
        company = SampleCompany(
            company_code="688981",
            company_name="中芯国际",
            segment="manufacturing_idm",
            subsegment="foundry",
            priority="high",
        )
        record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688981",
            company_name="中芯国际",
            title="2024年年度报告",
            publish_date="2025-03-29",
            source_doc_type="regular",
            pdf_url="https://example.test/a.pdf",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = FakeDownloader()
            service = PdfCorpusAcquisitionService(
                sse_adapter=FakeAdapter([record]),
                cninfo_adapter=FakeAdapter([]),
                downloader=downloader,
                raw_filings_root=Path(temp_dir) / "raw_filings",
                status_root=Path(temp_dir) / "corpus_status",
            )

            result = service.download_filings(
                companies=[company],
                start_date="2021-01-01",
                end_date="2026-06-30",
            )

            self.assertEqual(result.downloaded_count, 1)
            self.assertEqual(len(downloader.downloads), 1)
            self.assertTrue(result.status_snapshot_path.exists())

    def test_download_pilot_filings_uses_manifest_selection_and_writes_company_summary(
        self,
    ) -> None:
        companies = [
            SampleCompany(
                company_code="688981",
                company_name="中芯国际",
                segment="manufacturing_idm",
                subsegment="foundry",
                priority="high",
            ),
            SampleCompany(
                company_code="002371",
                company_name="北方华创",
                segment="equipment",
                subsegment="etch_deposition",
                priority="high",
            ),
        ]
        universe = SampleUniverse(
            theme="semiconductor",
            segment_targets={"equipment": 1, "manufacturing_idm": 1},
            companies=companies,
        )
        records_by_code = {
            "688981": [
                FilingRecord(
                    source_name="sse",
                    market="sse",
                    company_code="688981",
                    company_name="中芯国际",
                    title="2024年年度报告",
                    publish_date="2025-03-29",
                    source_doc_type="regular",
                    pdf_url="https://example.test/a.pdf",
                )
            ],
            "002371": [
                FilingRecord(
                    source_name="cninfo",
                    market="szse",
                    company_code="002371",
                    company_name="北方华创",
                    title="关于签订重大合同的公告",
                    publish_date="2025-04-18",
                    source_doc_type="announcement",
                    pdf_url="https://example.test/b.pdf",
                )
            ],
        }

        class RoutedFakeAdapter:
            def list_filings(self, company, start_date, end_date):
                return list(records_by_code.get(company.company_code, []))

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = FakeDownloader()
            service = PdfCorpusAcquisitionService(
                sse_adapter=RoutedFakeAdapter(),
                cninfo_adapter=RoutedFakeAdapter(),
                downloader=downloader,
                raw_filings_root=Path(temp_dir) / "raw_filings",
                status_root=Path(temp_dir) / "corpus_status",
            )

            result = service.download_pilot_filings(
                sample_universe=universe,
                pilot_company_count=1,
                start_date="2021-01-01",
                end_date="2026-06-30",
            )

            self.assertEqual(result.downloaded_count, 1)
            self.assertEqual(len(downloader.downloads), 1)
            snapshot_payload = result.status_snapshot_path.read_text(encoding="utf-8")
            self.assertIn('"selected_company_count": 1', snapshot_payload)
            self.assertIn('"688981"', snapshot_payload)

    def test_download_filings_records_failed_items_in_status_snapshot(self) -> None:
        company = SampleCompany(
            company_code="688072",
            company_name="拓荆科技",
            segment="equipment",
            subsegment="thin_film_deposition",
            priority="high",
        )
        record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688072",
            company_name="拓荆科技",
            title="关于与关联方共同投资暨关联交易的公告",
            publish_date="2025-12-06",
            source_doc_type="announcement",
            pdf_url="https://example.test/fail.pdf",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            service = PdfCorpusAcquisitionService(
                sse_adapter=FakeAdapter([record]),
                cninfo_adapter=FakeAdapter([]),
                downloader=FailingDownloader(),
                raw_filings_root=Path(temp_dir) / "raw_filings",
                status_root=Path(temp_dir) / "corpus_status",
            )

            result = service.download_filings(
                companies=[company],
                start_date="2024-01-01",
                end_date="2025-12-31",
            )

            self.assertEqual(result.downloaded_count, 0)
            self.assertEqual(result.failed_count, 1)
            snapshot_payload = result.status_snapshot_path.read_text(encoding="utf-8")
            self.assertIn('"failed_count": 1', snapshot_payload)
            self.assertIn("关于与关联方共同投资暨关联交易的公告", snapshot_payload)
            self.assertIn("download failed for https://example.test/fail.pdf", snapshot_payload)

    def test_download_filings_prefers_cninfo_source_before_sse_download_for_688_company(
        self,
    ) -> None:
        company = SampleCompany(
            company_code="688012",
            company_name="中微公司",
            segment="equipment",
            subsegment="etch_deposition",
            priority="high",
        )
        sse_record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688012",
            company_name="中微公司",
            title="2025年半年度报告",
            publish_date="2025-08-29",
            source_doc_type="regular",
            pdf_url="https://www.sse.com.cn/disclosure/listedinfo/announcement/c/new/2025-08-29/688012_20250829_BW75.pdf",
        )
        cninfo_record = FilingRecord(
            source_name="cninfo",
            market="szse",
            company_code="688012",
            company_name="中微公司",
            title="中微公司：2025年半年度报告",
            publish_date="2025-08-29",
            source_doc_type="announcement",
            pdf_url="https://static.cninfo.com.cn/finalpage/2025-08-29/1224600000.PDF",
        )

        class SseOnlyAdapter:
            def list_filings(self, company, start_date, end_date):
                return [sse_record]

        class CninfoFallbackAdapter:
            def list_filings(self, company, start_date, end_date):
                return [cninfo_record]

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = SelectiveDownloader()
            service = PdfCorpusAcquisitionService(
                sse_adapter=SseOnlyAdapter(),
                cninfo_adapter=CninfoFallbackAdapter(),
                downloader=downloader,
                raw_filings_root=Path(temp_dir) / "raw_filings",
                status_root=Path(temp_dir) / "corpus_status",
            )

            result = service.download_filings(
                companies=[company],
                start_date="2025-01-01",
                end_date="2025-12-31",
            )

            self.assertEqual(result.downloaded_count, 1)
            self.assertEqual(result.failed_count, 0)
            # 现在在“列表发现”阶段就优先保留 CNInfo 记录，
            # 因此不会先打到会被拦截的 SSE PDF 直链。
            self.assertEqual(len(downloader.downloads), 1)
            self.assertIn("static.cninfo.com.cn", downloader.downloads[0][0])

    def test_download_filings_prefers_cninfo_pdf_for_688_company_when_same_record_exists(
        self,
    ) -> None:
        company = SampleCompany(
            company_code="688012",
            company_name="中微公司",
            segment="equipment",
            subsegment="etch_deposition",
            priority="high",
        )
        sse_record = FilingRecord(
            source_name="sse",
            market="sse",
            company_code="688012",
            company_name="中微公司",
            title="2025年半年度报告",
            publish_date="2025-08-29",
            source_doc_type="regular",
            pdf_url="https://www.sse.com.cn/disclosure/blocked.pdf",
        )
        cninfo_record = FilingRecord(
            source_name="cninfo",
            market="szse",
            company_code="688012",
            company_name="中微公司",
            title="中微公司：2025年半年度报告",
            publish_date="2025-08-29",
            source_doc_type="announcement",
            pdf_url="https://static.cninfo.com.cn/finalpage/2025-08-29/ok.PDF",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = SelectiveDownloader()
            service = PdfCorpusAcquisitionService(
                sse_adapter=FakeAdapter([sse_record]),
                cninfo_adapter=FakeAdapter([cninfo_record]),
                downloader=downloader,
                raw_filings_root=Path(temp_dir) / "raw_filings",
                status_root=Path(temp_dir) / "corpus_status",
            )

            result = service.download_filings(
                companies=[company],
                start_date="2025-01-01",
                end_date="2025-12-31",
            )

            self.assertEqual(result.downloaded_count, 1)
            self.assertEqual(result.failed_count, 0)
            self.assertEqual(len(downloader.downloads), 1)
            self.assertIn("static.cninfo.com.cn", downloader.downloads[0][0])


class PdfDownloadPayloadValidationTest(unittest.TestCase):
    def test_extract_pdf_bytes_accepts_plain_pdf(self) -> None:
        payload = b"%PDF-1.4\nhello"

        result = _extract_pdf_bytes(payload)

        self.assertEqual(result, payload)

    def test_extract_pdf_bytes_accepts_gzip_wrapped_pdf(self) -> None:
        payload = gzip.compress(b"%PDF-1.7\nwrapped")

        result = _extract_pdf_bytes(payload)

        self.assertTrue(result.startswith(b"%PDF-1.7"))

    def test_extract_pdf_bytes_rejects_gzip_wrapped_html_challenge(self) -> None:
        payload = gzip.compress(b"<html><script>bot challenge</script></html>")

        with self.assertRaisesRegex(ValueError, "非 PDF"):
            _extract_pdf_bytes(payload)


class RetrievalFacadeTest(unittest.TestCase):
    def test_build_pdf_corpus_acquisition_service_uses_repository_settings(self) -> None:
        service = build_pdf_corpus_acquisition_service()

        self.assertIsNotNone(service)
        self.assertTrue(hasattr(service, "download_filings"))


if __name__ == "__main__":
    unittest.main()
