from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.contracts.final_response import FinalResponse
from shared.contracts.guardrail_or_error_response import GuardrailOrErrorResponse
from shared.contracts.trace_block import TraceBlock


@dataclass(slots=True)
class AnalysisResponseEnvelope:
    """统一分析接口返回给前端的稳定响应包裹对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 当前轮次所属的会话标识，供前端继续追问时复用。
    session_id: str = ""
    # 当前分析轮次标识，便于后续扩展多轮追踪。
    turn_id: str = "turn_stub"
    # 主响应对象，可能是成功/降级结果，也可能是 guardrail/error 结果。
    response: FinalResponse | GuardrailOrErrorResponse = field(
        default_factory=FinalResponse
    )
    # 这一轮分析附带的可展示 trace 区块列表。
    trace_blocks: list[TraceBlock] = field(default_factory=list)
    # 统一证据注册表：evidence_id -> EvidenceDetail（来源标注用）。
    # 汇聚 retrieve_evidence（年报/公告 RAG）、collect_event_context（事件新闻）、
    # query_structured_data（年报结构化指标）三类证据的完整溯源，供前端
    # 在「参考来源」面板与中间节点渲染来源标注。
    evidence_index: dict[str, Any] = field(default_factory=dict)
    # 预留的可选备注字段，不作为前端渲染主逻辑的依赖。
    notes: str | None = None
