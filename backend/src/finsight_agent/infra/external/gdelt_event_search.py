from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


@dataclass(slots=True)
class GdeltHttpFetcher:
    timeout_seconds: float = 30.0

    def get_json(self, url: str, params: dict[str, object]) -> dict[str, object]:
        query_string = urllib.parse.urlencode(params)
        with urllib.request.urlopen(
            f"{url}?{query_string}",
            timeout=self.timeout_seconds,
        ) as response:
            return json.loads(response.read().decode("utf-8"))


class GdeltEventSearchProvider:
    """GDELT 事件搜索 provider。

    首版只抽取最小字段，先服务 collect_event_context 的外部事件背景建立。
    """

    def __init__(self, *, fetcher: GdeltHttpFetcher | None = None) -> None:
        self._fetcher = fetcher or GdeltHttpFetcher()

    def search_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> ExternalContextResult:
        payload = self._fetcher.get_json(
            GDELT_DOC_API_URL,
            {
                "query": " ".join([query, event, *themes]).strip(),
                "mode": "ArtList",
                "maxrecords": str(limit),
                "format": "json",
            },
        )
        items: list[ExternalContextItem] = []
        evidence_refs: list[str] = []
        for index, article in enumerate(payload.get("articles", []) or [], start=1):
            title = str(article.get("title") or "").strip()
            url = str(article.get("url") or "").strip()
            publish_date = str(article.get("seendate") or "")[:8]
            normalized_date = (
                datetime.strptime(publish_date, "%Y%m%d").strftime("%Y-%m-%d")
                if publish_date
                else ""
            )
            items.append(
                ExternalContextItem(
                    title=title,
                    source="gdelt",
                    publish_date=normalized_date,
                    url=url,
                    snippet=title,
                    themes=list(themes),
                )
            )
            evidence_refs.append(f"gdelt:item_{index:03d}")

        summary_hint = items[0].title if items else ""
        return ExternalContextResult(
            items=items,
            summary_hint=summary_hint,
            supporting_points=[item.title for item in items[:2]],
            evidence_refs=evidence_refs,
            candidate_hints=list(themes),
            source_status={"gdelt_used": bool(items), "time_scope": time_scope},
        )
