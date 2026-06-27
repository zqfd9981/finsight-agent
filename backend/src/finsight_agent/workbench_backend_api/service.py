from __future__ import annotations

from shared.contracts.analysis_request import AnalysisRequest
from shared.contracts.analysis_response_envelope import AnalysisResponseEnvelope
from shared.contracts.trace_block import TraceBlock
from shared.enums.follow_up_type import FollowUpType
from shared.enums.intent import Intent

from finsight_agent.capabilities.reporting.service import ReportingService
from finsight_agent.control_plane.router.service import RouterService


class WorkbenchBackendApiService:
    """统一分析入口的最小后端适配服务。"""

    def __init__(self) -> None:
        self._router_service = RouterService()
        self._reporting_service = ReportingService()

    def build_stub_response(self, request: AnalysisRequest) -> AnalysisResponseEnvelope:
        """根据共享 request contract 返回稳定的占位响应 envelope。"""
        session_id = request.session_id or "sess_stub"
        router_result = self._router_service.build_metric_lookup_stub()

        if request.query_mode == "follow_up":
            router_result.follow_up_type = FollowUpType.DRILLDOWN.value

        response = self._reporting_service.build_brief_response(
            session_id=session_id,
            summary=f"占位分析结果：{request.query}",
        )
        trace_blocks: list[TraceBlock] = []
        if request.include_trace:
            trace_blocks.append(
                TraceBlock(
                    block_type="routing",
                    title="路由结果",
                    status="success",
                    payload_summary={
                        "intent": router_result.intent,
                        "follow_up_type": router_result.follow_up_type,
                        "query_mode": request.query_mode,
                    },
                    raw_refs=[Intent.METRIC_LOOKUP.value],
                )
            )

        return AnalysisResponseEnvelope(
            session_id=session_id,
            turn_id="turn_stub",
            response=response,
            trace_blocks=trace_blocks,
        )
