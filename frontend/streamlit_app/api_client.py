from __future__ import annotations

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
    """工作台侧统一分析接口 client 骨架。"""

    def __init__(
        self,
        endpoint_path: str = "/api/v1/analysis/turns",
        event_cases_path: str = "/api/v1/eval/event-cases",
        event_replay_path: str = "/api/v1/eval/event-replay",
    ) -> None:
        self.endpoint_path = endpoint_path
        self.event_cases_path = event_cases_path
        self.event_replay_path = event_replay_path

    def build_request(
        self,
        query: str,
        session_id: str | None = None,
        include_trace: bool = False,
    ) -> AnalysisRequest:
        """根据是否存在 session_id 生成首轮或追问请求。"""

        return AnalysisRequest(
            query=query,
            query_mode="follow_up" if session_id else "first_turn",
            session_id=session_id,
            include_trace=include_trace,
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
