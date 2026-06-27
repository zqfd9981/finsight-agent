from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Plan:
    """V1 跨模块共享的执行计划契约对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 当前计划的唯一标识。
    plan_id: str = ""
    # 计划对应的意图类型，需要与路由结果对齐。
    intent: str = ""
    # 顶层执行阶段列表，按实际执行顺序排列。
    stages: list[str] = field(default_factory=list)
    # 各阶段的执行约束，例如预算、时间提示或输出偏好。
    stage_constraints: dict[str, Any] = field(default_factory=dict)
    # 最终响应模式，例如 report 或 brief_answer。
    response_mode: str = ""
    # 预留的可选备注字段，不参与阶段编排判断。
    notes: str | None = None
    # 仅用于调试的补充元数据，下游不应依赖。
    debug_meta: dict[str, Any] = field(default_factory=dict)
