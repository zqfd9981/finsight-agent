#!/usr/bin/env bash
# POSIX / Git Bash 工作台一键启动器：先后端再前端。
#
# 用法：
#   ./scripts/run_workbench.sh
#
# 行为：
#   1. 把后端作为后台进程拉起，等待 ``/api/v1/eval/event-cases`` 就绪。
#   2. 前台拉起 Streamlit 前端。
#   3. 用户按 Ctrl+C 时优雅杀掉后端。

set -euo pipefail

cd "$(dirname "$0")/.."

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
HEALTH_URL="http://${BACKEND_HOST}:${BACKEND_PORT}/api/v1/eval/event-cases"

echo "[run_workbench] starting backend on ${BACKEND_HOST}:${BACKEND_PORT} ..."
python scripts/run_workbench_backend.py &
BACKEND_PID=$!

cleanup() {
  echo "[run_workbench] stopping backend (pid=${BACKEND_PID}) ..."
  if kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "[run_workbench] waiting for backend health at ${HEALTH_URL} ..."
ready=0
for _ in $(seq 1 60); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "[run_workbench] backend exited prematurely; aborting."
    exit 1
  fi
  sleep 0.5
done

if [ "$ready" -ne 1 ]; then
  echo "[run_workbench] backend did not become ready in time."
  exit 1
fi

echo "[run_workbench] backend is ready. starting Streamlit frontend ..."
exec ./scripts/run_workbench_frontend.sh
