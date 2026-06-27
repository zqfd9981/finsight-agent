from __future__ import annotations

from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.final_response import FinalResponse
from shared.contracts.guardrail_or_error_response import GuardrailOrErrorResponse
from shared.contracts.trace_block import TraceBlock


class WorkbenchApiClient:
    """工作台侧统一分析接口 client 骨架。"""

    def __init__(self, endpoint_path: str = "/api/v1/analysis/turns") -> None:
        self.endpoint_path = endpoint_path

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
