from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class _StubCninfoContextFetcher:
    def get_json(
        self,
        url: str,
        params: dict[str, object],
        headers: dict[str, str],
    ) -> dict[str, object]:
        del url, params, headers
        return {
            "announcements": [
                {
                    "secCode": "000001",
                    "secName": "平安银行",
                    "announcementTitle": "关于航运链风险提示的公告",
                    "announcementTime": 1782960000000,
                    "adjunctUrl": "finalpage/2026-07-02/sample.PDF",
                    "announcementId": "ann_001",
                }
            ]
        }


class _RecordingCninfoContextFetcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_json(
        self,
        url: str,
        params: dict[str, object],
        headers: dict[str, str],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "url": url,
                "params": dict(params),
                "headers": dict(headers),
            }
        )
        return {"announcements": []}


class _StubSseContextFetcher:
    def get_json(
        self,
        url: str,
        params: dict[str, object],
        headers: dict[str, str],
    ) -> dict[str, object]:
        del url, params, headers
        return {
            "result": [
                {
                    "SECURITY_CODE": "600026",
                    "TITLE": "关于航运市场波动的公告",
                    "SSEDATE": "2026-07-02",
                    "URL": "/disclosure/listedinfo/announcement/c/new.pdf",
                    "BULLETIN_ID": "bulletin_001",
                }
            ]
        }


class CninfoContextSearchProviderTest(unittest.TestCase):
    def test_search_returns_standardized_items(self) -> None:
        from finsight_agent.infra.external.cninfo_context_search import (
            CninfoContextSearchProvider,
        )

        provider = CninfoContextSearchProvider(fetcher=_StubCninfoContextFetcher())
        result = provider.search(
            query="红海局势升级 航运",
            limit=3,
        )

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source, "cninfo")
        self.assertEqual(result.items[0].company_codes, ["000001"])

    def test_search_does_not_put_raw_chinese_query_into_referer_header(self) -> None:
        from finsight_agent.infra.external.cninfo_context_search import (
            CninfoContextSearchProvider,
        )

        fetcher = _RecordingCninfoContextFetcher()
        provider = CninfoContextSearchProvider(fetcher=fetcher)
        query = "宁德时代扩产公告意味着什么？"

        provider.search(query=query, limit=3)

        self.assertEqual(len(fetcher.calls), 1)
        headers = fetcher.calls[0]["headers"]
        assert isinstance(headers, dict)
        self.assertIn("Referer", headers)
        self.assertNotIn(query, str(headers["Referer"]))


class SseContextSearchProviderTest(unittest.TestCase):
    def test_search_returns_standardized_items(self) -> None:
        from finsight_agent.infra.external.sse_context_search import (
            SseContextSearchProvider,
        )

        provider = SseContextSearchProvider(fetcher=_StubSseContextFetcher())
        result = provider.search(
            query="红海局势升级 航运",
            limit=3,
        )

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source, "sse")
        self.assertEqual(result.items[0].company_codes, ["600026"])


class _StubDisclosureProvider:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = 0

    def search(self, *, query: str, limit: int):
        del query, limit
        self.calls += 1
        return self.result


class OfficialDisclosureSearchProviderTest(unittest.TestCase):
    def test_search_merges_cninfo_and_sse_results(self) -> None:
        from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
            ExternalContextItem,
            ExternalContextResult,
        )
        from finsight_agent.infra.external.official_disclosure_search import (
            OfficialDisclosureSearchProvider,
        )

        cninfo = _StubDisclosureProvider(
            ExternalContextResult(
                items=[
                    ExternalContextItem(
                        title="公告A",
                        source="cninfo",
                        publish_date="2026-07-02",
                        url="https://a",
                        snippet="公告A",
                        company_codes=["000001"],
                    )
                ],
                evidence_refs=["cninfo:a"],
                source_status={"cninfo_used": True},
            )
        )
        sse = _StubDisclosureProvider(
            ExternalContextResult(
                items=[
                    ExternalContextItem(
                        title="公告B",
                        source="sse",
                        publish_date="2026-07-02",
                        url="https://b",
                        snippet="公告B",
                        company_codes=["600026"],
                    )
                ],
                evidence_refs=["sse:b"],
                source_status={"sse_used": True},
            )
        )

        provider = OfficialDisclosureSearchProvider(
            cninfo_provider=cninfo,
            sse_provider=sse,
        )
        result = provider.search(query="红海局势升级 航运", limit=3)

        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.evidence_refs, ["cninfo:a", "sse:b"])


if __name__ == "__main__":
    unittest.main()
