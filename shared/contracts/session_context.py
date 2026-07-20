from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ConversationTurn:
    """单轮对话记录（v2 会话记忆核心单元）。

    保留每轮的 query、intent、答案摘要与 entities 快照，
    用于多轮指代消解与历史回溯。
    """

    # 轮次稳定标识，turn_xxxxxxxx
    turn_id: str = ""
    # 用户原文
    query: str = ""
    # first_turn / follow_up
    query_mode: str = ""
    # metric_lookup / general_finance_qa / ...
    intent: str = ""
    # 最终答案摘要（前 200 字符）
    response_summary: str = ""
    # router 提取的 entities 快照（company/metric/time_scope）
    entities_snapshot: dict = field(default_factory=dict)
    # 本轮引用的证据
    evidence_refs: list[str] = field(default_factory=list)
    # ISO 时间戳
    created_at: str = ""


@dataclass(slots=True)
class SessionContext:
    """跨模块共享的会话上下文契约对象。

    v2 升级要点：
    - 新增 ``turns`` 列表保留最近 3 轮完整原文（短期记忆）
    - 新增 ``active_metrics`` / ``active_time_scope`` 支持指标/时间指代消解
    - ``history_summary`` 角色变更：仅保存第 4 轮及更早的 LLM 压缩摘要
    - v1 字段（active_topic / active_candidates / key_evidence_refs /
      available_follow_ups）保留，平滑过渡
    """

    # 共享 contract 版本，V1 固定为 v1，V2 为 v2。
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
    # ── v2 新增字段 ──
    # 活跃指标（metric standard_name），支持"这个指标"指代消解
    active_metrics: list[str] = field(default_factory=list)
    # 活跃时间范围（period_end/fiscal_year），支持"那段时间"指代消解
    active_time_scope: dict = field(default_factory=dict)
    # 完整轮次历史（最多保留 3 轮原文，更早的进 history_summary）
    turns: list[ConversationTurn] = field(default_factory=list)
