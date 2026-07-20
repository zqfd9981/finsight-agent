"""批量测试子集：可指定 ids 子集跳过慢 query（如事件类）。

用法：
    python scripts/batch_test_subset.py            # 跑非事件类
    python scripts/batch_test_subset.py --ids M-001,M-002
    python scripts/batch_test_subset.py --events   # 只跑事件类
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_URL = "http://127.0.0.1:8000/api/v1/analysis/turns"
TIMEOUT = 115
OUTPUT = REPO_ROOT / "scripts" / "test_results.jsonl"

# 复用 batch_test 的 query 集合
from batch_test import TEST_QUERIES

EVENT_CATS = {"event_impact/event_primary", "event_impact/变体"}


def run_one(item: dict) -> dict:
    qid = item["id"]
    query = item["query"]
    start = time.time()
    result = {
        "id": qid,
        "cat": item["cat"],
        "query": query,
        "elapsed": 0.0,
        "status": "unknown",
        "intent": None,
        "summary": "",
        "answer_markdown": "",
        "error": "",
    }
    try:
        req = urllib.request.Request(
            API_URL,
            data=json.dumps({
                "query": query,
                "query_mode": "first_turn",
                "include_trace": True,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - start
        result["elapsed"] = round(elapsed, 1)
        resp_obj = data.get("response", {})
        result["summary"] = str(resp_obj.get("summary") or "")[:600]
        result["answer_markdown"] = str(resp_obj.get("answer_markdown") or "")[:600]
        trace = data.get("trace_blocks") or []
        if isinstance(trace, list):
            for blk in trace:
                if isinstance(blk, dict) and blk.get("block_type") == "routing":
                    payload = blk.get("payload") or {}
                    result["intent"] = payload.get("intent")
                    break
        result["status"] = "ok"
    except urllib.error.HTTPError as e:
        result["elapsed"] = round(time.time() - start, 1)
        result["status"] = "http_error"
        result["error"] = f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        result["elapsed"] = round(time.time() - start, 1)
        result["status"] = "timeout" if "timeout" in str(e).lower() else "url_error"
        result["error"] = str(e)
    except Exception as e:
        result["elapsed"] = round(time.time() - start, 1)
        result["status"] = "exception"
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ids", help="逗号分隔的 id 子集，仅跑这些")
    p.add_argument("--events", action="store_true", help="仅跑事件类")
    p.add_argument("--no-events", action="store_true", help="跳过事件类")
    p.add_argument("--append", action="store_true", help="追加而非覆盖")
    args = p.parse_args()

    items = TEST_QUERIES
    if args.ids:
        want = {x.strip() for x in args.ids.split(",")}
        items = [it for it in items if it["id"] in want]
    elif args.events:
        items = [it for it in items if it["cat"] in EVENT_CATS]
    elif args.no_events:
        items = [it for it in items if it["cat"] not in EVENT_CATS]

    if not args.append:
        OUTPUT.write_text("", encoding="utf-8")
    total = len(items)
    print(f"批量测试 {total} 个 query")
    print("=" * 80)
    results = []
    for i, item in enumerate(items, 1):
        print(f"[{i}/{total}] {item['id']} {item['query'][:40]}", flush=True)
        r = run_one(item)
        results.append(r)
        with OUTPUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        icon = "OK" if r["status"] == "ok" else "XX"
        am = r["answer_markdown"][:100].replace("\n", " ")
        print(f"  [{icon}] {r['status']} {r['elapsed']}s intent={r['intent']} | {am}")
        if r["error"]:
            print(f"  ERR: {r['error']}")

    print("\n" + "=" * 80)
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"成功: {ok}/{total}")
    print(f"平均: {sum(r['elapsed'] for r in results)/max(total,1):.1f}s  最大: {max((r['elapsed'] for r in results), default=0):.1f}s")
    for r in results:
        if r["status"] != "ok":
            print(f"  FAIL {r['id']} {r['query'][:30]} → {r['status']}")


if __name__ == "__main__":
    main()
