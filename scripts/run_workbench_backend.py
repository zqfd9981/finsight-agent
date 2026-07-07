"""跨平台工作台后端启动器。

用法：
    python scripts/run_workbench_backend.py
    python scripts/run_workbench_backend.py --reload

读 ``config/app.yaml`` 的 ``app.workbench.backend_host`` / ``backend_port``，
并把 ``backend.apps.api.main:app`` 喂给 ``uvicorn.run``。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

# 让 ``frontend.streamlit_app.config_resolver`` 与 ``backend.apps.api.*`` 都能 import。
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_SRC_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="FinSight V1 workbench backend launcher.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="开发期热重载（修改服务端代码自动重启）",
    )
    args = parser.parse_args()

    # 必须在 ``import uvicorn`` 之前把 repo + backend/src 加进 sys.path；
    # config_resolver 依赖 ``import yaml`` 与 ``config/app.yaml`` 路径。
    import uvicorn  # noqa: E402
    from frontend.streamlit_app.config_resolver import (  # noqa: E402
        resolve_workbench_config,
    )

    cfg = resolve_workbench_config()
    uvicorn.run(
        "backend.apps.api.main:app",
        host=cfg["backend_host"],
        port=int(cfg["backend_port"]),
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
