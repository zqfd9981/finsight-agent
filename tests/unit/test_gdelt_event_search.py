from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


class _StubGdeltFetcher:
    def get_json(self, url: str, params: dict[str, object]) -> dict[str, object]:
        del url, params
        return {
            "articles": [
                {
                    "title": "Red Sea disruptions raise shipping concerns",
                    "url": "https://example.com/red-sea",
                    "seendate": "20260702T120000Z",
                    "domain": "example.com",
                    "socialimage": "",
                    "language": "English",
                    "sourcecountry": "US",
                }
            ]
        }


class GdeltEventSearchProviderTest(unittest.TestCase):
    def test_search_returns_standardized_context_result(self) -> None:
        from finsight_agent.infra.external.gdelt_event_search import (
            GdeltEventSearchProvider,
        )

        provider = GdeltEventSearchProvider(fetcher=_StubGdeltFetcher())

        result = provider.search_event_context(
            query="红海局势升级利好哪些A股航运股？",
            event="红海局势升级",
            themes=["航运", "油运"],
            time_scope="recent",
            limit=3,
        )

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source, "gdelt")
        self.assertTrue(result.summary_hint)
        self.assertTrue(result.evidence_refs)


if __name__ == "__main__":
    unittest.main()
