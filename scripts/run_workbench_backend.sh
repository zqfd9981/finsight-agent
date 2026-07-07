#!/usr/bin/env bash
# POSIX / Git Bash 工作台后端启动器（包装 Python launcher）。
#
# 用法：
#   ./scripts/run_workbench_backend.sh
#   ./scripts/run_workbench_backend.sh --reload

set -euo pipefail

cd "$(dirname "$0")/.."
exec python scripts/run_workbench_backend.py "$@"
