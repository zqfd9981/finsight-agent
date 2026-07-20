"""单条快速验证脚本，用于在批量测试前确认修复已加载。"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

API_URL = "http://127.0.0.1:8000/api/v1/analysis/turns"
TIMEOUT = 110


def run(query: str) -> None:
    print(f"\n>>> {query}")
    start = time.time()
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
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        return
    elapsed = time.time() - start
    resp_obj = data.get("response", {})
    print(f"耗时: {elapsed:.1f}s")
    print(f"summary: {resp_obj.get('summary', '')[:300]}")
    print(f"answer_markdown:\n{resp_obj.get('answer_markdown', '')[:600]}")


if __name__ == "__main__":
    queries = sys.argv[1:] or ["宁德时代2024年净利润多少"]
    for q in queries:
        run(q)
