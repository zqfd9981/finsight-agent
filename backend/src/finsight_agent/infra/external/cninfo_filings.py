from __future__ import annotations

import html
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

from finsight_agent.capabilities.retrieval.acquisition_models import (
    FilingRecord,
    SampleCompany,
)


CNINFO_BASE_URL = "https://static.cninfo.com.cn/"
CNINFO_SITE_BASE_URL = "https://www.cninfo.com.cn"
CNINFO_SEARCH_URL = f"{CNINFO_SITE_BASE_URL}/new/information/topSearch/query"
CNINFO_FULLTEXT_URL = f"{CNINFO_SITE_BASE_URL}/new/fulltextSearch/full"
CNINFO_TZ = timezone(timedelta(hours=8))


def normalize_cninfo_record(raw_item: dict[str, object]) -> FilingRecord:
    """把 CNInfo 返回字段映射成统一的披露记录对象。"""

    # CNInfo 时间戳按北京时间理解更稳定，否则凌晨零点会被误判成前一天。
    timestamp_ms = int(raw_item["announcementTime"])
    publish_date = datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=CNINFO_TZ,
    ).strftime("%Y-%m-%d")
    return FilingRecord(
        source_name="cninfo",
        market="szse",
        company_code=str(raw_item["secCode"]),
        company_name=str(raw_item["secName"]),
        title=_strip_highlight(str(raw_item["announcementTitle"])),
        publish_date=publish_date,
        source_doc_type="announcement",
        pdf_url=urljoin(CNINFO_BASE_URL, str(raw_item["adjunctUrl"])),
        announcement_id=str(raw_item["announcementId"]),
    )


@dataclass(slots=True)
class CninfoHttpFetcher:
    """对 CNInfo 提供一个很薄的 HTTP 封装，方便测试替换。"""

    timeout_seconds: float = 30.0
    max_attempts: int = 3
    retry_delay_seconds: float = 1.0

    def post_form(
        self,
        url: str,
        data: dict[str, object],
        headers: dict[str, str],
    ) -> Any:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=encoded,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                **headers,
            },
            method="POST",
        )
        return self._with_retry(lambda: self._read_json(request))

    def get_json(
        self,
        url: str,
        params: dict[str, object],
        headers: dict[str, str],
    ) -> Any:
        query_string = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url=f"{url}?{query_string}",
            headers=headers,
            method="GET",
        )
        return self._with_retry(lambda: self._read_json(request))

    def _read_json(self, request: urllib.request.Request) -> Any:
        """发起一次真实请求并解析 JSON。"""

        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)

    def _with_retry(self, operation) -> Any:
        """对外部站点的偶发 SSL EOF 做最小重试。"""

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                time.sleep(self.retry_delay_seconds * attempt)
        assert last_error is not None
        raise last_error


class CninfoFilingsAdapter:
    """CNInfo 披露列表采集适配器。"""

    def __init__(self, fetcher: CninfoHttpFetcher | None = None) -> None:
        self._fetcher = fetcher or CninfoHttpFetcher()

    def list_filings(
        self,
        company: SampleCompany,
        start_date: str,
        end_date: str,
    ) -> list[FilingRecord]:
        """通过全文检索接口分页抓取公司公告列表。"""

        collected: list[FilingRecord] = []
        page_num = 1
        while True:
            payload = self._fetcher.get_json(
                url=CNINFO_FULLTEXT_URL,
                params={
                    "searchkey": company.company_code,
                    "sdate": start_date,
                    "edate": end_date,
                    "isfulltext": "false",
                    "sortName": "pubdate",
                    "sortType": "desc",
                    "pageNum": str(page_num),
                    "pageSize": "20",
                    "type": "",
                },
                headers={
                    "Referer": (
                        f"{CNINFO_SITE_BASE_URL}/new/fulltextSearch"
                        f"?keyWord={company.company_code}"
                    ),
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json, text/plain, */*",
                },
            )
            if not isinstance(payload, dict):
                break

            page_records = [
                normalize_cninfo_record(raw_item=item)
                for item in payload.get("announcements", []) or []
                if isinstance(item, dict)
                and str(item.get("secCode", "")) == company.company_code
            ]
            collected.extend(page_records)

            total_records = int(payload.get("totalRecordNum") or 0)
            page_size = 20
            if not page_records:
                break
            if page_num * page_size >= total_records:
                break
            page_num += 1
        return collected

    def _resolve_org_id(self, company: SampleCompany) -> str | None:
        """通过站内搜索接口拿到公司对应的 orgId。"""

        payload = self._fetcher.post_form(
            url=CNINFO_SEARCH_URL,
            data={
                "keyWord": company.company_code,
                "maxNum": "10",
            },
            headers={
                "Referer": (
                    f"{CNINFO_SITE_BASE_URL}/new/fulltextSearch"
                    f"?keyWord={company.company_code}"
                ),
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
            },
        )
        if not isinstance(payload, list):
            return None

        for item in payload:
            if not isinstance(item, dict):
                continue
            if str(item.get("code", "")) == company.company_code:
                org_id = str(item.get("orgId", "")).strip()
                if org_id:
                    return org_id
        return None


def _strip_highlight(title: str) -> str:
    """去掉 CNInfo 搜索结果里的高亮标签，保留纯文本标题。"""

    cleaned = title.replace("<em>", "").replace("</em>", "")
    return html.unescape(cleaned)
