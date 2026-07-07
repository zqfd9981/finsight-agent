from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class _StubBochaFetcher:
    def __init__(self, payload=None, side_effect=None):
        self._payload = payload
        self._side_effect = side_effect
        self.calls = []

    def post_json(self, url, *, headers, body):
        self.calls.append({"url": url, "headers": headers, "body": body})
        if self._side_effect is not None:
            raise self._side_effect
        return self._payload or {"data": {"webPages": {"value": []}}}


_FULL_PAYLOAD = {
    "data": {
        "webPages": {
            "value": [
                {
                    "id": "https://example.com/a",
                    "name": "红海航运受阻 油运价格连涨三周",
                    "url": "https://example.com/a",
                    "siteName": "财联社",
                    "datePublished": "2026-07-04T10:23:00",
                    "snippet": "受红海局势持续升级影响，全球航运受阻。",
                    "summary": "红海局势升级导致苏伊士航线绕行成本上升，国际油运价格连续三周上涨。国内中远海能、招商轮船等航运企业近期订单及运价数据均出现显著回升。",
                },
                {
                    "name": "A股航运板块走强",
                    "url": "https://example.com/b",
                    "datePublished": "2026-07-03T09:00:00",
                    "snippet": "中远海能、招商轮船领涨。",
                    "summary": "受地缘冲突影响，A股航运板块今日普遍走强。",
                },
                {
                    "name": "油运价格周报",
                    "url": "https://example.com/c",
                    "datePublished": "2026-07-02T08:00:00",
                    "snippet": "本周油运价格继续上行。",
                    "summary": "",
                },
            ]
        }
    }
}


