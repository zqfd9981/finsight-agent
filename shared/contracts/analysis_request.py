from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AnalysisRequest:
    """工作台到后端统一分析入口的最小请求 contract。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 用户当前这一轮提交的自然语言问题。
    query: str = ""
    # 请求模式，区分首轮问题和基于上下文的追问。
    query_mode: str = "first_turn"
    # 会话标识；首轮请求可为空，追问时用于续接同一会话。
    session_id: str | None = None
    # 是否要求后端在响应中附带 trace_blocks。
    include_trace: bool = False
    # 预留的可选备注字段，不参与核心流程判断。
    notes: str | None = None
