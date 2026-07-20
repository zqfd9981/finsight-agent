"""验证净利润 vs 归母净利润 是否被正确区分。"""
import json
import urllib.request

def send_turn(query):
    body = json.dumps({
        "query": query,
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
    return json.loads(resp.read())

queries = [
    "宁德时代2024年净利润是多少",
    "宁德时代2024年归母净利润是多少",
    "宁德时代2024年净利润怎么样",
]

for q in queries:
    print("=" * 60)
    print(f"query: {q}")
    print("=" * 60)
    r = send_turn(q)
    summary = r.get("response", {}).get("summary", "") or ""
    print(f"summary: {summary[:200]}")
    for tb in r.get("trace_blocks", []):
        if tb.get("block_type") == "routing":
            payload = tb.get("payload_summary", {})
            entities = payload.get("entities", {})
            metric_entity = entities.get("metric", {})
            if isinstance(metric_entity, dict):
                print(f"  metric.raw = {metric_entity.get('raw')!r}")
                print(f"  metric.standard_name = {metric_entity.get('standard_name')!r}")
            else:
                print(f"  metric = {metric_entity!r}")
    print()
