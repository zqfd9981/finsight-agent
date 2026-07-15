"""调试 MinerU batch 查询接口：上传文件并打印 batch 响应。"""
import os
import time
import requests
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
pdf_path = REPO_ROOT / "var" / "data" / "raw_filings" / "002129_TCL中环" / "annual" / "2025" / "002129_TCL中环_annual_report_2025_20250426.pdf"
api_key = os.getenv("MINERU_API_KEY", "")

# 1. 申请上传链接
url = "https://mineru.net/api/v4/file-urls/batch"
body = {
    "files": [{"name": pdf_path.name, "page_ranges": "10-12"}],
    "model_version": "vlm",
    "enable_formula": True,
    "enable_table": True,
}
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
print(f"[1] 申请上传链接...")
resp = requests.post(url, headers=headers, json=body, timeout=30)
data = resp.json()["data"]
batch_id = data["batch_id"]
upload_url = data["file_urls"][0]
print(f"  batch_id: {batch_id}")

# 2. 上传文件
print(f"[2] 上传文件...")
with pdf_path.open("rb") as f:
    put_resp = requests.put(upload_url, data=f, timeout=300)
print(f"  status: {put_resp.status_code}")

# 3. 轮询 batch 直到 done
print(f"[3] 轮询 batch 结果直到 done...")
for i in range(60):
    time.sleep(5)
    url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
    resp = requests.get(url, headers=headers, timeout=30)
    payload = resp.json()
    results = payload.get("data", {}).get("extract_result") or []
    if not results:
        print(f"  [{i+1}] no extract_result yet")
        continue
    item = results[0]
    state = item.get("state", "")
    print(f"  [{i+1}] state={state}")
    if state == "done":
        print(f"\n=== done 状态完整返回 ===")
        print(item)
        break
    if state == "failed":
        print(f"\n=== failed ===")
        print(item)
        break
