"""验证 LangSmith tracing 是否真的启用并成功上报。

1. 检查环境变量是否加载
2. 调用 setup_langsmith_tracing()
3. 通过 LangSmith REST API 查询 finsight-agent 项目下的最近 runs
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# 加载 .env
REPO_ROOT = Path(__file__).resolve().parents[1]
env_path = REPO_ROOT / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    os.environ.setdefault(key, value)

# 加入 backend.src 到 sys.path 以导入 feature_flags
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT))

from finsight_agent.config.feature_flags import (  # noqa: E402
    langsmith_api_key,
    langsmith_project,
    setup_langsmith_tracing,
)

print("=== 1. 环境变量检查 ===")
print(f"LANGCHAIN_TRACING_V2 = {os.getenv('LANGCHAIN_TRACING_V2')!r}")
print(f"LANGCHAIN_API_KEY = {os.getenv('LANGCHAIN_API_KEY', '')[:20]}...")
print(f"LANGCHAIN_PROJECT = {os.getenv('LANGCHAIN_PROJECT')!r}")
print(f"LANGCHAIN_ENDPOINT = {os.getenv('LANGCHAIN_ENDPOINT')!r}")
print(f"FINSIGHT_USE_LANGGRAPH_ORCHESTRATOR = {os.getenv('FINSIGHT_USE_LANGGRAPH_ORCHESTRATOR')!r}")

print("\n=== 2. setup_langsmith_tracing() 调用 ===")
enabled = setup_langsmith_tracing()
print(f"setup_langsmith_tracing() 返回: {enabled}")
print(f"langsmith_api_key() = {langsmith_api_key()[:20]}...")
print(f"langsmith_project() = {langsmith_project()}")

print("\n=== 3. 查询 LangSmith 项目下的最近 runs ===")
api_key = langsmith_api_key()
project = langsmith_project()
endpoint = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

# LangSmith REST API: GET /runs?session={project}
# Bearer token 认证
url = f"{endpoint}/runs?session={project}&limit=5"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
try:
    resp = urllib.request.urlopen(req, timeout=30)
    runs = json.loads(resp.read())
    print(f"查询成功，返回 {len(runs)} 条 runs:")
    for r in runs[:5]:
        print(f"  - name={r.get('name')} status={r.get('status')} "
              f"start={r.get('start_time')} end={r.get('end_time')}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode()[:300]}")
except Exception as e:
    print(f"查询失败: {type(e).__name__}: {e}")
