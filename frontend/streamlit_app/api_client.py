from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict, fields
import json
from typing import Any

import requests

from frontend.streamlit_app.config_resolver import resolve_workbench_config
from frontend.streamlit_app.state.models import (
    EventEvalCaseView,
    EventReplayRecordView,
    EventReplayResultView,
    EventReplayRunView,
    EventReplaySummaryView,
)
from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.analysis_stream_event import AnalysisStreamEvent
from shared.contracts.final_response import FinalResponse
from shared.contracts.guardrail_or_error_response import GuardrailOrErrorResponse
from shared.contracts.trace_block import TraceBlock


class WorkbenchApiClient:
    """HTTP client for the Streamlit workbench."""

    def __init__(
        self,
        endpoint_path: str = "/api/v1/analysis/turns",
        stream_endpoint_path: str = "/api/v1/analysis/turns/stream",
        event_cases_path: str = "/api/v1/eval/event-cases",
        event_replay_path: str = "/api/v1/eval/event-replay",
        *,
        backend_base_url: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.endpoint_path = endpoint_path
        self.stream_endpoint_path = stream_endpoint_path
        self.event_cases_path = event_cases_path
        self.event_replay_path = event_replay_path
        self.timeout_seconds = timeout_seconds

        if backend_base_url is None:
            backend_base_url = resolve_workbench_config()["backend_base_url"]
        self.backend_base_url = backend_base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.backend_base_url}{path}"

    def send_request(
        self,
        *,
        query: str,
        session_id: str | None = None,
        include_trace: bool = True,
        notes: str | None = None,
    ) -> AnalysisResponseEnvelope:
        request = self.build_request(
            query=query,
            session_id=session_id,
            include_trace=include_trace,
            notes=notes,
        )
        response = requests.post(
            self._url(self.endpoint_path),
            json=asdict(request),
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise RuntimeError(
                f"backend POST {self.endpoint_path} failed: "
                f"{response.status_code} {response.text}"
            )
        return self.parse_response(response.json())

    def stream_request(
        self,
        *,
        query: str,
        session_id: str | None = None,
        include_trace: bool = True,
        notes: str | None = None,
    ) -> Iterator[AnalysisStreamEvent]:
        request = self.build_request(
            query=query,
            session_id=session_id,
            include_trace=include_trace,
            notes=notes,
        )
        with requests.post(
            self._url(self.stream_endpoint_path),
            json=asdict(request),
            timeout=self.timeout_seconds,
            stream=True,
        ) as response:
            if not response.ok:
                raise RuntimeError(
                    f"backend POST {self.stream_endpoint_path} failed: "
                    f"{response.status_code} {response.text}"
                )
            for payload in _iter_sse_payloads(
                response.iter_lines(decode_unicode=True)
            ):
                yield self.parse_stream_event(json.loads(payload))

    def fetch_event_cases(self) -> list[EventEvalCaseView]:
        response = requests.get(
            self._url(self.event_cases_path),
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise RuntimeError(
                f"backend GET {self.event_cases_path} failed: "
                f"{response.status_code} {response.text}"
            )
        return self.parse_event_cases(response.json())

    def fetch_event_replay(
        self, *, case_ids: list[str] | None = None
    ) -> EventReplayRunView:
        response = requests.post(
            self._url(self.event_replay_path),
            json={"case_ids": case_ids},
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise RuntimeError(
                f"backend POST {self.event_replay_path} failed: "
                f"{response.status_code} {response.text}"
            )
        return self.parse_event_replay(response.json())

    def build_request(
        self,
        query: str,
        session_id: str | None = None,
        include_trace: bool = False,
        notes: str | None = None,
    ) -> AnalysisRequest:
        return AnalysisRequest(
            query=query,
            query_mode="follow_up" if session_id else "first_turn",
            session_id=session_id,
            include_trace=include_trace,
            notes=notes,
        )

    def parse_response(self, payload: dict) -> AnalysisResponseEnvelope:
        response_payload = payload["response"]
        trace_payloads = payload.get("trace_blocks", [])
        response_type = response_payload.get("response_type", "success")

        if response_type in {"guardrail", "error"}:
            response: FinalResponse | GuardrailOrErrorResponse = (
                GuardrailOrErrorResponse(
                    **_filter_dataclass_payload(
                        GuardrailOrErrorResponse,
                        response_payload,
                    )
                )
            )
        else:
            response = FinalResponse(
                **_filter_dataclass_payload(
                    FinalResponse,
                    response_payload,
                )
            )

        return AnalysisResponseEnvelope(
            version=payload.get("version", "v1"),
            session_id=payload.get("session_id", ""),
            turn_id=payload.get("turn_id", "turn_stub"),
            response=response,
            trace_blocks=[TraceBlock(**item) for item in trace_payloads],
            notes=payload.get("notes"),
        )

    def parse_stream_event(self, payload: dict[str, Any]) -> AnalysisStreamEvent:
        return AnalysisStreamEvent(
            **_filter_dataclass_payload(
                AnalysisStreamEvent,
                payload,
            )
        )

    def extract_envelope_from_stream_event(
        self,
        event: AnalysisStreamEvent,
    ) -> AnalysisResponseEnvelope | None:
        envelope_payload = event.payload.get("response_envelope")
        if not isinstance(envelope_payload, dict):
            return None
        return self.parse_response(envelope_payload)

    def parse_event_cases(self, payload: dict) -> list[EventEvalCaseView]:
        return [
            EventEvalCaseView(
                case_id=item["case_id"],
                query=item["query"],
                expected_intent=item["expected_intent"],
                expected_strategy=item["expected_strategy"],
                allow_degraded=item["allow_degraded"],
                min_target_count=item.get("min_target_count", 0),
                expected_target_keywords=item.get("expected_target_keywords", []),
                notes=item.get("notes"),
            )
            for item in payload.get("cases", [])
        ]

    def parse_event_replay(self, payload: dict) -> EventReplayRunView:
        summary_payload = payload["summary"]
        records = []
        for item in payload.get("records", []):
            result_payload = item["result"]
            records.append(
                EventReplayRecordView(
                    case_id=item["case"]["case_id"],
                    query=item["case"]["query"],
                    result=EventReplayResultView(
                        case_id=result_payload["case_id"],
                        query=result_payload["query"],
                        actual_intent=result_payload["actual_intent"],
                        actual_strategy=result_payload["actual_strategy"],
                        response_type=result_payload["response_type"],
                        degraded=result_payload["degraded"],
                        target_count=result_payload["target_count"],
                        evidence_ref_count=result_payload["evidence_ref_count"],
                        summary=result_payload["summary"],
                        failure_reason=result_payload.get("failure_reason"),
                        target_keywords=result_payload.get("target_keywords", []),
                    ),
                    checks=item.get("checks", []),
                )
            )
        return EventReplayRunView(
            summary=EventReplaySummaryView(
                total=summary_payload["total"],
                pass_count=summary_payload["pass"],
                warn_count=summary_payload["warn"],
                fail_count=summary_payload["fail"],
            ),
            records=records,
        )


def _filter_dataclass_payload(
    dataclass_type: type,
    payload: dict[str, Any],
) -> dict[str, Any]:
    allowed_fields = {field.name for field in fields(dataclass_type)}
    return {key: value for key, value in payload.items() if key in allowed_fields}


def _iter_sse_payloads(lines: Iterator[str]) -> Iterator[str]:
    data_lines: list[str] = []
    for line in lines:
        if line is None:
            continue
        stripped = line.strip()
        if not stripped:
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if stripped.startswith(":"):
            continue
        if stripped.startswith("data:"):
            data_lines.append(stripped[5:].lstrip())
    if data_lines:
        yield "\n".join(data_lines)
