from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_stream_event import AnalysisStreamEvent

from finsight_agent.workbench_backend_api.service import WorkbenchBackendApiService


ANALYSIS_TURNS_PATH = "/api/v1/analysis/turns"
ANALYSIS_TURNS_STREAM_PATH = "/api/v1/analysis/turns/stream"


def build_route_metadata() -> dict[str, str]:
    return {
        "method": "POST",
        "path": ANALYSIS_TURNS_PATH,
        "handler": "handle_analysis_turn",
    }


def handle_analysis_turn(request: AnalysisRequest) -> dict[str, Any]:
    response = WorkbenchBackendApiService().build_response(request)
    return asdict(response)


def handle_analysis_turn_stream(request: AnalysisRequest):
    return WorkbenchBackendApiService().stream_response_events(request)


def serialize_stream_event(event: AnalysisStreamEvent) -> str:
    body = json.dumps(asdict(event), ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event_type}\ndata: {body}\n\n"
