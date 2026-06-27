from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class GuardrailOrErrorResponse:
    """V1 跨模块共享的 guardrail / error 响应契约对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 响应类型，限定为 guardrail 或 error。
    response_type: str = "guardrail"
    # 触发 guardrail 或错误的原因代码。
    reason_code: str = ""
    # 当前流程推进到的阶段，用于解释停止位置。
    progress_state: str = ""
    # 在受限或出错情况下仍可给出的部分回答。
    partial_answer: str = ""
    # 建议用户下一步如何补充信息或调整问题。
    suggested_next_actions: list[str] = field(default_factory=list)
    # 关联的 trace 引用列表，方便前端定位详情。
    trace_refs: list[str] = field(default_factory=list)
    # 预留的可选备注字段，不参与主渲染判断。
    notes: str | None = None
