from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from finsight_agent.capabilities.retrieval.acquisition_models import (
    FilingRecord,
    SampleCompany,
)


SSE_BASE_URL = "https://www.sse.com.cn"
SSE_QUERY_BASE_URL = "https://query.sse.com.cn"
SSE_ANNOUNCEMENT_URL = (
    f"{SSE_QUERY_BASE_URL}/security/stock/queryCompanyBulletinNew.do"
)


def normalize_sse_record(raw_item: dict[str, object], company_name: str) -> FilingRecord:
    """把 SSE 返回字段映射成统一的披露记录对象。"""

    pdf_url = str(raw_item["URL"])
    return FilingRecord(
        source_name="sse",
        market="sse",
        company_code=str(raw_item["SECURITY_CODE"]),
        company_name=company_name,
        title=str(raw_item["TITLE"]),
        publish_date=str(raw_item["SSEDATE"]),
        source_doc_type=str(raw_item.get("BULLETIN_TYPE", "unknown")),
        pdf_url=urljoin(SSE_BASE_URL, pdf_url),
        announcement_id=str(raw_item.get("BULLETIN_ID", "")) or None,
    )


@dataclass(slots=True)
class SseHttpFetcher:
    """对 SSE 提供一个很薄的 HTTP 抓取封装，方便测试时替换。"""

    timeout_seconds: float = 30.0
    max_attempts: int = 3
    retry_delay_seconds: float = 1.0

    def get_json(
        self,
        url: str,
        params: dict[str, object],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        # SSE 接口直接返回 JSON，本地只需要统一好 query 参数和 header。
        query_string = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url=f"{url}?{query_string}",
            headers=headers,
            method="GET",
        )
        return self._with_retry(lambda: self._read_json(request))

    def _read_json(self, request: urllib.request.Request) -> dict[str, Any]:
        """发起一次真实请求并解析 JSON。"""

        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)

    def _with_retry(self, operation) -> dict[str, Any]:
        """对交易所接口的偶发网络波动做最小重试。"""

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


class SseFilingsAdapter:
    """SSE 披露列表采集适配器。"""

    def __init__(self, fetcher: SseHttpFetcher | None = None) -> None:
        self._fetcher = fetcher or SseHttpFetcher()

    def list_filings(
        self,
        company: SampleCompany,
        start_date: str,
        end_date: str,
    ) -> list[FilingRecord]:
        """按公司和时间范围抓取 SSE 披露列表。"""

        payload = self._fetcher.get_json(
            url=SSE_ANNOUNCEMENT_URL,
            params=self._build_query_params(
                company=company,
                start_date=start_date,
                end_date=end_date,
            ),
            headers={
                # 交易所接口对 Referer 更友好，首版先显式带上，减少被拦截概率。
                "Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )
        return [
            normalize_sse_record(raw_item=item, company_name=company.company_name)
            for item in _flatten_sse_result(payload.get("result"))
        ]

    def _build_query_params(
        self,
        company: SampleCompany,
        start_date: str,
        end_date: str,
    ) -> dict[str, object]:
        # 这里对齐官网脚本中的默认参数，后面若要翻页只需要扩这层即可。
        return {
            "isPagination": "true",
            "pageHelp.pageSize": "200",
            "pageHelp.pageNo": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": "1",
            "SECURITY_CODE": company.company_code,
            "START_DATE": start_date,
            "END_DATE": end_date,
        }


def _flatten_sse_result(raw_result: object) -> list[dict[str, object]]:
    """把 SSE 可能返回的分组二维数组拍平成单层记录列表。"""

    if not isinstance(raw_result, list):
        return []

    flattened: list[dict[str, object]] = []
    for item in raw_result:
        if isinstance(item, dict):
            flattened.append(item)
            continue
        if isinstance(item, list):
            for nested in item:
                if isinstance(nested, dict):
                    flattened.append(nested)
    return flattened
