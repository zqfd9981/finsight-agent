"""详细 trace 检查：输出完整 trace_blocks 结构。"""
from __future__ import annotations

import json
import sys
import urllib.request

API_URL = "http://127.0.0.1:8000/api/v1/analysis/turns"


def run(query: str) -> None:
    print(f"\n{'='*80}\n>>> {query}\n{'='*80}")
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
    try:
        with urllib.request.urlopen(req, timeout=115) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return

    print("Top-level keys:", list(data.keys()))
    trace = data.get("trace_blocks") or []
    print(f"trace_blocks: {len(trace)} blocks")
    for i, blk in enumerate(trace):
        if not isinstance(blk, dict):
            continue
        btype = blk.get("block_type")
        print(f"\n--- [{i}] block_type={btype} ---")
        print(json.dumps(blk, ensure_ascii=False, indent=2)[:2500])

    # response
    resp_obj = data.get("response", {})
    print(f"\nresponse.summary: {resp_obj.get('summary', '')[:300]}")


if __name__ == "__main__":
    for q in sys.argv[1:]:
        run(q)
