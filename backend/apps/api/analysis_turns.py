from __future__ import annotations

from dataclasses import asdict
from typing import Any

from shared.contracts.analysis_request import AnalysisRequest

from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService


ANALYSIS_TURNS_PATH = "/api/v1/analysis/turns"


def build_route_metadata() -> dict[str, str]:
    """返回统一分析入口的路由元数据。"""
    return {
        "method": "POST",
        "path": ANALYSIS_TURNS_PATH,
        "handler": "handle_analysis_turn",
    }


def handle_analysis_turn(request: AnalysisRequest) -> dict[str, Any]:
    """使用统一分析入口处理一轮分析，并返回可序列化结果。"""
    response = WorkbenchBackendApiService().build_response(request)
    return asdict(response)
