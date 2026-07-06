from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass


BOCHA_WEB_SEARCH_URL = "https://api.bochaai.com/v1/web-search"


@dataclass(slots=True)
class BochaSmokeResult:
    total: int
    items: list[dict[str, str]]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="测试博查（Bocha）Web Search API 是否可用。",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("BOCHA_API_KEY") or "",
        help=(
            "博查 API key。默认读取环境变量 BOCHA_API_KEY；未设置则报错退出。"
        ),
    )
    parser.add_argument(
        "--query", default="红海局势升级 航运", help="搜索关键词。"
    )
    parser.add_argument("--limit", type=int, default=3, help="返回结果条数。")
    parser.add_argument(
        "--freshness",
        default="oneWeek",
        choices=("noLimit", "oneDay", "oneWeek", "oneMonth", "oneYear"),
        help="时间窗口。默认 oneWeek。",
    )
    return parser


def _fetch_bocha(
    *, api_key: str, query: str, limit: int, freshness: str
) -> BochaSmokeResult:
    body = {
        "query": query,
        "freshness": freshness,
        "summary": True,
        "count": limit,
    }
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(BOCHA_WEB_SEARCH_URL, data=data, method="POST")
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "finsight-bocha-smoke-test/1.0")
    with urllib.request.urlopen(request, timeout=30.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    web_pages = (payload.get("data") or {}).get("webPages", {})
    value = web_pages.get("value") or []
    items: list[dict[str, str]] = []
    for entry in value:
        items.append(
            {
                "name": str(entry.get("name") or "").strip(),
                "url": str(entry.get("url") or "").strip(),
                "datePublished": str(entry.get("datePublished") or "").strip(),
                "snippet": (
                    str(entry.get("summary") or "").strip()
                    or str(entry.get("snippet") or "").strip()
                ),
            }
        )
    return BochaSmokeResult(total=len(items), items=items)


def _print_success(query: str, freshness: str, result: BochaSmokeResult) -> None:
    print("Bocha Web Search 测试成功")
    print(f"query={query}")
    print(f"freshness={freshness}")
    print(f"total={result.total}")
    print()
    if not result.items:
        print("未返回结果，但接口已正常响应。")
        return
    print("前几条结果：")
    for idx, item in enumerate(result.items, start=1):
        print(f"[{idx}] {item['name']}")
        if item["datePublished"]:
            print(f"    published: {item['datePublished']}")
        if item["url"]:
            print(f"    url: {item['url']}")
        if item["snippet"]:
            wrapped = textwrap.fill(
                item["snippet"][:200],
                width=80,
                initial_indent="    snippet: ",
                subsequent_indent="             ",
            )
            print(wrapped)
        print()


def _print_http_error(error: urllib.error.HTTPError) -> None:
    print("Bocha Web Search 测试失败", file=sys.stderr)
    print(f"http_status={error.code}", file=sys.stderr)
    try:
        payload = error.read().decode("utf-8", errors="replace")
    except Exception:
        payload = ""
    if error.code == 401:
        print("原因：API key 无效或缺失。", file=sys.stderr)
    elif error.code == 403:
        print("原因：当前 key 没有访问权限。", file=sys.stderr)
    elif error.code == 429:
        print("原因：触发 Bocha API 限流。", file=sys.stderr)
    else:
        print("原因：Bocha API 返回了非预期 HTTP 错误。", file=sys.stderr)
    if payload:
        print("response_body=", file=sys.stderr)
        print(payload, file=sys.stderr)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.api_key:
        print("缺少 BOCHA_API_KEY：请传 --api-key 或设置环境变量 BOCHA_API_KEY。", file=sys.stderr)
        return 2

    try:
        result = _fetch_bocha(
            api_key=args.api_key,
            query=args.query,
            limit=args.limit,
            freshness=args.freshness,
        )
    except urllib.error.HTTPError as error:
        _print_http_error(error)
        return 1
    except urllib.error.URLError as error:
        print("Bocha Web Search 测试失败", file=sys.stderr)
        print(f"network_error={error}", file=sys.stderr)
        return 2
    except Exception as error:  # pragma: no cover - smoke 兜底
        print("Bocha Web Search 测试失败", file=sys.stderr)
        print(f"unexpected_error={error}", file=sys.stderr)
        return 3

    _print_success(args.query, args.freshness, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())