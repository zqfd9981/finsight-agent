from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FinalResponse:
    """V1 面向用户的最终响应契约对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 响应类型，表示成功、降级等面向用户的结果状态。
    response_type: str = "degraded"
    # 当前响应所属的会话标识。
    session_id: str = ""
    # 面向用户的核心结论摘要。
    summary: str = ""
    # 结构化报告区块列表，供前端逐块渲染。
    report_blocks: list[dict[str, Any]] = field(default_factory=list)
    # 当前结果中需要显式提醒用户的不确定性说明。
    uncertainty_notes: list[str] = field(default_factory=list)
    # 建议用户继续查看或追问的下一步动作列表。
    next_actions: list[str] = field(default_factory=list)
    # 预留的可选备注字段，不作为主结果消费依据。
    notes: str | None = None
