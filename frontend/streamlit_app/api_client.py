from __future__ import annotations

from dataclasses import asdict
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
from shared.contracts.final_response import FinalResponse
from shared.contracts.guardrail_or_error_response import GuardrailOrErrorResponse
from shared.contracts.trace_block import TraceBlock


class WorkbenchApiClient:
    """工作台侧统一分析接口 client。

    既保留原有的 build_request / parse_* 纯函数，也新增 send_* HTTP
    调用方法。``backend_base_url`` 在构造时若未显式提供就从
    :mod:`frontend.streamlit_app.config_resolver` 读取
    ``app.workbench.backend_base_url``，避免硬编码到某个 host。
    """

    def __init__(
        self,
        endpoint_path: str = "/api/v1/analysis/turns",
        event_cases_path: str = "/api/v1/eval/event-cases",
        event_replay_path: str = "/api/v1/eval/event-replay",
        *,
        backend_base_url: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.endpoint_path = endpoint_path
        self.event_cases_path = event_cases_path
        self.event_replay_path = event_replay_path
        self.timeout_seconds = timeout_seconds

        if backend_base_url is None:
            backend_base_url = resolve_workbench_config()["backend_base_url"]
        self.backend_base_url = backend_base_url.rstrip("/")

    # ---------- URL helpers ----------
    def _url(self, path: str) -> str:
        return f"{self.backend_base_url}{path}"

    # ---------- HTTP senders ----------
    def send_request(
        self,
        *,
        query: str,
        session_id: str | None = None,
        include_trace: bool = True,
        notes: str | None = None,
    ) -> AnalysisResponseEnvelope:
        """POST 一轮分析请求到 ``backend_base_url + endpoint_path``。"""

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

    def fetch_event_cases(self) -> list[EventEvalCaseView]:
        """GET 事件评测样本列表。"""

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
        """POST 事件评测 replay 批量执行。"""

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

    # ---------- pure helpers (used by HTTP senders and pages) ----------
    def build_request(
        self,
        query: str,
        session_id: str | None = None,
        include_trace: bool = False,
        notes: str | None = None,
    ) -> AnalysisRequest:
        """根据是否存在 session_id 生成首轮或追问请求。"""

        return AnalysisRequest(
            query=query,
            query_mode="follow_up" if session_id else "first_turn",
            session_id=session_id,
            include_trace=include_trace,
            notes=notes,
        )

    def parse_response(self, payload: dict) -> AnalysisResponseEnvelope:
        """将后端返回的字典恢复为共享 response envelope。"""

        response_payload = payload["response"]
        trace_payloads = payload.get("trace_blocks", [])
        response_type = response_payload.get("response_type", "success")

        if response_type in {"guardrail", "error"}:
            response: FinalResponse | GuardrailOrErrorResponse = (
                GuardrailOrErrorResponse(**response_payload)
            )
        else:
            response = FinalResponse(**response_payload)

        return AnalysisResponseEnvelope(
            version=payload.get("version", "v1"),
            session_id=payload.get("session_id", ""),
            turn_id=payload.get("turn_id", "turn_stub"),
            response=response,
            trace_blocks=[TraceBlock(**item) for item in trace_payloads],
            notes=payload.get("notes"),
        )

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
