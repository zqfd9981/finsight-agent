"""验证多轮对话 + 指代消解。

测试场景：
1. 首轮: "格力电器货币资金" → 应命中结构化数据
2. 二轮: "它的净利润呢" → 应指代消解为"格力电器" + 净利润
3. 三轮: "宁德时代资产负债率" → 应判定为 redirect，切换公司
"""
import json
import urllib.request

BACKEND = "http://127.0.0.1:8000/api/v1/analysis/turns"

def send_turn(query, session_id=None):
    body = json.dumps({
        "query": query,
        "query_mode": "follow_up" if session_id else "first_turn",
        "session_id": session_id,
        "include_trace": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        BACKEND,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read())


print("=" * 60)
print("第 1 轮: 格力电器货币资金")
print("=" * 60)
r1 = send_turn("格力电器货币资金")
sid = r1.get("session_id", "")
print(f"session_id: {sid}")
print(f"response_type: {r1.get('response', {}).get('response_type', '')}")
summary1 = r1.get("response", {}).get("summary", "") or ""
print(f"summary: {summary1[:200]}")
for tb in r1.get("trace_blocks", []):
    if tb.get("block_type") == "routing":
        payload = tb.get("payload_summary", {})
        print(f"  routing: intent={payload.get('intent')} entities={payload.get('entities', {})}")

print()
print("=" * 60)
print(f"第 2 轮: 它的净利润呢  (session_id={sid})")
print("=" * 60)
r2 = send_turn("它的净利润呢", session_id=sid)
print(f"response_type: {r2.get('response', {}).get('response_type', '')}")
summary2 = r2.get("response", {}).get("summary", "") or ""
print(f"summary: {summary2[:200]}")
for tb in r2.get("trace_blocks", []):
    if tb.get("block_type") == "routing":
        payload = tb.get("payload_summary", {})
        print(f"  routing: intent={payload.get('intent')} follow_up={payload.get('follow_up_type')}")
        entities = payload.get("entities", {})
        print(f"  entities: company_name={entities.get('company_name')!r} metric_raw={entities.get('metric_raw')!r}")

print()
print("=" * 60)
print(f"第 3 轮: 宁德时代资产负债率  (session_id={sid})")
print("=" * 60)
r3 = send_turn("宁德时代资产负债率", session_id=sid)
print(f"response_type: {r3.get('response', {}).get('response_type', '')}")
summary3 = r3.get("response", {}).get("summary", "") or ""
print(f"summary: {summary3[:200]}")
for tb in r3.get("trace_blocks", []):
    if tb.get("block_type") == "routing":
        payload = tb.get("payload_summary", {})
        print(f"  routing: intent={payload.get('intent')} follow_up={payload.get('follow_up_type')}")
        entities = payload.get("entities", {})
        print(f"  entities: company_name={entities.get('company_name')!r} metric_raw={entities.get('metric_raw')!r}")
