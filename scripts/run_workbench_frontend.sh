#!/usr/bin/env bash
# POSIX / Git Bash 工作台前端启动器。
#
# 用法：
#   ./scripts/run_workbench_frontend.sh
#
# 读 ``config/app.yaml`` 的 ``app.workbench.frontend_host`` /
# ``frontend_port`` 段，并以 headless 模式拉起 Streamlit。

set -euo pipefail

cd "$(dirname "$0")/.."

FRONTEND_HOST="${FRONTEND_HOST:-}"
FRONTEND_PORT="${FRONTEND_PORT:-}"

if [ -z "$FRONTEND_HOST" ] || [ -z "$FRONTEND_PORT" ]; then
  if command -v python >/dev/null 2>&1; then
    eval "$(python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('frontend/streamlit_app').resolve()))
from config_resolver import resolve_workbench_config  # noqa: E402
cfg = resolve_workbench_config()
print(f'export FRONTEND_HOST={cfg[\"frontend_host\"]}')
print(f'export FRONTEND_PORT={cfg[\"frontend_port\"]}')
")"
  fi
fi

FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-8501}"

exec python -m streamlit run frontend/streamlit_app/streamlit_entry.py \
  --server.port "${FRONTEND_PORT}" \
  --server.address "${FRONTEND_HOST}" \
  --server.headless true
