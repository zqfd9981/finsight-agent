from __future__ import annotations

from urllib.parse import urljoin

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)
from finsight_agent.infra.external.sse_filings import (
    SSE_ANNOUNCEMENT_URL,
    SSE_BASE_URL,
    SseHttpFetcher,
)


class SseContextSearchProvider:
    """SSE 运行时上下文搜索 provider。"""

    def __init__(self, *, fetcher: SseHttpFetcher | None = None) -> None:
        self._fetcher = fetcher or SseHttpFetcher()

    def search(self, *, query: str, limit: int) -> ExternalContextResult:
        payload = self._fetcher.get_json(
            url=SSE_ANNOUNCEMENT_URL,
            params={
                "isPagination": "true",
                "pageHelp.pageSize": str(limit),
                "pageHelp.pageNo": "1",
                "pageHelp.beginPage": "1",
                "pageHelp.cacheSize": "1",
                "pageHelp.endPage": "1",
                "title": query,
            },
            headers={
                "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )

        raw_items = payload.get("result") or []
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        items: list[ExternalContextItem] = []
        evidence_refs: list[str] = []
        for index, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                continue
            code = str(raw.get("SECURITY_CODE") or "").strip()
            title = str(raw.get("TITLE") or "").strip()
            url = urljoin(SSE_BASE_URL, str(raw.get("URL") or "").strip())
            bulletin_id = str(raw.get("BULLETIN_ID") or index)
            items.append(
                ExternalContextItem(
                    title=title,
                    source="sse",
                    publish_date=str(raw.get("SSEDATE") or "").strip(),
                    url=url,
                    snippet=title,
                    evidence_ref=f"sse:{bulletin_id}",
                    company_names=[],
                    company_codes=[code] if code else [],
                    themes=[],
                )
            )
            evidence_refs.append(f"sse:{bulletin_id}")

        return ExternalContextResult(
            items=items,
            summary_hint=items[0].title if items else "",
            supporting_points=[item.title for item in items[:2]],
            evidence_refs=evidence_refs,
            candidate_hints=[code for item in items for code in item.company_codes],
            source_status={"sse_used": bool(items)},
        )
