from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SessionContext:
    """V1 跨模块共享的会话上下文契约对象。"""

    # 共享 contract 版本，V1 固定为 v1。
    version: str = "v1"
    # 当前会话的稳定标识。
    session_id: str = ""
    # 当前会话正在讨论的主主题。
    active_topic: str = ""
    # 当前活跃的候选对象列表，例如公司或标的。
    active_candidates: list[str] = field(default_factory=list)
    # 当前上下文中关键证据的引用列表。
    key_evidence_refs: list[str] = field(default_factory=list)
    # 历史对话的压缩摘要，供后续轮次续接。
    history_summary: str = ""
    # 当前允许继续展开的追问方向列表。
    available_follow_ups: list[str] = field(default_factory=list)
    # 预留的可选备注字段，不参与会话续接判断。
    notes: str | None = None
