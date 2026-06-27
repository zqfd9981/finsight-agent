from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TraceBlock:
    """V1 跨模块共享的 trace 区块契约对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # trace 区块类型，例如 routing、planning 或 retrieval。
    block_type: str = ""
    # 面向前端展示的区块标题。
    title: str = ""
    # 当前 trace 区块的状态。
    status: str = "degraded"
    # 用于展示的 payload 摘要，而不是完整原始对象。
    payload_summary: dict[str, Any] = field(default_factory=dict)
    # 指向原始对象或记录的引用列表。
    raw_refs: list[str] = field(default_factory=list)
    # 预留的可选备注字段，不作为前端核心渲染依据。
    notes: str | None = None
