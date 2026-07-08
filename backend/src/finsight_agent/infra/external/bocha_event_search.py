from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)


_logger = logging.getLogger(__name__)

BOCHA_WEB_SEARCH_URL = "https://api.bochaai.com/v1/web-search"
BOCHA_FRESHNESS = "oneWeek"
BOCHA_USER_AGENT = "finsight-bocha-search/1.0"


@dataclass(slots=True)
class BochaHttpFetcher:
    """Bocha HTTP 客户端：仅负责发 POST + 解 JSON，不做错误翻译。"""

    timeout_seconds: float = 30.0

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        body: dict[str, object],
    ) -> dict[str, object]:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        for key, value in headers.items():
            request.add_header(key, value)
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


class BochaEventSearchProvider:
    """Bocha 事件搜索 provider（首版默认事件搜索实现）。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        fetcher: BochaHttpFetcher | None = None,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get("BOCHA_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "BOCHA_API_KEY is required: pass api_key=... or set BOCHA_API_KEY env"
            )
        self._api_key = resolved_key
        self._fetcher = fetcher or BochaHttpFetcher()

    def search_event_context(
        self,
        *,
        query: str,
        event: str,
        themes: list[str],
        time_scope: str,
        limit: int,
    ) -> ExternalContextResult:
        composed_query = " ".join(
            part for part in (query, event, *themes) if part
        ).strip()
        if not composed_query:
            return self._empty_result(themes, time_scope, error="empty_query")

        body = {
            "query": composed_query,
            "freshness": BOCHA_FRESHNESS,
            "summary": True,
            "count": limit,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": BOCHA_USER_AGENT,
        }

        try:
            payload = self._fetcher.post_json(
                BOCHA_WEB_SEARCH_URL, headers=headers, body=body
            )
        except urllib.error.HTTPError as exc:
            tag = f"http_{exc.code}"
            _logger.warning(
                "bocha search failed: error=%s query_len=%d", tag, len(composed_query)
            )
            return self._empty_result(themes, time_scope, error=tag)
        except urllib.error.URLError:
            _logger.warning(
                "bocha search failed: error=timeout query_len=%d", len(composed_query)
            )
            return self._empty_result(themes, time_scope, error="timeout")
        except json.JSONDecodeError:
            _logger.warning(
                "bocha search failed: error=invalid_json query_len=%d",
                len(composed_query),
            )
            return self._empty_result(themes, time_scope, error="invalid_json")
        except Exception:
            _logger.warning(
                "bocha search failed: error=unknown query_len=%d", len(composed_query)
            )
            return self._empty_result(themes, time_scope, error="unknown")

        value_list = (
            (payload.get("data") or {}).get("webPages", {}).get("value") or []
        )
        if not value_list:
            return self._empty_result(themes, time_scope, error="empty_response")

        items = self._map_items(value_list[:limit], themes)
        return ExternalContextResult(
            items=items,
            summary_hint=items[0].title if items else "",
            supporting_points=[(item.snippet or item.title) for item in items[:2]],
            evidence_refs=[item.evidence_ref for item in items if item.evidence_ref],
            candidate_hints=list(themes),
            source_status={
                "bocha_used": True,
                "freshness": BOCHA_FRESHNESS,
                "time_scope": time_scope,
            },
        )

    @staticmethod
    def _map_items(value_list: list[dict[str, object]], themes: list[str]) -> list[ExternalContextItem]:
        items: list[ExternalContextItem] = []
        for index, entry in enumerate(value_list, start=1):
            title = str(entry.get("name") or "").strip()
            url = str(entry.get("url") or "").strip()
            publish_date = str(entry.get("datePublished") or "").strip()
            # snippet 三级兜底：summary → snippet → name
            snippet = (
                str(entry.get("summary") or "").strip()
                or str(entry.get("snippet") or "").strip()
                or title
            )
            items.append(
                ExternalContextItem(
                    title=title,
                    source="bocha",
                    publish_date=publish_date,
                    url=url,
                    snippet=snippet,
                    evidence_ref=f"bocha:item_{index:03d}",
                    themes=list(themes),
                )
            )
        return items

    @staticmethod
    def _empty_result(
        themes: list[str], time_scope: str, *, error: str
    ) -> ExternalContextResult:
        return ExternalContextResult(
            items=[],
            summary_hint="",
            supporting_points=[],
            evidence_refs=[],
            candidate_hints=list(themes),
            source_status={
                "bocha_used": False,
                "freshness": BOCHA_FRESHNESS,
                "time_scope": time_scope,
                "error": error,
            },
        )
