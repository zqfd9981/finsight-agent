"""FinSight Agent V1 的后端 API 入口。

向后兼容：
- ``main()`` 仍返回入口说明与元数据，用于脚本 / smoke。
- ``app`` 是 ``uvicorn backend.apps.api.main:app`` 实际加载的 FastAPI 实例。
"""

from backend.apps.api.analysis_turns import build_route_metadata
from backend.apps.api.app_factory import build_app
from backend.apps.api.event_eval import build_eval_route_metadata


APP_ENTRY_DESCRIPTION = "Backend API entrypoint for FinSight Agent V1."

# 真实 FastAPI 实例，供 ``uvicorn backend.apps.api.main:app`` 启动使用。
app = build_app()


def main() -> dict[str, object]:
    """返回入口说明和当前冻结的 API 路由元数据。"""

    return {
        "description": APP_ENTRY_DESCRIPTION,
        "routes": [build_route_metadata(), *build_eval_route_metadata()],
    }