class BochaEventSearchProviderTest(unittest.TestCase):
    def test_search_returns_standardized_context_result(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="红海局势升级利好哪些A股航运股？",
            event="红海局势升级",
            themes=["航运", "油运"],
            time_scope="recent",
            limit=3,
        )

        self.assertEqual(len(result.items), 3)
        self.assertEqual(result.items[0].source, "bocha")
        self.assertEqual(result.items[0].title, "红海航运受阻 油运价格连涨三周")
        self.assertEqual(result.items[0].publish_date, "2026-07-04T10:23:00")
        self.assertEqual(result.items[0].url, "https://example.com/a")
        self.assertEqual(result.items[0].themes, ["航运", "油运"])
        # snippet 优先 summary；第 3 条 summary 空则回退 snippet
        self.assertIn("苏伊士航线绕行成本上升", result.items[0].snippet)
        self.assertEqual(result.items[2].snippet, "本周油运价格继续上行。")
        # summary_hint / supporting_points
        self.assertEqual(result.summary_hint, "红海航运受阻 油运价格连涨三周")
        self.assertEqual(len(result.supporting_points), 2)
        # evidence_refs 形如 bocha:item_001
        self.assertEqual(
            result.evidence_refs, ["bocha:item_001", "bocha:item_002", "bocha:item_003"]
        )
        # candidate_hints == themes
        self.assertEqual(result.candidate_hints, ["航运", "油运"])
        # source_status
        self.assertTrue(result.source_status["bocha_used"])
        self.assertEqual(result.source_status["freshness"], "oneWeek")
        self.assertEqual(result.source_status["time_scope"], "recent")

    def test_snippet_prefers_summary_then_snippet_then_name(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        payload = {
            "data": {
                "webPages": {
                    "value": [
                        {"name": "n1", "url": "u1", "snippet": "s1", "summary": "sum1"},
                        {"name": "n2", "url": "u2", "snippet": "s2"},  # 无 summary
                        {"name": "n3", "url": "u3"},  # 都无
                    ]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=payload)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(result.items[0].snippet, "sum1")
        self.assertEqual(result.items[1].snippet, "s2")
        self.assertEqual(result.items[2].snippet, "n3")

    def test_publish_date_passed_through_as_is(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        payload = {
            "data": {
                "webPages": {
                    "value": [
                        {
                            "name": "n",
                            "url": "u",
                            "datePublished": "2026-07-04T10:23:00",
                            "summary": "s",
                        }
                    ]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=payload)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=1
        )
        self.assertEqual(result.items[0].publish_date, "2026-07-04T10:23:00")

    def test_themes_passed_through_into_items(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        payload = {
            "data": {
                "webPages": {
                    "value": [{"name": "n", "url": "u", "summary": "s"}]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=payload)
        )
        result = provider.search_event_context(
            query="q",
            event="e",
            themes=["航运", "油运"],
            time_scope="recent",
            limit=1,
        )
        self.assertEqual(result.items[0].themes, ["航运", "油运"])

    def test_candidate_hints_are_input_themes(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        payload = {
            "data": {
                "webPages": {
                    "value": [{"name": "n", "url": "u", "summary": "s"}]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=payload)
        )
        result = provider.search_event_context(
            query="q",
            event="e",
            themes=["航运"],
            time_scope="recent",
            limit=1,
        )
        self.assertEqual(result.candidate_hints, ["航运"])

    def test_evidence_refs_use_bocha_prefix(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(
            result.evidence_refs,
            ["bocha:item_001", "bocha:item_002", "bocha:item_003"],
        )

    def test_evidence_refs_match_item_count(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(len(result.evidence_refs), len(result.items))

    def test_handles_empty_webpages_value(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(payload={"data": {"webPages": {"value": []}}}),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.items, [])
        self.assertEqual(result.evidence_refs, [])
        self.assertFalse(result.source_status["bocha_used"])
        self.assertEqual(result.source_status["error"], "empty_response")

    def test_handles_missing_webpages_field(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(payload={"data": {}}),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "empty_response")

    def test_handles_missing_data_field(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload={"other": "stuff"})
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "empty_response")

    def test_handles_http_error_401(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(side_effect=urllib.error.HTTPError(
                url="http://x", code=401, msg="Unauthorized", hdrs=None, fp=None
            )),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "http_401")
        self.assertFalse(result.source_status["bocha_used"])

    def test_handles_http_error_429(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(side_effect=urllib.error.HTTPError(
                url="http://x", code=429, msg="Too Many", hdrs=None, fp=None
            )),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "http_429")

    def test_handles_urlerror_timeout(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key",
            fetcher=_StubBochaFetcher(side_effect=urllib.error.URLError("timeout")),
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "timeout")

    def test_handles_json_decode_error(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        class _BadJsonFetcher:
            def post_json(self, url, *, headers, body):
                raise json.JSONDecodeError("bad", "", 0)

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_BadJsonFetcher()
        )
        result = provider.search_event_context(
            query="q", event="e", themes=["t"], time_scope="recent", limit=3
        )
        self.assertEqual(result.source_status["error"], "invalid_json")

    def test_limit_truncates_items(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        # Bocha 返回 5 条，limit=3
        big_payload = {
            "data": {
                "webPages": {
                    "value": [
                        {"name": f"n{i}", "url": f"u{i}", "summary": f"s{i}"}
                        for i in range(5)
                    ]
                }
            }
        }
        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=big_payload)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(len(result.items), 3)
        self.assertEqual(len(result.evidence_refs), 3)

    def test_constructor_raises_without_api_key(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        # 确保 env 也没设置
        import os

        old = os.environ.pop("BOCHA_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                BochaEventSearchProvider()
            self.assertIn("BOCHA_API_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["BOCHA_API_KEY"] = old

    def test_summary_hint_uses_first_item_title(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(result.summary_hint, result.items[0].title)
        self.assertEqual(result.summary_hint, "红海航运受阻 油运价格连涨三周")

    def test_supporting_points_take_first_two(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        provider = BochaEventSearchProvider(
            api_key="test-key", fetcher=_StubBochaFetcher(payload=_FULL_PAYLOAD)
        )
        result = provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertLessEqual(len(result.supporting_points), 2)
        self.assertEqual(result.supporting_points[0], result.items[0].snippet)

    def test_request_body_uses_one_week_freshness(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BOCHA_FRESHNESS,
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="test-key", fetcher=fetcher)
        provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(fetcher.calls[0]["body"]["freshness"], BOCHA_FRESHNESS)
        self.assertEqual(fetcher.calls[0]["body"]["freshness"], "oneWeek")

    def test_request_body_passes_count_as_limit(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="test-key", fetcher=fetcher)
        provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=7
        )
        self.assertEqual(fetcher.calls[0]["body"]["count"], 7)

    def test_request_body_sets_summary_true(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="test-key", fetcher=fetcher)
        provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        self.assertIs(fetcher.calls[0]["body"]["summary"], True)

    def test_request_headers_include_bearer_token(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="my-secret-key", fetcher=fetcher)
        provider.search_event_context(
            query="q", event="e", themes=[], time_scope="recent", limit=3
        )
        auth = fetcher.calls[0]["headers"]["Authorization"]
        self.assertTrue(auth.startswith("Bearer "))
        self.assertIn("my-secret-key", auth)

    def test_empty_query_returns_empty_result(self):
        from finsight_agent.infra.external.bocha_event_search import (
            BochaEventSearchProvider,
        )

        fetcher = _StubBochaFetcher(payload=_FULL_PAYLOAD)
        provider = BochaEventSearchProvider(api_key="test-key", fetcher=fetcher)
        result = provider.search_event_context(
            query="", event="", themes=[], time_scope="recent", limit=3
        )
        self.assertEqual(result.items, [])
        self.assertEqual(result.source_status["error"], "empty_query")
        # 不调 fetcher
        self.assertEqual(fetcher.calls, [])


if __name__ == "__main__":
    unittest.main()