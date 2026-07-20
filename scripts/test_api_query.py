"""通过 API 发起真实查询，验证 LangSmith tracing。"""
import json
import urllib.request

body = json.dumps({
    "query": "格力电器货币资金",
    "query_mode": "conversational",
    "session_id": "test_langsmith_003",
    "include_trace": True,
}).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/analysis/turns",
    data=body,
    headers={"Content-Type": "application/json"},
)
resp = urllib.request.urlopen(req, timeout=120)
data = json.loads(resp.read())

print("session_id:", data.get("session_id"))
print("response_type:", data.get("response", {}).get("response_type", ""))
summary = data.get("response", {}).get("summary", "") or ""
print("summary:", summary[:200])
print("trace_blocks:", len(data.get("trace_blocks", [])))
for tb in data.get("trace_blocks", []):
    bt = tb.get("block_type", "")
    st = tb.get("status", "")
    print(f"  - block_type={bt} status={st}")
