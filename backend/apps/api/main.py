"""FinSight Agent V1 的后端 API 入口骨架。"""

from backend.apps.api.analysis_turns import build_route_metadata


# 当前阶段只冻结统一分析入口的元数据，不接入真实 FastAPI 实例。
APP_ENTRY_DESCRIPTION = "Backend API entrypoint placeholder for FinSight Agent V1."


def main() -> dict[str, object]:
    """返回入口说明和统一分析路由元数据，供骨架阶段校验。"""
    return {
        "description": APP_ENTRY_DESCRIPTION,
        "routes": [build_route_metadata()],
    }
