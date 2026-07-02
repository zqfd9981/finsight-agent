from __future__ import annotations

from finsight_agent.control_plane.orchestrator.context_retrieval_models import (
    ExternalContextItem,
    ExternalContextResult,
)
from finsight_agent.infra.external.cninfo_filings import (
    CNINFO_FULLTEXT_URL,
    CNINFO_SITE_BASE_URL,
    CninfoHttpFetcher,
    normalize_cninfo_record,
)


class CninfoContextSearchProvider:
    """CNInfo 运行时上下文搜索 provider。"""

    def __init__(self, *, fetcher: CninfoHttpFetcher | None = None) -> None:
        self._fetcher = fetcher or CninfoHttpFetcher()

    def search(self, *, query: str, limit: int) -> ExternalContextResult:
        payload = self._fetcher.get_json(
            url=CNINFO_FULLTEXT_URL,
            params={
                "searchkey": query,
                "sdate": "",
                "edate": "",
                "isfulltext": "false",
                "sortName": "pubdate",
                "sortType": "desc",
                "pageNum": "1",
                "pageSize": str(limit),
                "type": "",
            },
            headers={
                "Referer": f"{CNINFO_SITE_BASE_URL}/new/fulltextSearch?keyWord={query}",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
            },
        )
        items: list[ExternalContextItem] = []
        evidence_refs: list[str] = []
        for index, raw in enumerate(payload.get("announcements", []) or [], start=1):
            if not isinstance(raw, dict):
                continue
            record = normalize_cninfo_record(raw)
            items.append(
                ExternalContextItem(
                    title=record.title,
                    source="cninfo",
                    publish_date=record.publish_date,
                    url=record.pdf_url,
                    snippet=record.title,
                    company_names=[record.company_name],
                    company_codes=[record.company_code],
                    themes=[],
                )
            )
            evidence_refs.append(f"cninfo:{record.announcement_id or index}")

        return ExternalContextResult(
            items=items,
            summary_hint=items[0].title if items else "",
            supporting_points=[item.title for item in items[:2]],
            evidence_refs=evidence_refs,
            candidate_hints=[name for item in items for name in item.company_names],
            source_status={"cninfo_used": bool(items)},
        )
