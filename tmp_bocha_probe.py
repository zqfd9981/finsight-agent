from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from finsight_agent.infra.external.bocha_event_search import BochaEventSearchProvider


QUERIES = [
    "红海局势最近怎么了？",
    "美国加征关税会影响哪些行业？",
    "中东局势对A股黄金股影响",
    "美元指数的上升会对A股产生哪些方面的影响",
    "宁德时代扩产公告意味着什么？",
    "AI 算力行情最近有哪些新催化？",
    "钢铁新一轮产能去化到底是行政命令还是市场化倒逼？",
]


def _print_result(index: int, query: str, result_dict: dict[str, object], elapsed_seconds: float) -> None:
    items = result_dict.get("items") or []
    source_status = result_dict.get("source_status") or {}
    preview = []
    for item in items[:3]:
        preview.append(
            {
                "title": item.get("title", ""),
                "publish_date": item.get("publish_date", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
            }
        )

    payload = {
        "index": index,
        "query": query,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "summary_hint": result_dict.get("summary_hint", ""),
        "supporting_points": result_dict.get("supporting_points", []),
        "evidence_refs": result_dict.get("evidence_refs", []),
        "candidate_hints": result_dict.get("candidate_hints", []),
        "source_status": source_status,
        "item_count": len(items),
        "items_preview": preview,
    }
    print("=" * 80)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    provider = BochaEventSearchProvider()
    print(f"Running Bocha probe with {len(QUERIES)} queries")
    for index, query in enumerate(QUERIES, start=1):
        start = time.perf_counter()
        result = provider.search_event_context(
            query=query,
            event="",
            themes=[],
            time_scope="recent",
            limit=3,
        )
        elapsed_seconds = time.perf_counter() - start
        _print_result(index, query, asdict(result), elapsed_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
