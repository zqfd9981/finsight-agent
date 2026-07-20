"""用 LangSmith SDK 查询项目下的 runs，确认 tracing 上报成功。"""
from __future__ import annotations

import os
from pathlib import Path

# 加载 .env
REPO_ROOT = Path(__file__).resolve().parents[1]
env_path = REPO_ROOT / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from langsmith import Client

client = Client(
    api_url=os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"),
    api_key=os.getenv("LANGCHAIN_API_KEY", ""),
)

project = os.getenv("LANGCHAIN_PROJECT", "finsight-agent")
print(f"查询 project={project} 下的最近 runs...")

try:
    # 查询根 run
    root_runs = list(client.list_runs(project_name=project, limit=5, is_root=True))
    print(f"找到 {len(root_runs)} 条根 runs（顶层 trace）:")
    for r in root_runs[:2]:  # 只看最近2条
        meta = r.extra or {}
        metadata = meta.get("metadata", {}) if isinstance(meta, dict) else {}
        query = metadata.get("query", "")
        session = metadata.get("session_id", "")
        print(f"\n=== 根 run: name={r.name} id={r.id} status={r.status} ===")
        print(f"  query={query!r} session={session!r}")
        # 查询该根 run 的所有子 runs
        child_runs = list(client.list_runs(project_name=project, parent_run_id=r.id, limit=50))
        print(f"  子 runs ({len(child_runs)} 条):")
        for c in sorted(child_runs, key=lambda x: x.start_time or ""):
            print(f"    - name={c.name!r:30s} run_type={c.run_type:8s} status={c.status:8s} "
                  f"parent={str(c.parent_run_id)[:8] if c.parent_run_id else 'ROOT':8s}")
except Exception as e:
    print(f"查询失败: {type(e).__name__}: {e}")
