from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.apps.api.analysis_turns import (
    ANALYSIS_TURNS_PATH,
    ANALYSIS_TURNS_STREAM_PATH,
    handle_analysis_turn,
    handle_analysis_turn_stream,
    serialize_stream_event,
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


_logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # 启动期预热：在主线程、尚未接受并发请求时构建检索 facade，
    # 触发 bge-m3 模型（torch/OpenMP）一次性加载，规避请求线程内初始化竞态 SIGSEGV。
    # 仅在启用真实 dense 模型时预热（否则走 384 维哈希回退，无重模型加载）。
    if os.environ.get("DENSE_USE_REAL_MODEL", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        try:
            from finsight_agent.capabilities.retrieval.service import (
                get_shared_retrieval_facade,
            )

            get_shared_retrieval_facade()
            _logger.info("检索 facade 启动期预热完成（bge-m3 模型已加载）")
        except Exception as exc:  # noqa: BLE001
            # 捕获 Python 层异常（如模型文件缺失）以便记录；原生 SIGSEGV 无法被
            # Python 捕获，会直接终止进程——此时配合 faulthandler 可定位到崩溃点。
            _logger.warning("检索 facade 启动期预热失败：%s", exc)
    yield


def build_app(*, cors_origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="FinSight Agent V1 Workbench Backend",
        version="v1",
        lifespan=_lifespan,
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
        if not body.get("query"):
            raise HTTPException(status_code=422, detail="query is required")
        analysis_request = AnalysisRequest(**body)
        return handle_analysis_turn(analysis_request)

    @app.post(ANALYSIS_TURNS_STREAM_PATH)
    async def _analysis_turns_stream(request: Request) -> StreamingResponse:
        body = await request.json()
        if not body.get("query"):
            raise HTTPException(status_code=422, detail="query is required")
        analysis_request = AnalysisRequest(**body)
        stream = (
            serialize_stream_event(event)
            for event in handle_analysis_turn_stream(analysis_request)
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

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
