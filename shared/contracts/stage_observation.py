from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StageObservation:
    """V1 跨模块共享的阶段观测契约对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 当前阶段观测记录的唯一标识。
    observation_id: str = ""
    # 被观测的顶层阶段名称。
    stage_name: str = ""
    # 当前阶段执行状态，例如 success、partial 或 failed。
    status: str = "failed"
    # 进入该阶段时的输入摘要。
    input_summary: dict[str, Any] = field(default_factory=dict)
    # 当前阶段产出的关键结果摘要。
    key_outputs: dict[str, Any] = field(default_factory=dict)
    # 阶段内形成的置信度信号集合。
    confidence_signals: dict[str, Any] = field(default_factory=dict)
    # 与当前阶段结果相关的证据引用列表。
    evidence_refs: list[str] = field(default_factory=list)
    # 预留的可选备注字段，不参与主流程消费。
    notes: str | None = None
