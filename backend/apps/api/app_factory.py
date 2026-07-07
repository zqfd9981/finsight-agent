"""FinSight Agent V1 工作台后端的 FastAPI app factory。

> 上线前必须把 ``cors_origins`` 收窄到生产可信任来源；
> 本 change 默认仅放行本地开发端口 (8501)。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.apps.api.analysis_turns import (
    ANALYSIS_TURNS_PATH,
    handle_analysis_turn,
)
from backend.apps.api.event_eval import (
    EVENT_CASES_PATH,
    EVENT_REPLAY_PATH,
    handle_event_cases,
    handle_event_replay,
)
from shared.contracts.analysis_request import AnalysisRequest


_DEFAULT_CORS_ORIGINS: list[str] = [
    "http://localhost:8501",
    "http://127.0.0.1:8501",
]


def build_app(*, cors_origins: list[str] | None = None) -> FastAPI:
    """构造 FinSight Agent V1 工作台后端的 FastAPI 实例。

    Parameters
    ----------
    cors_origins : list[str] | None
        允许跨域来源列表。``None`` 表示使用本地开发默认 (``localhost:8501``
        与 ``127.0.0.1:8501``)。
    """

    app = FastAPI(
        title="FinSight Agent V1 Workbench Backend",
        version="v1",
    )

    origins = list(cors_origins) if cors_origins is not None else list(_DEFAULT_CORS_ORIGINS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.post(ANALYSIS_TURNS_PATH)
    async def _analysis_turns(request: Request) -> dict[str, Any]:
        body = await request.json()
        # 协议级必填校验：缺少 ``query`` 时直接拒绝，避免被当成业务降级。
        if not body.get("query"):
            raise HTTPException(status_code=422, detail="query is required")
        analysis_request = AnalysisRequest(**body)
        return handle_analysis_turn(analysis_request)

    @app.get(EVENT_CASES_PATH)
    def _event_cases() -> dict[str, Any]:
        return handle_event_cases()

    @app.post(EVENT_REPLAY_PATH)
    async def _event_replay(request: Request) -> dict[str, Any]:
        raw = await request.body()
        body: dict[str, Any] = {}
        if raw:
            body = json.loads(raw)
        return handle_event_replay(body)

    return app
