"""检查 query_structured_data stage 的 key_outputs 字段名。"""
import json
import urllib.request

body = json.dumps({
    "query": "宁德时代2024年的归母净利润怎么样？",
    "query_mode": "first_turn",
    "session_id": None,
    "include_trace": True,
}).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/analysis/turns",
    data=body,
    headers={"Content-Type": "application/json"},
)
resp = urllib.request.urlopen(req, timeout=120)
data = json.loads(resp.read())

print("summary:", data.get("response", {}).get("summary", "")[:200])
print()
for tb in data.get("trace_blocks", []):
    if tb.get("block_type") == "execution":
        payload = tb.get("payload_summary", {})
        for obs in payload.get("stage_observations", []):
            if obs.get("stage_name") == "query_structured_data":
                print("query_structured_data key_outputs:")
                ko = obs.get("key_outputs", {})
                for k, v in ko.items():
                    print(f"  {k!r}: {v!r}")
